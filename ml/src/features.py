"""Représentations vectorielles avec FashionCLIP (patrickjohncyh/fashion-clip).

Les projections sont calculées explicitement (vision_model → visual_projection,
text_model → text_projection) pour rester compatible avec transformers 4.x et 5.x.

Origine : ce module est une copie verbatim du notebook de l'équipe
(01_data_understanding_exploration_transformation (1).ipynb, src/features.py), placée
ici pour être réutilisée en dehors du notebook (voir ml/notebooks/06_fashionclip_tunisian.py).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

FASHIONCLIP_REPO = "patrickjohncyh/fashion-clip"

# Requêtes textuelles (en anglais : langue d'entraînement de FashionCLIP) pour le zero-shot.
DRESSME_CATEGORY_PROMPTS = {
    "haut": "a top such as a t-shirt, shirt, blouse or sweater",
    "bas": "a bottom such as trousers, jeans, shorts or a skirt",
    "robe": "a dress or a jumpsuit",
    "veste": "a jacket or a coat",
    "chaussures": "a pair of shoes",
    "sac": "a bag",
    "accessoire": "a fashion accessory such as jewellery, a watch, a hat, sunglasses or a scarf",
}
COLOR_PROMPTS = {
    "noir": "black", "blanc": "white", "gris": "grey", "beige": "beige", "marron": "brown",
    "rouge": "red", "rose": "pink", "orange": "orange", "jaune": "yellow", "vert": "green",
    "bleu": "blue", "violet": "purple",
}
STYLE_PROMPTS = {
    "Casual": "casual", "Formal": "formal", "Sports": "sporty", "Ethnic": "traditional ethnic",
    "Party": "party", "Smart Casual": "smart casual", "Travel": "travel", "Home": "loungewear",
}
# No source (Kaggle, Tunisian scrapes, Polyvore) labels pattern at all — these are weak
# labels from FashionCLIP zero-shot, not ground truth. See ml/notebooks/07_pattern_weak_labels.py
# and ml/data/DATA_DICTIONARY.md for the honesty caveat on using these.
PATTERN_PROMPTS = {
    "uni": "a plain solid-color garment with no pattern",
    "rayures": "a striped garment",
    "a_pois": "a polka dot garment",
    "fleuri": "a floral print garment",
    "carreaux": "a checkered or plaid garment",
    "imprime_animal": "an animal print garment such as leopard or snake print",
    "brode": "an embroidered garment with decorative stitching",
    "geometrique": "a garment with a geometric or abstract print",
}


def get_device() -> str:
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


def load_fashionclip(device: str | None = None):
    from transformers import CLIPModel, CLIPProcessor

    device = device or get_device()
    model = CLIPModel.from_pretrained(FASHIONCLIP_REPO).to(device).eval()
    if device == "cuda":
        model = model.half()
    processor = CLIPProcessor.from_pretrained(FASHIONCLIP_REPO)
    return model, processor, device


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.clip(norms, 1e-12, None)


def _embed_pil_images(opener, items, model, processor, device: str, batch_size: int) -> tuple[np.ndarray, list[int]]:
    """Shared batching loop — `opener(item)` must return a PIL Image or raise."""
    import torch

    vectors, kept = [], []
    items = list(items)
    for start in range(0, len(items), batch_size):
        images, batch_idx = [], []
        for offset, item in enumerate(items[start:start + batch_size]):
            try:
                images.append(opener(item).convert("RGB"))
                batch_idx.append(start + offset)
            except Exception:  # noqa: BLE001
                continue
        if not images:
            continue
        inputs = processor(images=images, return_tensors="pt").to(device)
        pixel_values = inputs["pixel_values"].to(model.dtype)
        with torch.no_grad():
            pooled = model.vision_model(pixel_values=pixel_values).pooler_output
            projected = model.visual_projection(pooled)
        vectors.append(projected.float().cpu().numpy())
        kept.extend(batch_idx)
    if not vectors:
        return np.empty((0, model.config.projection_dim), dtype=np.float32), []
    return _normalize(np.concatenate(vectors)).astype(np.float32), kept


def embed_images(paths, model, processor, device: str, batch_size: int = 32) -> tuple[np.ndarray, list[int]]:
    """Embeddings normalisés L2. Renvoie aussi les indices des images réellement traitées."""
    from PIL import Image

    return _embed_pil_images(lambda p: Image.open(p), paths, model, processor, device, batch_size)


def embed_image_bytes(images_bytes, model, processor, device: str, batch_size: int = 32) -> tuple[np.ndarray, list[int]]:
    """Same as embed_images, but from in-memory bytes (e.g. Polyvore's embedded
    images — see polyvore_official.extract_image_bytes_batch) instead of file paths."""
    import io

    from PIL import Image

    return _embed_pil_images(
        lambda b: Image.open(io.BytesIO(b)), images_bytes, model, processor, device, batch_size
    )


def embed_texts(texts: list[str], model, processor, device: str) -> np.ndarray:
    import torch

    inputs = processor(text=texts, return_tensors="pt", padding=True, truncation=True).to(device)
    with torch.no_grad():
        pooled = model.text_model(input_ids=inputs["input_ids"], attention_mask=inputs["attention_mask"]).pooler_output
        projected = model.text_projection(pooled)
    return _normalize(projected.float().cpu().numpy()).astype(np.float32)


def zero_shot(image_vectors: np.ndarray, labels: list[str], model, processor, device: str,
              template: str = "a photo of a {} item of clothing") -> tuple[np.ndarray, np.ndarray]:
    """Classification zero-shot : renvoie (indice du label prédit, probabilités)."""
    text_vectors = embed_texts([template.format(label) for label in labels], model, processor, device)
    scale = float(model.logit_scale.exp().item())
    logits = scale * image_vectors @ text_vectors.T
    logits -= logits.max(axis=1, keepdims=True)
    probs = np.exp(logits)
    probs /= probs.sum(axis=1, keepdims=True)
    return probs.argmax(axis=1), probs


def top_k_similar(query: np.ndarray, vectors: np.ndarray, k: int = 5,
                  exclude_index: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Similarité cosinus (vecteurs déjà normalisés) → (indices, scores) des k plus proches."""
    scores = vectors @ query.reshape(-1)
    if exclude_index is not None:
        scores[exclude_index] = -np.inf
    order = np.argsort(-scores)[:k]
    return order, scores[order]


def project_2d(vectors: np.ndarray, method: str = "umap", seed: int = 42) -> tuple[np.ndarray, str]:
    """Projection 2D pour visualisation : UMAP si disponible, sinon t-SNE."""
    if method == "umap":
        try:
            import umap

            return umap.UMAP(n_components=2, metric="cosine", random_state=seed).fit_transform(vectors), "UMAP"
        except ImportError:
            pass
    from sklearn.manifold import TSNE

    perplexity = min(30, max(5, len(vectors) // 50))
    return TSNE(n_components=2, metric="cosine", perplexity=perplexity, random_state=seed).fit_transform(vectors), "t-SNE"


def save_embeddings(path: str | Path, vectors: np.ndarray, ids: list[str]) -> None:
    np.savez_compressed(path, vectors=vectors, ids=np.array(ids))


def load_embeddings(path: str | Path) -> tuple[np.ndarray, list[str]]:
    data = np.load(path, allow_pickle=False)
    return data["vectors"], data["ids"].tolist()

"""FashionCLIP-based inference for the Vision Agent.

Self-contained here (no import of the top-level ml/ folder) because the backend is
built as its own Docker image from backend/ alone (see infra/docker-compose.yml) — ml/
is a separate research/data-pipeline folder not included in that build context.

- `category`: a linear-probe classifier trained on frozen FashionCLIP embeddings
  (artifacts/category_classifier.joblib — see ml/notebooks/08_category_classifier.py for
  how it was trained and validated: 81% accuracy / 0.81 macro F1 on held-out Tunisian
  photos, vs. 62% / 0.55 for zero-shot).
- `color` / `pattern` / `style`: zero-shot classification (no labeled training data exists
  for these), same prompts as ml/src/features.py.
- The raw embedding is also returned for similarity search (Purchase Agent / Pinecone).
"""

from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

import numpy as np

FASHIONCLIP_REPO = "patrickjohncyh/fashion-clip"
CATEGORY_CLASSIFIER_PATH = Path(__file__).resolve().parent / "artifacts" / "category_classifier.joblib"

COLOR_PROMPTS = {
    "noir": "black", "blanc": "white", "gris": "grey", "beige": "beige", "marron": "brown",
    "rouge": "red", "rose": "pink", "orange": "orange", "jaune": "yellow", "vert": "green",
    "bleu": "blue", "violet": "purple",
}
STYLE_PROMPTS = {
    "Casual": "casual", "Formal": "formal", "Sports": "sporty", "Ethnic": "traditional ethnic",
    "Party": "party", "Smart Casual": "smart casual", "Travel": "travel", "Home": "loungewear",
}
# Weak labels, not ground truth — no source labels pattern at all (see
# ml/data/DATA_DICTIONARY.md). Same prompts validated in ml/notebooks/07_pattern_weak_labels.py.
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


def _get_device() -> str:
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


@lru_cache
def _load_fashionclip():
    from transformers import CLIPModel, CLIPProcessor

    device = _get_device()
    model = CLIPModel.from_pretrained(FASHIONCLIP_REPO).to(device).eval()
    processor = CLIPProcessor.from_pretrained(FASHIONCLIP_REPO)
    return model, processor, device


@lru_cache
def _load_category_classifier():
    import joblib

    if not CATEGORY_CLASSIFIER_PATH.exists():
        raise FileNotFoundError(
            f"{CATEGORY_CLASSIFIER_PATH} missing — run "
            "ml/notebooks/08_category_classifier.py and copy its output here."
        )
    return joblib.load(CATEGORY_CLASSIFIER_PATH)


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return vectors / np.clip(norms, 1e-12, None)


def embed_image_bytes(image_bytes: bytes) -> np.ndarray:
    """Returns a single L2-normalized 512-d FashionCLIP embedding for one image."""
    import torch
    from PIL import Image

    model, processor, device = _load_fashionclip()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    inputs = processor(images=[image], return_tensors="pt").to(device)
    with torch.no_grad():
        pooled = model.vision_model(pixel_values=inputs["pixel_values"]).pooler_output
        projected = model.visual_projection(pooled)
    return _normalize(projected.float().cpu().numpy())[0]


def _embed_texts(texts: list[str]) -> np.ndarray:
    import torch

    model, processor, device = _load_fashionclip()
    inputs = processor(text=texts, return_tensors="pt", padding=True, truncation=True).to(device)
    with torch.no_grad():
        pooled = model.text_model(
            input_ids=inputs["input_ids"], attention_mask=inputs["attention_mask"]
        ).pooler_output
        projected = model.text_projection(pooled)
    return _normalize(projected.float().cpu().numpy())


@lru_cache
def _prompt_text_vectors(prompts: tuple[tuple[str, str], ...], template: str) -> np.ndarray:
    texts = [template.format(value) for _, value in prompts]
    return _embed_texts(texts)


def _zero_shot(embedding: np.ndarray, prompts: dict[str, str], template: str) -> str:
    model, _, _ = _load_fashionclip()
    items = tuple(prompts.items())
    text_vectors = _prompt_text_vectors(items, template)
    scale = float(model.logit_scale.exp().item())
    logits = scale * embedding @ text_vectors.T
    probs = np.exp(logits - logits.max())
    probs /= probs.sum()
    best = int(probs.argmax())
    return list(prompts)[best]


def predict_category(embedding: np.ndarray) -> str:
    clf = _load_category_classifier()
    return clf.predict(embedding.reshape(1, -1))[0]


def predict_color(embedding: np.ndarray) -> str:
    return _zero_shot(embedding, COLOR_PROMPTS, template="a photo of a {} item of clothing")


def predict_pattern(embedding: np.ndarray) -> str:
    return _zero_shot(embedding, PATTERN_PROMPTS, template="{}")


def predict_style(embedding: np.ndarray) -> str:
    return _zero_shot(embedding, STYLE_PROMPTS, template="a photo of a {} item of clothing")


def analyze_image(image_bytes: bytes) -> dict:
    """Runs the full Vision Agent pipeline on one image: category, color, pattern,
    style, and the raw embedding (for similarity search / Pinecone storage)."""
    embedding = embed_image_bytes(image_bytes)
    return {
        "category": predict_category(embedding),
        "colors": [predict_color(embedding)],
        "pattern": predict_pattern(embedding),
        "style": predict_style(embedding),
        "embedding": embedding,
    }

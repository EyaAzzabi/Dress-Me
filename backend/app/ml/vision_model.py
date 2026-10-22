"""FashionCLIP-based inference for the Vision Agent.

Self-contained here (no import of the top-level ml/ folder) because the backend is
built as its own Docker image from backend/ alone (see infra/docker-compose.yml) — ml/
is a separate research/data-pipeline folder not included in that build context.

- `category`: two stages. (1) the 8-class linear probe (artifacts/category_classifier.joblib,
  ml/notebooks/08_category_classifier.py) says whether this is clothing at all
  (hors_perimetre); (2) a dedicated 7-class RBF-SVM on garments only
  (artifacts/garment_category_classifier.joblib, ml/notebooks/11_garment_category_head.py)
  names the category. On the held-out Tunisian garment photos the gate keeps, it is 87.0%
  accurate (macro-F1 0.871 over the 7 garment labels) vs 85.2% (0.851) for the 8-class probe:
  a modest gain (+1.8 points, paired-bootstrap 95% CI [-0.4, +4.2] — not statistically
  significant), clear on robes (F1 0.77 -> 0.86), slightly negative on vestes (0.76 -> 0.71).
  Falls back to the probe if the second artifact is missing.
- `season` / `style`: read through the garment type (app/ml/garment_types.py): FashionCLIP
  recognizes "a pair of shorts" far better than "a summer garment", and each type carries a
  learned leaning toward a season and a usage. Season is only *suggested* when confident
  (SEASON_MIN_CONFIDENCE); style is Casual / Sports / Ethnic / Formal — the only styles with
  enough labels to learn. Without the priors artifact, both fall back to zero-shot prompts.
- `color` / `pattern`: zero-shot classification (no labeled training data of the right kind
  exists). Prompt ensembling, synonyms and a probe trained on the Tunisian color labels were
  all tried and none beat the plain prompt reliably (ml/reports/vision_agent_evaluation.md).
- Every attribute comes with a confidence. `pattern`/`style`/`season` come back as None
  below their minimum confidence rather than storing a near-random guess; `colors` lists up
  to MAX_COLORS labels above COLOR_SECONDARY_MIN_PROB.
- The raw embedding is also returned for similarity search (Purchase Agent / Pinecone).
"""

from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.ml import garment_types

FASHIONCLIP_REPO = "patrickjohncyh/fashion-clip"
CATEGORY_CLASSIFIER_PATH = Path(__file__).resolve().parent / "artifacts" / "category_classifier.joblib"
GARMENT_CLASSIFIER_PATH = Path(__file__).resolve().parent / "artifacts" / "garment_category_classifier.joblib"

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


SEASON_PROMPTS = {
    "ete": "a lightweight summer garment",
    "hiver": "a warm heavy winter garment",
    "mi_saison": "a medium-weight spring or autumn garment",
}

# Below this the category is more guess than reading — typically a photo of several pieces
# at once (a full outfit), which the classifier wasn't trained on (it saw one item per photo).
# Measured end to end on the held-out Tunisian garment photos (735, catalog-style, one item each,
# ml/notebooks/13_vision_agent_evaluation.py): at 0.60 it asks the user to confirm 9.8% of
# garments — 4.6% of the correct predictions and 40.2% of the wrong ones; what gets through is
# 90.3% accurate. Users confirm a held-back category in one tap, so the false alarms are cheap.
# Real phone photos may score differently than catalog shots — revisit with real uploads.
CATEGORY_MIN_CONFIDENCE = 0.60
MAX_COLORS = 3
COLOR_SECONDARY_MIN_PROB = 0.25
PATTERN_MIN_CONFIDENCE = 0.30  # weak labels: below this, report no pattern
# Measured on the 300 labeled Kaggle photos with the type-based method (model in garment_types.py):
# season at >= 0.60 answers 21% of photos with 64% accuracy (the majority class gets 41% on that
# subset); below it, no better than always answering the majority — so no suggestion at all.
# Style at >= 0.70 answers 60% of photos with 0.90 balanced accuracy over the 4 learnable styles.
STYLE_MIN_CONFIDENCE = 0.70  # type-based. (Zero-shot fallback uses ZERO_SHOT_STYLE_MIN_CONFIDENCE.)
SEASON_MIN_CONFIDENCE = 0.60  # below this, don't suggest a season at all
ZERO_SHOT_STYLE_MIN_CONFIDENCE = 0.25
ZERO_SHOT_SEASON_MIN_CONFIDENCE = 0.50


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


@lru_cache
def _load_garment_classifier():
    """The 7-class garment head, or None when the artifact isn't there (older checkout)."""
    import joblib

    if not GARMENT_CLASSIFIER_PATH.exists():
        return None
    return joblib.load(GARMENT_CLASSIFIER_PATH)


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


def _zero_shot_probs(embedding: np.ndarray, prompts: dict[str, str], template: str) -> dict[str, float]:
    model, _, _ = _load_fashionclip()
    items = tuple(prompts.items())
    text_vectors = _prompt_text_vectors(items, template)
    scale = float(model.logit_scale.exp().item())
    logits = scale * embedding @ text_vectors.T
    probs = np.exp(logits - logits.max())
    probs /= probs.sum()
    return dict(zip(prompts, (float(p) for p in probs)))


def _top(probs: dict[str, float]) -> tuple[str, float]:
    label = max(probs, key=probs.get)
    return label, probs[label]


def predict_category(embedding: np.ndarray) -> tuple[str, float]:
    gate = _load_category_classifier()
    x = embedding.reshape(1, -1)
    label = gate.predict(x)[0]
    # A linear probe normally exposes predict_proba; if it doesn't, report full
    # confidence rather than inventing a number.
    confidence = float(gate.predict_proba(x).max()) if hasattr(gate, "predict_proba") else 1.0
    if label == "hors_perimetre":
        return label, confidence  # not clothing: the garment head never saw such photos

    head = _load_garment_classifier()
    if head is None:
        return label, confidence
    probabilities = head.predict_proba(x)[0]
    best = int(probabilities.argmax())
    return str(head.classes_[best]), float(probabilities[best])


def predict_colors(embedding: np.ndarray) -> tuple[list[str], float]:
    """Dominant color first, plus up to MAX_COLORS-1 more that are clearly present."""
    probs = _zero_shot_probs(embedding, COLOR_PROMPTS, template="a photo of a {} item of clothing")
    ranked = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)
    colors = [ranked[0][0]] + [
        label for label, p in ranked[1:MAX_COLORS] if p >= COLOR_SECONDARY_MIN_PROB
    ]
    return colors, ranked[0][1]


def predict_pattern(embedding: np.ndarray) -> tuple[str | None, float]:
    label, confidence = _top(_zero_shot_probs(embedding, PATTERN_PROMPTS, template="{}"))
    return (label if confidence >= PATTERN_MIN_CONFIDENCE else None), confidence


def predict_style(embedding: np.ndarray) -> tuple[str | None, float]:
    if garment_types.available():
        label, confidence = _top(garment_types.usage_posterior(embedding))
        return (label if confidence >= STYLE_MIN_CONFIDENCE else None), confidence
    label, confidence = _top(
        _zero_shot_probs(embedding, STYLE_PROMPTS, template="a photo of a {} item of clothing")
    )
    return (label if confidence >= ZERO_SHOT_STYLE_MIN_CONFIDENCE else None), confidence


def predict_season(embedding: np.ndarray) -> tuple[str | None, float]:
    if garment_types.available():
        label, confidence = _top(garment_types.season_posterior(embedding))
        return (label if confidence >= SEASON_MIN_CONFIDENCE else None), confidence
    label, confidence = _top(_zero_shot_probs(embedding, SEASON_PROMPTS, template="{}"))
    return (label if confidence >= ZERO_SHOT_SEASON_MIN_CONFIDENCE else None), confidence


def analyze_image(image_bytes: bytes) -> dict:
    """Runs the full Vision Agent pipeline on one image: category, colors, pattern,
    style, a suggested season, per-attribute confidence, and the raw embedding (for
    similarity search / Pinecone storage)."""
    embedding = embed_image_bytes(image_bytes)
    category, category_conf = predict_category(embedding)
    colors, color_conf = predict_colors(embedding)
    pattern, pattern_conf = predict_pattern(embedding)
    style, style_conf = predict_style(embedding)
    season, season_conf = predict_season(embedding)
    return {
        "category": category,
        "colors": colors,
        "pattern": pattern,
        "style": style,
        "season": season,
        "category_uncertain": category_conf < CATEGORY_MIN_CONFIDENCE,
        "confidence": {
            "category": round(category_conf, 3),
            "colors": round(color_conf, 3),
            "pattern": round(pattern_conf, 3),
            "style": round(style_conf, 3),
            "season": round(season_conf, 3),
        },
        "embedding": embedding,
    }

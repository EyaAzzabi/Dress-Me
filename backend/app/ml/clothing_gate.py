"""Out-of-distribution guard for the Purchase flow: is this photo a garment at all?

The category classifier's hors_perimetre class only ever saw non-clothing *catalog
products* (cosmetics, boxes...), so a landscape, an animal or a screenshot gets forced
into the nearest garment class ~12 % of the time. A zero-shot "clothing vs. anything
else" check on the same FashionCLIP embedding cuts that to ~3 %, for ~2 more points of
real garments rejected (scripts/evaluate_clothing_gate.py).
"""

from functools import lru_cache

import numpy as np

from app.ml import vision_model

CLOTHING_GATE_PROMPTS = [
    "a photo of a clothing item", "a photo of a top or shirt", "a photo of trousers or a skirt",
    "a photo of a dress", "a photo of a jacket or coat", "a photo of shoes", "a photo of a handbag",
    "a photo of a fashion accessory such as a belt, scarf, hat or jewelry", "a person wearing an outfit",
]
NON_CLOTHING_GATE_PROMPTS = [
    "a photo of a landscape", "a photo of nature", "a photo of a city or building", "a photo of an animal",
    "a photo of food", "a photo of a car or vehicle", "a photo of an electronic device",
    "a photo of furniture or a room", "a screenshot or a document with text",
    "a photo of a cosmetic or beauty product", "a photo of a household object",
    "a close-up photo of a face", "an abstract texture or pattern",
]
CLOTHING_GATE_THRESHOLD = 0.3


@lru_cache
def _text_vectors() -> np.ndarray:
    return vision_model._embed_texts(CLOTHING_GATE_PROMPTS + NON_CLOTHING_GATE_PROMPTS)


def clothing_probability(embeddings: np.ndarray) -> np.ndarray:
    """Zero-shot probability mass on the clothing prompts, for one (512,) or a batch
    (n, 512) of L2-normalized embeddings."""
    model, _, _ = vision_model._load_fashionclip()
    scale = float(model.logit_scale.exp().item())
    logits = scale * np.atleast_2d(embeddings) @ _text_vectors().T
    probs = np.exp(logits - logits.max(axis=1, keepdims=True))
    probs /= probs.sum(axis=1, keepdims=True)
    return probs[:, :len(CLOTHING_GATE_PROMPTS)].sum(axis=1)


def is_clothing(embedding: np.ndarray) -> bool:
    return bool(clothing_probability(embedding)[0] >= CLOTHING_GATE_THRESHOLD)

from typing import Any

import httpx
import numpy as np

from app.agents.base import BaseAgent
from app.ml import clothing_gate, garment_segmentation, vision_model
from app.services.storage import StorageService

# The segmentation's "upper clothes" covers tops and jackets alike: the category
# classifier, restricted to these two classes, decides on the cut-out.
UPPER_BODY_CATEGORIES = ["haut", "veste"]


class ExtractionAgent(BaseAgent):
    """Finds the garments in a photo and returns each one as its own cut-out image
    (white background, stored like any uploaded photo), so a single piece of an
    outfit can be analyzed on its own — the jacket a mannequin wears, not the whole
    shop window.

    Segmentation (app/ml/garment_segmentation.py) only works on photos of people;
    for a product photo with no one in it, the whole image is returned as the single
    garment, classified by the regular Vision Agent pipeline.
    """

    name = "extraction_agent"

    def __init__(self) -> None:
        self.storage = StorageService()

    def run(self, *, image_url: str, **kwargs: Any) -> dict[str, Any]:
        response = httpx.get(image_url, timeout=15.0, follow_redirects=True)
        response.raise_for_status()
        segmentation = garment_segmentation.segment_garments(response.content)

        if not segmentation.person_detected or not segmentation.garments:
            embedding = vision_model.embed_image_bytes(response.content)
            category = vision_model.predict_category(embedding)[0]
            if not clothing_gate.is_clothing(embedding):
                category = "hors_perimetre"
            return {
                "person_detected": segmentation.person_detected,
                "garments": [{
                    "category": category,
                    "color": _main_color(embedding),
                    "image_url": image_url,
                    "share": 1.0,
                }],
            }

        garments = []
        for garment in segmentation.garments:
            content = garment.to_jpeg()
            embedding = vision_model.embed_image_bytes(content)
            category = garment.category
            if category == "haut":
                category = _upper_body_category(embedding)
            garments.append({
                "category": category,
                "color": _main_color(embedding),
                "image_url": self.storage.upload_image(content, "image/jpeg"),
                "share": garment.share,
            })
        return {"person_detected": True, "garments": garments}


def _main_color(embedding: np.ndarray) -> str | None:
    colors, _ = vision_model.predict_colors(embedding)
    return colors[0] if colors else None


def _upper_body_category(embedding: np.ndarray) -> str:
    classifier = vision_model._load_category_classifier()
    probabilities = dict(zip(classifier.classes_, classifier.predict_proba(embedding.reshape(1, -1))[0]))
    return max(UPPER_BODY_CATEGORIES, key=lambda c: probabilities.get(c, 0.0))

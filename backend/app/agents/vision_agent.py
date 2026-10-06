from typing import Any

import httpx

from app.agents.base import BaseAgent
from app.ml import vision_model


class VisionAgent(BaseAgent):
    """Analyzes clothing images: category, color, style, pattern, visual embedding.

    Backed by FashionCLIP (app/ml/vision_model.py) — zero-shot for color/pattern/style
    (no labeled data exists for these), and a linear-probe classifier trained on frozen
    FashionCLIP embeddings for category (81% accuracy on held-out Tunisian photos, vs.
    62% for zero-shot — see ml/notebooks/08_category_classifier.py).

    Only analyzes — does not persist anything. The embedding is returned as a numpy
    array under "embedding" so callers can decide what to do with it: the wardrobe
    route upserts it to Pinecone once an item is actually added (see
    app/api/routes/wardrobe.py), while a purchase check (not yet owned) reads it
    without ever storing it (see app/agents/purchase_agent.py).
    """

    name = "vision_agent"

    def run(self, *, image_url: str) -> dict[str, Any]:
        response = httpx.get(image_url, timeout=15.0, follow_redirects=True)
        response.raise_for_status()
        return vision_model.analyze_image(response.content)

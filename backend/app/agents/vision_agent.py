from typing import Any

import httpx
from PIL import UnidentifiedImageError

from app.agents.base import BaseAgent
from app.ml import vision_model

MAX_IMAGE_BYTES = 10 * 1024 * 1024


class VisionAgent(BaseAgent):
    """Analyzes clothing images: category, color, style, pattern, visual embedding.

    Backed by FashionCLIP (app/ml/vision_model.py) — zero-shot for color/pattern/style
    (no labeled data exists for these), and a linear-probe classifier trained on frozen
    FashionCLIP embeddings for category (81% accuracy on held-out Tunisian photos, vs.
    62% for zero-shot — see ml/notebooks/08_category_classifier.py).

    Besides the attributes it returns a `confidence` dict (one probability per attribute),
    up to 3 `colors`, a suggested `season`, and None for `pattern`/`style`/`season` when
    the model isn't sure enough to say.

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
        content = response.content
        if len(content) > MAX_IMAGE_BYTES:
            raise ValueError(f"Image is too large ({len(content)} bytes, max {MAX_IMAGE_BYTES}).")
        try:
            return vision_model.analyze_image(content)
        except UnidentifiedImageError as exc:
            raise ValueError("The URL doesn't point to a readable image.") from exc

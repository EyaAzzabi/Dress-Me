import uuid
from typing import Any

from app.agents.base import BaseAgent
from app.db import vector_store
from app.services.ecommerce import EcommerceService

DUPLICATE_SIMILARITY = 0.95  # near-identical embedding -> likely the exact same item
GOOD_FIT_SIMILARITY = 0.75  # close enough to the existing wardrobe to call it consistent
ALTERNATIVES_LIMIT = 3


class PurchaseAgent(BaseAgent):
    """Analyzes a potential new purchase: duplicate detection via similarity search
    against the user's own wardrobe (Pinecone, scoped by owner_id), a verdict, and a
    few real catalog alternatives in the same category/color (EcommerceService).

    Never persists the candidate's embedding — it isn't owned yet (see
    app/agents/vision_agent.py's docstring). "Compatibility" here is a plain
    embedding-similarity heuristic against the existing wardrobe, not the trained
    outfit-compatibility model the Polyvore data (ml/) could eventually support — a
    separate, bigger piece of work (see ml/data/DATA_DICTIONARY.md).
    """

    name = "purchase_agent"

    def __init__(self) -> None:
        self.ecommerce_service = EcommerceService()

    def run(
        self, *, image_url: str, attributes: dict[str, Any], user_id: uuid.UUID, **kwargs: Any
    ) -> dict[str, Any]:
        if attributes["category"] == "hors_perimetre":
            return {
                "verdict": "not_recommended",
                "compatibility_score": 0.0,
                "similar_item_ids": [],
                "catalog_alternatives": [],
                "explanation": "This doesn't look like a clothing item.",
            }

        alternatives = self._catalog_alternatives(attributes)
        matches = vector_store.find_similar_items(attributes["embedding"], owner_id=user_id, top_k=10)
        if not matches:
            return {
                "verdict": "recommended",
                "compatibility_score": 0.5,
                "similar_item_ids": [],
                "catalog_alternatives": alternatives,
                "explanation": (
                    "Nothing in your wardrobe to compare this against yet (empty, or "
                    "similarity search isn't configured) — no reason not to get it."
                ),
            }

        same_category = [m for m in matches if m["category"] == attributes["category"]]
        if same_category and same_category[0]["score"] >= DUPLICATE_SIMILARITY:
            return {
                "verdict": "not_recommended",
                "compatibility_score": round(same_category[0]["score"], 2),
                "similar_item_ids": [same_category[0]["item_id"]],
                "catalog_alternatives": alternatives,
                "explanation": "You already own a very similar item.",
            }

        compatibility_score = round(sum(m["score"] for m in matches) / len(matches), 2)
        similar_item_ids = [m["item_id"] for m in matches if m["score"] >= GOOD_FIT_SIMILARITY]
        if compatibility_score >= GOOD_FIT_SIMILARITY:
            verdict, explanation = "recommended", "Visually consistent with pieces you already own."
        else:
            verdict, explanation = "think_twice", "Quite different from your existing wardrobe style."

        return {
            "verdict": verdict,
            "compatibility_score": compatibility_score,
            "similar_item_ids": similar_item_ids,
            "catalog_alternatives": alternatives,
            "explanation": explanation,
        }

    def _catalog_alternatives(self, attributes: dict[str, Any]) -> list[dict]:
        """A few real, similarly-categorized/colored products from the bundled
        Tunisian catalog — not a recommendation, just "here's what else is out there"
        context. Category and color_family values are already French words that match
        the catalog's own naming (see ml/src/preprocessing.py), so they're usable
        directly as a search query without translation."""
        # category is handled by the `category=` filter already — searching by color
        # alone within that filter (rather than re-adding the category as a query word,
        # which would rarely appear in a product name) is what actually narrows results.
        color = attributes["colors"][0] if attributes["colors"] else ""
        return self.ecommerce_service.search_products(
            color, category=attributes["category"], limit=ALTERNATIVES_LIMIT
        )

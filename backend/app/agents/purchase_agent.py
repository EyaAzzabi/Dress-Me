from typing import Any

from app.agents.base import BaseAgent


class PurchaseAgent(BaseAgent):
    """Analyzes a potential new purchase: duplicate detection via similarity search,
    compatibility with the existing wardrobe, and a purchase verdict.
    """

    name = "purchase_agent"

    def run(self, *, image_url: str, **kwargs: Any) -> dict[str, Any]:
        # TODO: embed the candidate item, compare against the wardrobe in Qdrant,
        # then produce a recommended / think_twice / not_recommended verdict
        raise NotImplementedError

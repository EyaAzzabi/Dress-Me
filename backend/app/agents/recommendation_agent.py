from typing import Any

from app.agents.base import BaseAgent


class RecommendationAgent(BaseAgent):
    """Generates personalized outfits from the wardrobe: compatible combinations,
    relevance score, look diversity, and explanations.
    """

    name = "recommendation_agent"

    def run(self, **kwargs: Any) -> dict[str, Any]:
        # TODO: combine wardrobe items + style profile + context into ranked outfits
        raise NotImplementedError

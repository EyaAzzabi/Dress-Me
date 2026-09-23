import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.agents.context_agent import ContextAgent
from app.agents.llm_agent import LLMAgent
from app.agents.purchase_agent import PurchaseAgent
from app.agents.recommendation_agent import RecommendationAgent
from app.agents.style_profile_agent import StyleProfileAgent
from app.agents.vision_agent import VisionAgent
from app.agents.wardrobe_agent import WardrobeAgent


class AgentOrchestrator:
    """Analyzes the incoming request, plans which specialized agents to invoke,
    and coordinates them to produce a single coherent response.

    Mirrors the "Agent Orchestrateur" box in docs/ — the intelligence core that
    sits between the FastAPI layer and the specialized agents.
    """

    def __init__(self, db: Session):
        self.db = db
        self.vision_agent = VisionAgent()
        self.wardrobe_agent = WardrobeAgent(db)
        self.style_profile_agent = StyleProfileAgent()
        self.context_agent = ContextAgent()
        self.recommendation_agent = RecommendationAgent()
        self.purchase_agent = PurchaseAgent()
        self.llm_agent = LLMAgent()

    def recommend_outfits(
        self,
        *,
        user_id: uuid.UUID,
        occasion: str | None = None,
        weather: str | None = None,
        season: str | None = None,
    ) -> dict[str, Any]:
        context = self.context_agent.run(occasion=occasion, weather=weather, season=season)
        wardrobe = self.wardrobe_agent.run(user_id=user_id)
        # TODO: feed wardrobe + context (+ style profile) into recommendation_agent
        return {"context": context, "wardrobe_size": len(wardrobe["items"])}

    def evaluate_purchase(self, *, user_id: uuid.UUID, image_url: str) -> dict[str, Any]:
        attributes = self.vision_agent.run(image_url=image_url)
        verdict = self.purchase_agent.run(image_url=image_url, attributes=attributes)
        return verdict

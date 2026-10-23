import uuid
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.agents.context_agent import ContextAgent
from app.agents.extraction_agent import ExtractionAgent
from app.agents.metadata_agent import MetadataAgent
from app.agents.packing_agent import PackingAgent
from app.agents.purchase_agent import PurchaseAgent
from app.agents.recommendation_agent import RecommendationAgent
from app.agents.style_profile_agent import StyleProfileAgent
from app.agents.vision_agent import VisionAgent
from app.agents.wardrobe_ingestion_agent import WardrobeIngestionAgent
from app.agents.llm_agent import LLMAgent
from app.core.config import get_settings
from app.db import vector_store
from app.ml import ranking_model
from app.models.outfit import Outfit
from app.models.packing_list import PackingList
from app.rag import context_retrieval
from app.services import occasions


class WardrobeItemRejected(ValueError):
    """A clothing image failed the validation used by the wardrobe endpoint."""

    def __init__(self, detail: str | dict[str, Any]):
        message = detail if isinstance(detail, str) else detail.get("message", "Invalid clothing item.")
        super().__init__(message)
        self.detail = detail


class AgentWorkflowService:
    """FastAPI adapter that exposes agent workflows to the API layer.

    LangGraph's LLM supervisor coordinates multi-agent workflows. This service only
    provides the database session and specialist agents to those graphs.
    """

    def __init__(self, db: Session):
        self.db = db
        self.vision_agent = VisionAgent()
        self.wardrobe_ingestion_agent = WardrobeIngestionAgent(db=db, vision_agent=self.vision_agent)
        self.metadata_agent = MetadataAgent(db)
        self.style_profile_agent = StyleProfileAgent(db)
        self.context_agent = ContextAgent()
        self.recommendation_agent = RecommendationAgent()
        self.purchase_agent = PurchaseAgent()
        self.extraction_agent = ExtractionAgent()
        self.packing_agent = PackingAgent()
        # StyleProfileAgent uses LLMAgent to phrase its profile. LangGraph uses the
        # same provider as the supervisor for multi-agent workflows.

    def recommend_outfits(
        self,
        *,
        user_id: uuid.UUID,
        occasion: str | None = None,
        weather: str | None = None,
        season: str | None = None,
        city: str | None = None,
    ) -> dict[str, Any]:
        from app.agents.langgraph_recommendation import LangGraphRecommendation

        return LangGraphRecommendation(self).run(
            user_id=user_id,
            occasion=occasion,
            weather=weather,
            season=season,
            city=city,
        )

    def _save_recommendations(
        self,
        *,
        user_id: uuid.UUID,
        context: dict[str, Any],
        generated: dict[str, Any],
        wardrobe_items: list[Any],
        style_profile: dict[str, Any],
    ) -> dict[str, Any]:
        # Generating the same wardrobe twice shouldn't insert duplicate Outfit rows —
        # reuse the existing one (by its exact set of items) instead of re-saving it.
        existing_by_items = {
            frozenset(o.item_ids): o
            for o in self.db.query(Outfit).filter(Outfit.owner_id == user_id).all()
        }

        result_outfits = []
        new_outfits = []
        items_by_id = {item.id: item for item in wardrobe_items}
        llm_agent = LLMAgent()
        for candidate in generated["outfits"]:
            item_set = frozenset(candidate["item_ids"])
            facts = {
                "items": [
                    {
                        "category": items_by_id[item_id].category,
                        "colors": items_by_id[item_id].colors,
                        "style": items_by_id[item_id].style,
                    }
                    for item_id in candidate["item_ids"]
                    if item_id in items_by_id
                ],
                "context": context,
                "favorite_styles": style_profile.get("favorite_styles", []),
                "relevance_score": candidate["relevance_score"],
                "deterministic_explanation": candidate["explanation"],
            }
            explanation = llm_agent.run(
                task="outfit",
                context=facts,
                cache_scope=str(user_id),
                instruction="Explique les pièces proposées sans changer le classement.",
            )["explanation"] or candidate["explanation"]
            existing = existing_by_items.get(item_set)
            if existing is not None:
                existing.occasion = context["occasion"]
                existing.relevance_score = candidate["relevance_score"]
                existing.explanation = explanation
                result_outfits.append(existing)
                continue
            outfit = Outfit(
                owner_id=user_id,
                item_ids=candidate["item_ids"],
                occasion=context["occasion"],
                relevance_score=candidate["relevance_score"],
                explanation=explanation,
            )
            new_outfits.append(outfit)
            result_outfits.append(outfit)
            existing_by_items[item_set] = outfit  # guards against duplicates within this same batch

        self.db.add_all(new_outfits)
        self.db.commit()
        for outfit in new_outfits:
            self.db.refresh(outfit)

        return {"context": context, "outfits": result_outfits}

    def plan_trip(
        self,
        *,
        user_id: uuid.UUID,
        destination: str,
        duration_days: int,
        trip_type: str,
        start_date: date | None = None,
    ) -> PackingList:
        """Builds and saves a packing list: the season comes from the dates (or the
        destination's current weather for a trip starting within days), outfits already
        planned in the calendar for those days are packed first, and wearing history
        steers the rest toward pieces that haven't been used much."""
        from app.agents.langgraph_workflows import LangGraphWorkflows

        return LangGraphWorkflows(self).plan_trip(
            user_id=user_id,
            destination=destination,
            duration_days=duration_days,
            trip_type=trip_type,
            start_date=start_date,
        )

    def list_outfits(self, *, user_id: uuid.UUID) -> list[Outfit]:
        return (
            self.db.query(Outfit)
            .filter(Outfit.owner_id == user_id)
            .order_by(Outfit.created_at.desc())
            .all()
        )

    def extract_garments(self, *, image_url: str) -> dict[str, Any]:
        return self.extraction_agent.run(image_url=image_url)

    def evaluate_purchase(
        self, *, user_id: uuid.UUID, image_url: str, price: float | None = None,
        category: str | None = None,
    ) -> dict[str, Any]:
        from app.agents.langgraph_workflows import LangGraphWorkflows

        return LangGraphWorkflows(self).evaluate_purchase(
            user_id=user_id,
            image_url=image_url,
            price=price,
            category=category,
        )

    def add_wardrobe_item(
        self,
        *,
        user_id: uuid.UUID,
        image_url: str,
        season: str | None = None,
        category: str | None = None,
    ):
        from app.agents.langgraph_workflows import LangGraphWorkflows

        return LangGraphWorkflows(self).add_wardrobe_item(
            user_id=user_id,
            image_url=image_url,
            season=season,
            category=category,
        )

    @staticmethod
    def _validate_wardrobe_attributes(attributes: dict[str, Any], category: str | None) -> None:
        if attributes["category"] == "hors_perimetre":
            raise WardrobeItemRejected(
                "This photo doesn't look like a clothing item — try a clearer photo of the item alone."
            )
        if attributes.get("category_uncertain") and category is None:
            raise WardrobeItemRejected(
                {
                    "code": "low_category_confidence",
                    "message": (
                        "On n'est pas sûr de la catégorie de cette pièce — la photo montre peut-être "
                        "plusieurs vêtements. Confirme la catégorie, ou ajoute une photo d'une seule pièce."
                    ),
                    "suggested_category": attributes["category"],
                    "confidence": attributes["confidence"]["category"],
                }
            )

    def get_style_profile(self, *, user_id: uuid.UUID) -> dict[str, Any]:
        return self.style_profile_agent.run(user_id=user_id)


# Kept as an import alias for existing API integrations while the orchestration
# itself lives in the LangGraph supervisors above.
AgentOrchestrator = AgentWorkflowService

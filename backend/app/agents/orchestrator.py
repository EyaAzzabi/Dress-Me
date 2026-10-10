import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.agents.context_agent import ContextAgent
from app.agents.extraction_agent import ExtractionAgent
from app.agents.metadata_agent import MetadataAgent
from app.agents.purchase_agent import PurchaseAgent
from app.agents.recommendation_agent import RecommendationAgent
from app.agents.style_profile_agent import StyleProfileAgent
from app.agents.vision_agent import VisionAgent
from app.db import vector_store
from app.models.outfit import Outfit


class AgentOrchestrator:
    """Analyzes the incoming request, plans which specialized agents to invoke,
    and coordinates them to produce a single coherent response.

    Mirrors the "Agent Orchestrateur" box in docs/ — the intelligence core that
    sits between the FastAPI layer and the specialized agents.
    """

    def __init__(self, db: Session):
        self.db = db
        self.vision_agent = VisionAgent()
        self.metadata_agent = MetadataAgent(db)
        self.style_profile_agent = StyleProfileAgent(db)
        self.context_agent = ContextAgent()
        self.recommendation_agent = RecommendationAgent()
        self.purchase_agent = PurchaseAgent()
        self.extraction_agent = ExtractionAgent()
        # LLMAgent isn't called directly here — StyleProfileAgent owns its own
        # instance (the only current consumer; see app/agents/style_profile_agent.py).

    def recommend_outfits(
        self,
        *,
        user_id: uuid.UUID,
        occasion: str | None = None,
        weather: str | None = None,
        season: str | None = None,
        city: str | None = None,
    ) -> dict[str, Any]:
        context = self.context_agent.run(occasion=occasion, weather=weather, season=season, city=city)
        wardrobe = self.metadata_agent.run(user_id=user_id)
        style_profile = self.style_profile_agent.run(user_id=user_id)
        generated = self.recommendation_agent.run(
            wardrobe_items=wardrobe["items"], occasion=context["occasion"],
            favorite_styles=style_profile["favorite_styles"],
        )

        # Generating the same wardrobe twice shouldn't insert duplicate Outfit rows —
        # reuse the existing one (by its exact set of items) instead of re-saving it.
        existing_by_items = {
            frozenset(o.item_ids): o
            for o in self.db.query(Outfit).filter(Outfit.owner_id == user_id).all()
        }

        result_outfits = []
        new_outfits = []
        for candidate in generated["outfits"]:
            item_set = frozenset(candidate["item_ids"])
            existing = existing_by_items.get(item_set)
            if existing is not None:
                result_outfits.append(existing)
                continue
            outfit = Outfit(
                owner_id=user_id,
                item_ids=candidate["item_ids"],
                occasion=context["occasion"],
                relevance_score=candidate["relevance_score"],
                explanation=candidate["explanation"],
            )
            new_outfits.append(outfit)
            result_outfits.append(outfit)
            existing_by_items[item_set] = outfit  # guards against duplicates within this same batch

        self.db.add_all(new_outfits)
        self.db.commit()
        for outfit in new_outfits:
            self.db.refresh(outfit)

        return {"context": context, "outfits": result_outfits}

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
        attributes = self.vision_agent.run(image_url=image_url)
        if category and attributes["category"] != "hors_perimetre":
            # Category already decided on this cut-out by ExtractionAgent (segmentation
            # label + classifier) — more reliable than re-guessing it from the crop alone.
            attributes["category"] = category
        wardrobe = self.metadata_agent.run(user_id=user_id)
        embeddings = vector_store.fetch_embeddings([item.id for item in wardrobe["items"]])
        return self.purchase_agent.run(
            attributes=attributes, wardrobe_items=wardrobe["items"], embeddings=embeddings, price=price,
        )

    def get_style_profile(self, *, user_id: uuid.UUID) -> dict[str, Any]:
        return self.style_profile_agent.run(user_id=user_id)

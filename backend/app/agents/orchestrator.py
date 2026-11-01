import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.agents.llm_agent import LLMAgent
from app.agents.context_agent import ContextAgent
from app.agents.extraction_agent import ExtractionAgent
from app.agents.llm_agent import LLMAgent
from app.agents.metadata_agent import MetadataAgent
from app.agents.packing_agent import PackingAgent
from app.agents.purchase_agent import PurchaseAgent
from app.agents.recommendation_agent import RecommendationAgent
from app.agents.style_profile_agent import StyleProfileAgent
from app.agents.vision_agent import VisionAgent
from app.agents.wardrobe_ingestion_agent import WardrobeIngestionAgent
from app.core.config import get_settings
from app.db import vector_store
from app.ml import clothing_gate, ranking_model
from app.models.outfit import Outfit
from app.models.packing_list import PackingList
from app.models.scheduled_outfit import ScheduledOutfit
from app.rag import context_retrieval
from app.services import occasions
from app.services.seasons import trip_season


class AgentOrchestrator:
    """Analyzes the incoming request, plans which specialized agents to invoke,
    and coordinates them to produce a single coherent response.

    Mirrors the "Agent Orchestrateur" box in docs/ — the intelligence core that
    sits between the FastAPI layer and the specialized agents.
    """

    def __init__(self, db: Session):
        self.db = db
        self.vision_agent = VisionAgent()
        self.wardrobe_ingestion_agent = WardrobeIngestionAgent(db)
        self.metadata_agent = MetadataAgent(db)
        self.style_profile_agent = StyleProfileAgent(db)
        self.context_agent = ContextAgent()
        self.recommendation_agent = RecommendationAgent()
        self.purchase_agent = PurchaseAgent()
        self.extraction_agent = ExtractionAgent()
        self.packing_agent = PackingAgent()
        # Used to phrase outfit explanations (task="outfit"); StyleProfileAgent keeps its
        # own independent instance for the profile narrative.
        self.llm_agent = LLMAgent()

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
        style_profile = self.style_profile_agent.run(user_id=user_id, include_narrative=False)
        usage = self.metadata_agent.usage_history(user_id=user_id)

        items_by_id = {}
        # Compute the shared context vector and the RAG references ONCE, before the
        # generate closure — generate may be called up to twice (season-filtered then
        # full wardrobe), so doing this inside it would double the work (review-F1,
        # review-F13). weather_band is derived from temperature and never passed to
        # run (review-F1/F3); ctx_vec is.
        weather_band = occasions.weather_band(context.get("temperature"))
        ctx_vec = ranking_model.context_vector(
            context.get("occasion_category"), context.get("season"), weather_band
        )
        if get_settings().contextual_rag_enabled:
            references = context_retrieval.retrieve_references(self.db, user_id, context, ctx_vec)
        else:
            references = None

        def generate(items):
            items_by_id.update({item.id: item for item in items})
            return self.recommendation_agent.run(
                wardrobe_items=items, occasion=context["occasion"],
                favorite_styles=style_profile["favorite_styles"], usage=usage,
                season=context.get("season"), temperature=context.get("temperature"),
                weather=context.get("weather"), occasion_category=context.get("occasion_category"),
                formality=context.get("formality"), references=references, ctx_vec=ctx_vec,
                # No llm_agent here on purpose: outfit explanations come from the grounded,
                # cached llm_agent.run(task="outfit") below. Passing it in as well would make a
                # second LLM call per outfit and feed LLM text back in as the "deterministic" fact.
            )

        # Prefer pieces wearable in the context's season; if that leaves nothing to build
        # an outfit from (e.g. only summer pieces in winter), fall back to the whole
        # wardrobe rather than returning nothing.
        generated = generate(
            self.metadata_agent.run(user_id=user_id, wearable_in=context["season"])["items"]
        )
        if not generated["outfits"] and context["season"]:
            generated = generate(self.metadata_agent.run(user_id=user_id)["items"])

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
            facts = {
                "items": [{"category": items_by_id[item_id].category,
                           "colors": items_by_id[item_id].colors,
                           "style": items_by_id[item_id].style}
                          for item_id in candidate["item_ids"] if item_id in items_by_id],
                "context": context,
                "favorite_styles": style_profile["favorite_styles"],
                "relevance_score": candidate["relevance_score"],
                "deterministic_explanation": candidate["explanation"],
            }
            explanation = self.llm_agent.run(
                task="outfit", context=facts, cache_scope=str(user_id),
                instruction="Explique les pièces proposées sans changer le classement.",
            )["explanation"] or candidate["explanation"]
            existing = existing_by_items.get(item_set)
            if existing is not None:
                # Reused identity, current context and usage-based scores.
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
        temperature = None
        weather = self.context_agent.weather_service.get_current_weather(destination)
        if weather is not None:
            temperature = weather["main"]["temp"]
        season = trip_season(start_date, temperature)

        required: set[uuid.UUID] = set()
        if start_date is not None:
            end_date = start_date + timedelta(days=duration_days - 1)
            planned = (
                self.db.query(ScheduledOutfit)
                .filter(
                    ScheduledOutfit.owner_id == user_id,
                    ScheduledOutfit.date >= start_date,
                    ScheduledOutfit.date <= end_date,
                )
                .all()
            )
            required = {item_id for outfit in planned for item_id in outfit.item_ids}

        generated = self.packing_agent.run(
            wardrobe_items=self.metadata_agent.run(user_id=user_id)["items"],
            duration_days=duration_days,
            trip_type=trip_type,
            season=season,
            usage=self.metadata_agent.usage_history(user_id=user_id),
            required_item_ids=required,
        )
        packing_list = PackingList(
            owner_id=user_id,
            destination=destination,
            duration_days=duration_days,
            trip_type=trip_type,
            start_date=start_date,
            season=season,
            item_ids=generated["item_ids"],
            checked_item_ids=[],
        )
        self.db.add(packing_list)
        self.db.commit()
        self.db.refresh(packing_list)
        return packing_list

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
        if not clothing_gate.is_clothing(attributes["embedding"]):
            attributes["category"] = "hors_perimetre"
        elif category and attributes["category"] != "hors_perimetre":
            # Category already decided on this cut-out by ExtractionAgent (segmentation
            # label + classifier) — more reliable than re-guessing it from the crop alone.
            attributes["category"] = category
        wardrobe = self.metadata_agent.run(user_id=user_id)
        embeddings = vector_store.fetch_embeddings([item.id for item in wardrobe["items"]])
        result = self.purchase_agent.run(
            attributes=attributes, wardrobe_items=wardrobe["items"], embeddings=embeddings, price=price,
        )
        if result["item"]["category"] != "hors_perimetre":
            facts = {key: result.get(key) for key in (
                "verdict", "score", "explanation", "item", "factors",
                "outfits_unlocked", "price_insight",
            )}
            # No images, vectors, IDs or purchase history sent to the LLM.
            facts["duplicates"] = [{"category": d.get("category"), "similarity": d["similarity"]}
                                   for d in result.get("duplicates", [])]
            facts["price"] = price
            facts["has_wardrobe_evidence"] = any(str(item.id) in embeddings for item in wardrobe["items"])
            if not result.get("llm"):
                # PurchaseAgent already phrased the verdict when its tool-calling LLM ran.
                explanation = self.llm_agent.run(
                    task="purchase", context=facts, cache_scope=str(user_id),
                    instruction="Explique le verdict fixé ; utiliser l'existant avant d'acheter.",
                )["explanation"]
                if explanation:
                    result = {**result, "explanation": explanation}
        return result

    def get_style_profile(self, *, user_id: uuid.UUID) -> dict[str, Any]:
        return self.style_profile_agent.run(user_id=user_id)

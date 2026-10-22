"""Read-only personal assistant, grounded in the authenticated user's records."""
import json
from time import monotonic
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.llm_agent import LLMAgent
from app.agents.style_profile_agent import StyleProfileAgent
from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.clothing_item import ClothingItem
from app.models.outfit import Outfit
from app.models.purchase_history import PurchaseHistoryEntry
from app.models.user import User

router = APIRouter(prefix="/llm", tags=["llm"])


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1500, pattern=r"\S")
    topic: Literal["wardrobe", "item", "outfit", "purchase"] = "wardrobe"
    record_id: UUID | None = None
    previous_questions: list[Annotated[str, Field(max_length=600)]] = Field(default_factory=list, max_length=4)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=8)
    wardrobe_only: bool = False


def item_facts(item: ClothingItem) -> dict:
    return {"category": item.category, "colors": item.colors or [], "style": item.style,
            "season": item.season, "pattern": item.pattern}


@router.get("/context")
def context(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    profile = StyleProfileAgent(db).run(user_id=user.id, include_narrative=False)
    profile.pop("narrative", None)
    items = db.query(ClothingItem).filter(ClothingItem.owner_id == user.id).order_by(ClothingItem.created_at.desc(), ClothingItem.id).limit(24).all()
    outfits = db.query(Outfit).filter(Outfit.owner_id == user.id).order_by(Outfit.created_at.desc(), Outfit.id).limit(10).all()
    purchases = db.query(PurchaseHistoryEntry).filter(PurchaseHistoryEntry.owner_id == user.id).order_by(PurchaseHistoryEntry.created_at.desc(), PurchaseHistoryEntry.id).limit(10).all()
    return {"profile": profile,
            "items": [{"id": i.id, "image_url": i.image_url, **item_facts(i)} for i in items],
            "outfits": [{"id": o.id, "occasion": o.occasion, "item_count": len(o.item_ids)} for o in outfits],
            "purchases": [{"id": p.id, "category": p.category, "color": p.color, "price": p.price,
                           "verdict": p.verdict} for p in purchases]}


@router.post("/chat")
def chat(payload: ChatRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    profile = StyleProfileAgent(db).run(user_id=user.id, include_narrative=False)
    profile.pop("narrative", None)
    facts = {"question": payload.message, "previous_questions": payload.previous_questions,
             "history": [h.model_dump() for h in payload.history] or [
                 {"role": "user", "content": q} for q in payload.previous_questions],
             "profile": profile, "topic": payload.topic, "wardrobe_only": payload.wardrobe_only}
    evidence = [{"label": "Ton dressing", "detail": f"{profile['wardrobe_size']} pièces enregistrées"}]
    wardrobe = db.query(ClothingItem).filter(ClothingItem.owner_id == user.id).order_by(ClothingItem.created_at.desc(), ClothingItem.id).limit(40).all()
    selected_item = None
    decision = None
    if payload.topic == "item":
        item = db.query(ClothingItem).filter(ClothingItem.id == payload.record_id, ClothingItem.owner_id == user.id).first()
        if item is None:
            raise HTTPException(404, "Choisis une pièce de ton dressing.")
        selected_item = item
        if all(i.id != item.id for i in wardrobe):
            wardrobe.append(item)
        evidence.append({"label": "Pièce sélectionnée", "detail": ", ".join(filter(None, [item.category, *(item.colors or [])]))})
    elif payload.topic == "outfit":
        outfit = db.query(Outfit).filter(Outfit.id == payload.record_id, Outfit.owner_id == user.id).first()
        if outfit is None:
            raise HTTPException(404, "Choisis une tenue enregistrée dans Idées de looks.")
        pieces = db.query(ClothingItem).filter(ClothingItem.owner_id == user.id, ClothingItem.id.in_(outfit.item_ids)).all()
        if len(pieces) != len(set(outfit.item_ids)):
            raise HTTPException(409, "Cette tenue contient une pièce qui n’est plus disponible. Génère une nouvelle tenue.")
        by_id = {i.id: i for i in pieces}
        known_ids = {i.id for i in wardrobe}
        wardrobe.extend(i for i in pieces if i.id not in known_ids)
        facts["outfit"] = {"items": [item_facts(by_id[i]) for i in outfit.item_ids],
                           "context": {"occasion": outfit.occasion},
                           "favorite_styles": profile["favorite_styles"], "relevance_score": outfit.relevance_score}
        evidence.append({"label": "Tenue enregistrée", "detail": f"{len(pieces)} pièces · {outfit.occasion or 'sans occasion précisée'}"})
    elif payload.topic == "purchase":
        purchase = db.query(PurchaseHistoryEntry).filter(PurchaseHistoryEntry.id == payload.record_id, PurchaseHistoryEntry.owner_id == user.id).first()
        if purchase is None:
            raise HTTPException(404, "Choisis un achat déjà analysé.")
        result = purchase.result or {}
        facts["purchase"] = {key: result.get(key) for key in ("explanation", "duplicates", "outfits_unlocked")}
        facts["purchase"].update(verdict=purchase.verdict, score=purchase.score, price=purchase.price,
                                 has_wardrobe_evidence=bool(result.get("outfit_examples")))
        facts["purchase"]["duplicates"] = [{"category": d.get("category"), "similarity": d.get("similarity")}
                                            for d in (result.get("duplicates") or [])]
        decision = {"verdict": purchase.verdict, "score": purchase.score,
                    "label": {"recommended": "Recommandé", "think_twice": "À réfléchir", "not_recommended": "Non recommandé"}.get(purchase.verdict, purchase.verdict),
                    "rationale": result.get("explanation", "")}
        evidence.append({"label": "Analyse d’achat enregistrée", "detail": f"{purchase.category} · verdict : {purchase.verdict}"})
    references = {f"p{n+1}": item for n, item in enumerate(wardrobe)}
    facts["items"] = [{"ref": ref, **item_facts(item)} for ref, item in references.items()]
    facts["wardrobe_details_complete"] = len(wardrobe) == profile["wardrobe_size"]
    if selected_item is not None:
        facts["selected_item_ref"] = next(ref for ref, item in references.items() if item.id == selected_item.id)
    settings = get_settings()
    chat_settings = settings.model_copy(update={"llm_model": settings.llm_chat_model or settings.llm_model,
                                                "llm_timeout_seconds": settings.llm_chat_timeout_seconds})
    agent = LLMAgent(settings=chat_settings)
    start = monotonic()
    result = agent.run(task="assistant", context=facts,
                       instruction="Réponds à la question précise en français à partir des données réelles du compte.",
                       cache_scope=f"chat:{user.id}:{payload.topic}:{payload.record_id}")
    if not result["explanation"] and agent.last_failure == "rate_limit" and settings.llm_chat_fallback_model and settings.llm_chat_fallback_model != chat_settings.llm_model:
        chat_settings = chat_settings.model_copy(update={"llm_model": settings.llm_chat_fallback_model, "llm_max_retries": 0})
        agent = LLMAgent(settings=chat_settings)
        result = agent.run(task="assistant", context=facts, instruction="Réponds à la question précise en français à partir des données réelles du compte.",
                           cache_scope=f"chat:{user.id}:{payload.topic}:{payload.record_id}")
    answer = json.loads(result["explanation"]) if result["explanation"] else None

    def public_item(ref: str) -> dict:
        item = references[ref]
        return {"id": str(item.id), "label": " · ".join(filter(None, [item.category, *(item.colors or [])]))}

    ideas = [{"title": idea["title"], "advice": idea["advice"],
              "items": [public_item(ref) for ref in idea["item_refs"]],
              "optional_additions": idea["optional_additions"]} for idea in answer["ideas"]] if answer else []
    return {"status": "success" if answer else "unavailable", "explanation": answer["answer"] if answer else None,
            "ideas": ideas, "follow_up": answer["follow_up"] if answer else "", "decision": decision,
            "evidence": evidence, "model": chat_settings.llm_model,
            "failure_reason": agent.last_failure if not answer else None,
            "elapsed_seconds": round(monotonic() - start, 2)}

import uuid

from fastapi import APIRouter, Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.agents.orchestrator import AgentOrchestrator
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.outfit import Outfit
from app.models.recommendation_feedback import RecommendationFeedback
from app.models.user import User
from app.schemas.outfit import (
    OutfitFeedbackRequest,
    OutfitRead,
    OutfitRecommendationResult,
    OutfitRequest,
)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.post("/outfits", response_model=OutfitRecommendationResult)
def recommend_outfits(
    payload: OutfitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    orchestrator = AgentOrchestrator(db)
    return orchestrator.recommend_outfits(
        user_id=current_user.id,
        occasion=payload.occasion,
        weather=payload.weather,
        season=payload.season,
        city=payload.city,
        request_text=payload.request_text,
    )


@router.get("/outfits", response_model=list[OutfitRead])
def list_outfits(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[Outfit]:
    orchestrator = AgentOrchestrator(db)
    return orchestrator.list_outfits(user_id=current_user.id)


@router.put("/outfits/{outfit_id}/feedback", response_model=OutfitRead)
def submit_outfit_feedback(
    outfit_id: uuid.UUID,
    payload: OutfitFeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Outfit:
    outfit = (
        db.query(Outfit)
        .filter(Outfit.id == outfit_id, Outfit.owner_id == current_user.id)
        .first()
    )
    if outfit is None:
        raise HTTPException(status_code=404, detail="Tenue introuvable")

    feedback = (
        db.query(RecommendationFeedback)
        .filter(
            RecommendationFeedback.outfit_id == outfit.id,
            RecommendationFeedback.owner_id == current_user.id,
        )
        .first()
    )
    if payload.rating is None:
        if feedback is not None:
            db.delete(feedback)
    elif feedback is None:
        db.add(RecommendationFeedback(
            owner_id=current_user.id, outfit_id=outfit.id, rating=payload.rating
        ))
    else:
        feedback.rating = payload.rating

    if payload.rating == "worn":
        from app.agents.metadata_agent import MetadataAgent

        metadata = MetadataAgent(db)
        for item_id in outfit.item_ids:
            metadata.log_worn(user_id=current_user.id, item_id=item_id)

    db.commit()
    db.refresh(outfit)
    return outfit

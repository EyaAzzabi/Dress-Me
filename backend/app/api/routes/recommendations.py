from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.orchestrator import AgentOrchestrator
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.outfit import OutfitRequest

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.post("/outfits")
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
    )

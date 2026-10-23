from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.workflow_service import AgentWorkflowService
from app.agents.llm_agent import LLMConfigurationError
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.outfit import Outfit
from app.models.user import User
from app.schemas.outfit import OutfitRead, OutfitRecommendationResult, OutfitRequest

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.post("/outfits", response_model=OutfitRecommendationResult)
def recommend_outfits(
    payload: OutfitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    workflow_service = AgentWorkflowService(db)
    try:
        return workflow_service.recommend_outfits(
            user_id=current_user.id,
            occasion=payload.occasion,
            weather=payload.weather,
            season=payload.season,
            city=payload.city,
        )
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/outfits", response_model=list[OutfitRead])
def list_outfits(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[Outfit]:
    workflow_service = AgentWorkflowService(db)
    return workflow_service.list_outfits(user_id=current_user.id)

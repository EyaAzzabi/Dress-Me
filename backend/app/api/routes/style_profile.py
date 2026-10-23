from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.llm_agent import LLMConfigurationError
from app.agents.workflow_service import AgentWorkflowService
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User

router = APIRouter(prefix="/style-profile", tags=["style-profile"])


@router.get("/")
def get_style_profile(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    workflow_service = AgentWorkflowService(db)
    try:
        return workflow_service.get_style_profile(user_id=current_user.id)
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

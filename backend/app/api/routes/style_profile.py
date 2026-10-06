from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.orchestrator import AgentOrchestrator
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User

router = APIRouter(prefix="/style-profile", tags=["style-profile"])


@router.get("/")
def get_style_profile(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    orchestrator = AgentOrchestrator(db)
    return orchestrator.get_style_profile(user_id=current_user.id)

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.style_profile_agent import StyleProfileAgent
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User

router = APIRouter(prefix="/style-profile", tags=["style-profile"])


@router.get("/")
def get_style_profile(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    agent = StyleProfileAgent()
    return agent.run(user_id=current_user.id)

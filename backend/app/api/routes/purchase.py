from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.orchestrator import AgentOrchestrator
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.outfit import PurchaseCheckRequest, PurchaseCheckResult

router = APIRouter(prefix="/purchase", tags=["purchase"])


@router.post("/check", response_model=PurchaseCheckResult)
def check_purchase(
    payload: PurchaseCheckRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    orchestrator = AgentOrchestrator(db)
    return orchestrator.evaluate_purchase(user_id=current_user.id, image_url=payload.image_url)

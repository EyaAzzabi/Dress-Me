from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.tryon_agent import TryOnAgent
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.clothing_item import ClothingItem
from app.models.user import User
from app.schemas.tryon import AvatarSet, TryOnRequest, TryOnResult

router = APIRouter(prefix="/tryon", tags=["tryon"])
tryon_agent = TryOnAgent()


@router.put("/avatar", response_model=AvatarSet)
def set_avatar(
    payload: AvatarSet,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Sets the user's reference photo for virtual try-on. Upload the raw photo via
    POST /wardrobe/upload first (same storage path wardrobe items use) to get the
    image_url this expects."""
    current_user.avatar_photo_url = payload.image_url
    db.commit()
    return {"image_url": payload.image_url}


@router.post("/", response_model=TryOnResult)
def try_on_garment(
    payload: TryOnRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not current_user.avatar_photo_url:
        raise HTTPException(
            status_code=422, detail="Set your avatar photo first (PUT /tryon/avatar)."
        )
    if not tryon_agent.is_configured():
        raise HTTPException(status_code=503, detail="Virtual try-on isn't configured on this server.")

    item = (
        db.query(ClothingItem)
        .filter(ClothingItem.id == payload.garment_item_id, ClothingItem.owner_id == current_user.id)
        .first()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="That item isn't in your wardrobe.")

    try:
        return tryon_agent.run(person_image_url=current_user.avatar_photo_url, garment_image_url=item.image_url)
    except (RuntimeError, TimeoutError) as exc:
        # Upstream (Replicate) failure — e.g. no billing set up, generation failed, or
        # timed out — not a bug in this request, so a 502 with the real reason beats a
        # generic 500.
        raise HTTPException(status_code=502, detail=str(exc))

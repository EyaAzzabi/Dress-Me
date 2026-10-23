import logging
import re

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
logger = logging.getLogger(__name__)


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

    ids: list[uuid.UUID] = []
    if payload.garment_item_ids:
        ids.extend(payload.garment_item_ids)
    elif payload.garment_item_id:
        ids.append(payload.garment_item_id)

    if not ids:
        raise HTTPException(status_code=400, detail="Veuillez sélectionner au moins un vêtement.")

    items = (
        db.query(ClothingItem)
        .filter(ClothingItem.id.in_(ids), ClothingItem.owner_id == current_user.id)
        .all()
    )
    if not items:
        raise HTTPException(status_code=404, detail="Aucune des pièces sélectionnées n'a été trouvée dans votre dressing.")

    from app.agents.tryon_agent import GARMENT_CATEGORY, garments_for_outfit

    try:
        if len(items) == 1:
            item = items[0]
            category = GARMENT_CATEGORY.get(item.category, "upper_body") if item.category else "upper_body"
            return tryon_agent.run(
                person_image_url=current_user.avatar_photo_url,
                garment_image_url=item.image_url,
                category=category,
            )
        else:
            garments = garments_for_outfit(items)
            if not garments:
                garments = [
                    (it.image_url, GARMENT_CATEGORY.get(it.category, "upper_body"))
                    for it in items
                ]
            return tryon_agent.run_outfit(
                person_image_url=current_user.avatar_photo_url,
                garments=garments,
            )
    except (RuntimeError, TimeoutError) as exc:
        # Upstream (Replicate / HF) failure
        detail = re.sub(r"https?://\S+", "[URL]", str(exc))
        for secret in (
            tryon_agent.settings.hf_token,
            tryon_agent.settings.replicate_api_token,
        ):
            if secret:
                detail = detail.replace(secret, "[REDACTED]")
        logger.warning(
            "tryon_provider_failure provider=%s error_type=%s detail=%s",
            tryon_agent.provider,
            type(exc).__name__,
            detail[:500],
        )
        raise HTTPException(status_code=502, detail=str(exc))

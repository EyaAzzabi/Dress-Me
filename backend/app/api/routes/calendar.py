import hashlib
from datetime import date

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.agents.tryon_agent import TryOnAgent, garments_for_outfit
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.clothing_item import ClothingItem
from app.models.scheduled_outfit import ScheduledOutfit
from app.models.user import User
from app.schemas.calendar import ScheduledOutfitCreate, ScheduledOutfitRead
from app.services.storage import StorageService

router = APIRouter(prefix="/calendar", tags=["calendar"])
tryon_agent = TryOnAgent()
storage_service = StorageService()


def _render_signature(item_ids, avatar_url: str | None) -> str:
    """Identifies what a render was made from: this exact set of items on this exact avatar photo."""
    payload = (avatar_url or "") + "|" + ",".join(sorted(str(i) for i in item_ids))
    return hashlib.sha256(payload.encode()).hexdigest()


def _resolve(scheduled: ScheduledOutfit, db: Session) -> dict:
    items = (
        db.query(ClothingItem)
        .filter(ClothingItem.id.in_(scheduled.item_ids), ClothingItem.owner_id == scheduled.owner_id)
        .all()
    )
    fresh = scheduled.render_signature == _render_signature(
        scheduled.item_ids, scheduled.owner.avatar_photo_url
    )
    return {
        "date": scheduled.date,
        "item_ids": scheduled.item_ids,
        "items": items,
        "render_image_url": scheduled.render_image_url if fresh else None,
    }


@router.put("/{day}", response_model=ScheduledOutfitRead)
def plan_outfit(
    day: date,
    payload: ScheduledOutfitCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    owned_count = (
        db.query(ClothingItem)
        .filter(ClothingItem.id.in_(payload.item_ids), ClothingItem.owner_id == current_user.id)
        .count()
    )
    if owned_count != len(set(payload.item_ids)):
        raise HTTPException(status_code=404, detail="One or more items don't belong to your wardrobe.")

    scheduled = (
        db.query(ScheduledOutfit)
        .filter(ScheduledOutfit.owner_id == current_user.id, ScheduledOutfit.date == day)
        .first()
    )
    if scheduled is None:
        scheduled = ScheduledOutfit(owner_id=current_user.id, date=day, item_ids=payload.item_ids)
        db.add(scheduled)
    else:
        scheduled.item_ids = payload.item_ids  # re-planning a day replaces it, not stacks it
        scheduled.render_image_url = scheduled.render_signature = None  # the old render shows other clothes
    db.commit()
    db.refresh(scheduled)
    return _resolve(scheduled, db)


@router.post("/{day}/render", response_model=ScheduledOutfitRead)
def render_outfit_on_avatar(
    day: date, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    """Renders the user's avatar wearing that day's planned outfit (virtual try-on, one
    paid call per garment — so on demand, not automatic) and keeps the picture so the
    calendar can show it. Re-asking for an unchanged outfit returns the stored render."""
    scheduled = (
        db.query(ScheduledOutfit)
        .filter(ScheduledOutfit.owner_id == current_user.id, ScheduledOutfit.date == day)
        .first()
    )
    if scheduled is None:
        raise HTTPException(status_code=404, detail="Nothing planned for this day.")
    if not current_user.avatar_photo_url:
        raise HTTPException(status_code=422, detail="Set your avatar photo first (PUT /tryon/avatar).")

    signature = _render_signature(scheduled.item_ids, current_user.avatar_photo_url)
    if scheduled.render_image_url and scheduled.render_signature == signature:
        return _resolve(scheduled, db)

    if not tryon_agent.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Virtual try-on isn't configured on this server (storage, or Replicate credentials).",
        )
    if not storage_service.is_configured():
        raise HTTPException(status_code=503, detail="Image storage isn't configured on this server.")

    items = (
        db.query(ClothingItem)
        .filter(ClothingItem.id.in_(scheduled.item_ids), ClothingItem.owner_id == current_user.id)
        .all()
    )
    try:
        generated = tryon_agent.run_outfit(
            person_image_url=current_user.avatar_photo_url, garments=garments_for_outfit(items)
        )
        stored_url = generated["result_image_url"]
        if not generated.get("persisted"):
            # Replicate's output URL expires within about an hour, so keep our own copy.
            image = httpx.get(stored_url, timeout=30.0, follow_redirects=True)
            image.raise_for_status()
            stored_url = storage_service.upload_image(
                image.content, image.headers.get("content-type", "image/jpeg").split(";")[0]
            )
    except (RuntimeError, TimeoutError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    scheduled.render_image_url = stored_url
    scheduled.render_signature = signature
    db.commit()
    db.refresh(scheduled)
    return _resolve(scheduled, db)


@router.get("/{day}", response_model=ScheduledOutfitRead)
def get_planned_outfit(
    day: date, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    scheduled = (
        db.query(ScheduledOutfit)
        .filter(ScheduledOutfit.owner_id == current_user.id, ScheduledOutfit.date == day)
        .first()
    )
    if scheduled is None:
        raise HTTPException(status_code=404, detail="Nothing planned for this day.")
    return _resolve(scheduled, db)


@router.get("/", response_model=list[ScheduledOutfitRead])
def list_planned_outfits(
    start: date = Query(..., description="Inclusive range start, e.g. the first day of a month"),
    end: date = Query(..., description="Inclusive range end, e.g. the last day of a month"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    if end < start:
        raise HTTPException(status_code=422, detail="end must not be before start.")
    scheduled_outfits = (
        db.query(ScheduledOutfit)
        .filter(
            ScheduledOutfit.owner_id == current_user.id,
            ScheduledOutfit.date >= start,
            ScheduledOutfit.date <= end,
        )
        .order_by(ScheduledOutfit.date)
        .all()
    )
    return [_resolve(s, db) for s in scheduled_outfits]


@router.delete("/{day}", status_code=204)
def unplan_outfit(
    day: date, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    scheduled = (
        db.query(ScheduledOutfit)
        .filter(ScheduledOutfit.owner_id == current_user.id, ScheduledOutfit.date == day)
        .first()
    )
    if scheduled:
        db.delete(scheduled)
        db.commit()

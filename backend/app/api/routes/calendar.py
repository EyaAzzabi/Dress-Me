from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.clothing_item import ClothingItem
from app.models.scheduled_outfit import ScheduledOutfit
from app.models.user import User
from app.schemas.calendar import ScheduledOutfitCreate, ScheduledOutfitRead

router = APIRouter(prefix="/calendar", tags=["calendar"])


def _resolve(scheduled: ScheduledOutfit, db: Session) -> dict:
    items = (
        db.query(ClothingItem)
        .filter(ClothingItem.id.in_(scheduled.item_ids), ClothingItem.owner_id == scheduled.owner_id)
        .all()
    )
    return {"date": scheduled.date, "item_ids": scheduled.item_ids, "items": items}


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

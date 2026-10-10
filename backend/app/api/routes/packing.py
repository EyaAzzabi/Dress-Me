import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.orchestrator import AgentOrchestrator
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.clothing_item import ClothingItem
from app.models.packing_list import PackingList
from app.models.user import User
from app.schemas.packing import PackingItemCheck, PackingListCreate, PackingListRead

router = APIRouter(prefix="/packing", tags=["packing"])


def _resolve(packing_list: PackingList, db: Session) -> dict:
    items = (
        db.query(ClothingItem)
        .filter(ClothingItem.id.in_(packing_list.item_ids), ClothingItem.owner_id == packing_list.owner_id)
        .all()
    )
    return {
        "id": packing_list.id,
        "destination": packing_list.destination,
        "duration_days": packing_list.duration_days,
        "trip_type": packing_list.trip_type,
        "start_date": packing_list.start_date,
        "season": packing_list.season,
        "item_ids": packing_list.item_ids,
        "checked_item_ids": packing_list.checked_item_ids,
        "items": items,
    }


@router.post("/", response_model=PackingListRead, status_code=201)
def create_packing_list(
    payload: PackingListCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if payload.duration_days < 1:
        raise HTTPException(status_code=422, detail="duration_days must be at least 1.")

    packing_list = AgentOrchestrator(db).plan_trip(
        user_id=current_user.id,
        destination=payload.destination,
        duration_days=payload.duration_days,
        trip_type=payload.trip_type,
        start_date=payload.start_date,
    )
    return _resolve(packing_list, db)


@router.get("/", response_model=list[PackingListRead])
def list_packing_lists(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[dict]:
    packing_lists = (
        db.query(PackingList)
        .filter(PackingList.owner_id == current_user.id)
        .order_by(PackingList.created_at.desc())
        .all()
    )
    return [_resolve(p, db) for p in packing_lists]


@router.get("/{packing_list_id}", response_model=PackingListRead)
def get_packing_list(
    packing_list_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    packing_list = (
        db.query(PackingList)
        .filter(PackingList.id == packing_list_id, PackingList.owner_id == current_user.id)
        .first()
    )
    if packing_list is None:
        raise HTTPException(status_code=404, detail="Packing list not found.")
    return _resolve(packing_list, db)


@router.patch("/{packing_list_id}/check", response_model=PackingListRead)
def check_packing_item(
    packing_list_id: uuid.UUID,
    payload: PackingItemCheck,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    packing_list = (
        db.query(PackingList)
        .filter(PackingList.id == packing_list_id, PackingList.owner_id == current_user.id)
        .first()
    )
    if packing_list is None:
        raise HTTPException(status_code=404, detail="Packing list not found.")
    if payload.item_id not in packing_list.item_ids:
        raise HTTPException(status_code=404, detail="That item isn't in this packing list.")

    checked = set(packing_list.checked_item_ids)
    if payload.checked:
        checked.add(payload.item_id)
    else:
        checked.discard(payload.item_id)
    packing_list.checked_item_ids = list(checked)
    db.commit()
    db.refresh(packing_list)
    return _resolve(packing_list, db)


@router.delete("/{packing_list_id}", status_code=204)
def delete_packing_list(
    packing_list_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    packing_list = (
        db.query(PackingList)
        .filter(PackingList.id == packing_list_id, PackingList.owner_id == current_user.id)
        .first()
    )
    if packing_list:
        db.delete(packing_list)
        db.commit()

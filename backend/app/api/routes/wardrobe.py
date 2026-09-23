from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.clothing_item import ClothingItem
from app.models.user import User
from app.schemas.clothing_item import ClothingItemCreate, ClothingItemRead

router = APIRouter(prefix="/wardrobe", tags=["wardrobe"])


@router.get("/", response_model=list[ClothingItemRead])
def list_items(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[ClothingItem]:
    return (
        db.query(ClothingItem)
        .filter(ClothingItem.owner_id == current_user.id)
        .all()
    )


@router.post("/", response_model=ClothingItemRead, status_code=201)
def add_item(
    payload: ClothingItemCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClothingItem:
    # TODO: run the Vision Agent on payload.image_url to fill in category/colors/style/...
    item = ClothingItem(owner_id=current_user.id, image_url=payload.image_url)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=204)
def remove_item(
    item_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    item = (
        db.query(ClothingItem)
        .filter(ClothingItem.id == item_id, ClothingItem.owner_id == current_user.id)
        .first()
    )
    if item:
        db.delete(item)
        db.commit()

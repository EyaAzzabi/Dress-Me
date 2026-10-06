import uuid

from pydantic import BaseModel

from app.schemas.clothing_item import ClothingItemRead


class PackingListCreate(BaseModel):
    destination: str
    duration_days: int
    trip_type: str  # plage | business | tourisme


class PackingListRead(BaseModel):
    id: uuid.UUID
    destination: str
    duration_days: int
    trip_type: str
    item_ids: list[uuid.UUID]
    checked_item_ids: list[uuid.UUID]
    items: list[ClothingItemRead]

    class Config:
        from_attributes = True


class PackingItemCheck(BaseModel):
    item_id: uuid.UUID
    checked: bool

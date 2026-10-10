import uuid
from datetime import date

from pydantic import BaseModel

from app.schemas.clothing_item import ClothingItemRead


class PackingListCreate(BaseModel):
    destination: str
    duration_days: int
    trip_type: str  # plage | business | tourisme
    start_date: date | None = None  # when given, drives the season and pulls in planned outfits


class PackingListRead(BaseModel):
    id: uuid.UUID
    destination: str
    duration_days: int
    trip_type: str
    start_date: date | None = None
    season: str | None = None
    item_ids: list[uuid.UUID]
    checked_item_ids: list[uuid.UUID]
    items: list[ClothingItemRead]

    class Config:
        from_attributes = True


class PackingItemCheck(BaseModel):
    item_id: uuid.UUID
    checked: bool

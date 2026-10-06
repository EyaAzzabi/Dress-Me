import uuid
from datetime import date

from pydantic import BaseModel

from app.schemas.clothing_item import ClothingItemRead


class ScheduledOutfitCreate(BaseModel):
    item_ids: list[uuid.UUID]


class ScheduledOutfitRead(BaseModel):
    date: date
    item_ids: list[uuid.UUID]
    # Resolved items (not just ids) — the calendar UI needs image_url/category to
    # render a thumbnail per planned day without a second round-trip per item.
    items: list[ClothingItemRead]

    class Config:
        from_attributes = True

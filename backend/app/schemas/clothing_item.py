import uuid
from datetime import datetime

from pydantic import BaseModel


class ClothingItemCreate(BaseModel):
    image_url: str


class ClothingItemRead(BaseModel):
    id: uuid.UUID
    image_url: str
    category: str | None = None
    colors: list[str] | None = None
    style: str | None = None
    season: str | None = None
    pattern: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True

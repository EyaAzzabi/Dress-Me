import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

# Same vocabulary the Vision Agent suggests (app/ml/vision_model.py SEASON_PROMPTS), plus
# "toutes_saisons" which only a user can pick (a model can't tell from a photo).
Season = Literal["ete", "hiver", "mi_saison", "toutes_saisons"]
# The categories the Vision Agent can output (minus "hors_perimetre", which is a rejection).
Category = Literal["haut", "bas", "robe", "veste", "chaussures", "sac", "accessoire"]


class ClothingItemCreate(BaseModel):
    image_url: str
    # Optional. A single product-style photo doesn't reliably show fabric weight/sleeve
    # length, so a user-provided value always wins; the Vision Agent's suggestion is only
    # used when this is omitted and the model was confident (see app/ml/vision_model.py).
    season: Season | None = None
    # The owner's own answer when the Vision Agent wasn't sure of the category (see the
    # 422 "low_category_confidence" from POST /wardrobe/) — trusted over the model.
    category: Category | None = None


class ClothingItemUpdate(BaseModel):
    """Owner corrections to what the Vision Agent guessed — only the fields sent change."""

    category: str | None = None
    colors: list[str] | None = None
    style: str | None = None
    season: Season | None = None
    pattern: str | None = None


class ClothingItemRead(BaseModel):
    id: uuid.UUID
    image_url: str
    category: str | None = None
    colors: list[str] | None = None
    style: str | None = None
    season: str | None = None
    season_source: str | None = None
    pattern: str | None = None
    attribute_confidence: dict[str, float] | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class ItemUsage(BaseModel):
    item_id: uuid.UUID
    wear_count: int
    last_worn: date


class WornPayload(BaseModel):
    day: date | None = None  # defaults to today

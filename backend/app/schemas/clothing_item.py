import uuid
from datetime import datetime

from pydantic import BaseModel


class ClothingItemCreate(BaseModel):
    image_url: str
    # Not inferred by the Vision Agent — a single product-style photo doesn't reliably
    # show fabric weight/sleeve length, the actual visual cues for season (see
    # app/ml/vision_model.py's docstring on what it does and doesn't infer). Optional,
    # user-provided ground truth beats a fabricated guess.
    season: str | None = None


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

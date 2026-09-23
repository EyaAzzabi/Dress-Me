import uuid

from pydantic import BaseModel


class OutfitRequest(BaseModel):
    occasion: str | None = None
    weather: str | None = None
    season: str | None = None


class OutfitRead(BaseModel):
    id: uuid.UUID
    item_ids: list[uuid.UUID]
    occasion: str | None = None
    relevance_score: float | None = None
    explanation: str | None = None

    class Config:
        from_attributes = True


class PurchaseCheckRequest(BaseModel):
    image_url: str


class PurchaseCheckResult(BaseModel):
    verdict: str  # recommended | think_twice | not_recommended
    compatibility_score: float
    similar_item_ids: list[uuid.UUID] = []
    explanation: str

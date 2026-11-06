import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RLHFFeedbackRequest(BaseModel):
    outfit_id: uuid.UUID
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=500)
    items_liked: list[dict] = Field(default_factory=list, max_length=20)
    items_disliked: list[dict] = Field(default_factory=list, max_length=20)
    occasion_matched: bool | None = None
    seasonal_appropriate: bool | None = None


class RLHFFeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    outfit_id: uuid.UUID
    rating: int
    created_at: datetime
    is_new: bool
    total_feedbacks_by_user: int
    pairs_available: int


class RLHFStatsDayPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: str
    avg_rating: float
    count: int


class RLHFStats(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_feedbacks: int
    average_rating: float
    rating_distribution: dict[int, int]
    recent_feedbacks: list[dict]
    most_liked_items: list[dict]
    most_disliked_items: list[dict]
    avg_rating_trend: list[RLHFStatsDayPoint]
    most_liked_occasions: dict[str, float]
    readiness_for_training: dict

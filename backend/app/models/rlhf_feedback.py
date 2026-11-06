import json
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator, Uuid

from app.db.base import Base


class JSONListTypeDecorator(TypeDecorator):
    """Stores a list[dict] as a JSON string — portable across all DB backends."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return "[]"
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return []
        return json.loads(value)


class RLHFFeedback(Base):
    __tablename__ = "rlhf_feedback"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    outfit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("outfits.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    items_liked: Mapped[list] = mapped_column(JSONListTypeDecorator, nullable=False, default=list, server_default="[]")
    items_disliked: Mapped[list] = mapped_column(JSONListTypeDecorator, nullable=False, default=list, server_default="[]")
    occasion_matched: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    seasonal_appropriate: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_rlhf_feedback_rating"),
        Index("idx_rlhf_user_created", "user_id", "created_at"),
        Index("idx_rlhf_outfit_rating", "outfit_id", "rating"),
        # NO UniqueConstraint on (user_id, outfit_id) — FIX-5
    )

import json
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator, Uuid

from app.db.base import Base


class JSONUUIDList(TypeDecorator):
    """Stores a list of UUIDs as a JSON string — portable across all DB backends."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps([str(v) for v in value])

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return [uuid.UUID(v) for v in json.loads(value)]


class Outfit(Base):
    __tablename__ = "outfits"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)

    item_ids: Mapped[list[uuid.UUID]] = mapped_column(JSONUUIDList, nullable=False)
    occasion: Mapped[str | None] = mapped_column(String(100))
    relevance_score: Mapped[float | None] = mapped_column(Float)
    explanation: Mapped[str | None] = mapped_column(String(2048))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="outfits")

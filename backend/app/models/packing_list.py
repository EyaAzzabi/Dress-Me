import json
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
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


class PackingList(Base):
    """A suggested packing list for a trip (PackingAgent generates item_ids from the
    wardrobe; checked_item_ids tracks the user's own checklist progress, a subset of
    item_ids). Kept separate from Outfit/ScheduledOutfit — a packing list isn't one
    outfit, it's a pool of items for the whole trip."""

    __tablename__ = "packing_lists"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)

    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    trip_type: Mapped[str] = mapped_column(String(50), nullable=False)  # plage | business | tourisme

    item_ids: Mapped[list[uuid.UUID]] = mapped_column(JSONUUIDList, nullable=False)
    checked_item_ids: Mapped[list[uuid.UUID]] = mapped_column(JSONUUIDList, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="packing_lists")

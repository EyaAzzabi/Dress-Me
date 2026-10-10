import json
import uuid
from datetime import date as date_type
from datetime import datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, UniqueConstraint, func
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


class ScheduledOutfit(Base):
    """One planned outfit for one calendar day. Stores item_ids directly (like
    Outfit does) rather than referencing a generated Outfit row — a planned day's
    outfit may be hand-picked from the wardrobe, not one of RecommendationAgent's
    suggestions. One row per (owner, date); re-planning a day replaces it rather
    than stacking duplicates (see the unique constraint and the route's upsert)."""

    __tablename__ = "scheduled_outfits"
    __table_args__ = (UniqueConstraint("owner_id", "date", name="uq_scheduled_outfit_owner_date"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)

    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    item_ids: Mapped[list[uuid.UUID]] = mapped_column(JSONUUIDList, nullable=False)

    # "My avatar wearing this outfit" — a virtual try-on render, stored in our own
    # storage (Replicate's URLs expire). render_signature is a hash of the items + the
    # avatar photo it was made from; when either changes the render is stale and hidden.
    render_image_url: Mapped[str | None] = mapped_column(String(1024))
    render_signature: Mapped[str | None] = mapped_column(String(64))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner = relationship("User", back_populates="scheduled_outfits")

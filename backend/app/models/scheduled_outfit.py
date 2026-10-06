import uuid
from datetime import date as date_type
from datetime import datetime

from sqlalchemy import Date, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ScheduledOutfit(Base):
    """One planned outfit for one calendar day. Stores item_ids directly (like
    Outfit does) rather than referencing a generated Outfit row — a planned day's
    outfit may be hand-picked from the wardrobe, not one of RecommendationAgent's
    suggestions. One row per (owner, date); re-planning a day replaces it rather
    than stacking duplicates (see the unique constraint and the route's upsert)."""

    __tablename__ = "scheduled_outfits"
    __table_args__ = (UniqueConstraint("owner_id", "date", name="uq_scheduled_outfit_owner_date"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    item_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner = relationship("User", back_populates="scheduled_outfits")

import uuid
from datetime import date as date_type

from sqlalchemy import Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


class WearLog(Base):
    """"I wore this item on this day" — the explicit counterpart of the calendar, for
    outfits that were never planned. One row per (item, day), so marking it twice or
    planning it *and* marking it counts once (see MetadataAgent.usage_history)."""

    __tablename__ = "wear_logs"
    __table_args__ = (UniqueConstraint("item_id", "date", name="uq_wear_log_item_date"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("clothing_items.id"), nullable=False)
    date: Mapped[date_type] = mapped_column(Date, nullable=False)

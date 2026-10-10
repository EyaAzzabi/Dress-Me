import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


class WishlistItem(Base):
    """A Tunisian catalog product the user saved from the purchase check. The price at
    save time is kept so the live store price can reveal a price drop later."""

    __tablename__ = "wishlist_items"
    __table_args__ = (UniqueConstraint("owner_id", "item_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    item_key: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(128))
    category: Mapped[str | None] = mapped_column(String(50))
    image_url: Mapped[str | None] = mapped_column(String(1024))
    saved_price: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

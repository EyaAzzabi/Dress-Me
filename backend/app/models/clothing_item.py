import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ClothingItem(Base):
    __tablename__ = "clothing_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    image_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))  # top, bottom, shoes, ...
    colors: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    style: Mapped[str | None] = mapped_column(String(100))  # casual, formal, sport, ...
    season: Mapped[str | None] = mapped_column(String(50))
    pattern: Mapped[str | None] = mapped_column(String(100))
    embedding_id: Mapped[str | None] = mapped_column(String(64))  # id in the Pinecone vector store

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="clothing_items")

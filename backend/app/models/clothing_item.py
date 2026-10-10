import json
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator, Uuid

from app.db.base import Base


class JSONList(TypeDecorator):
    """Stores a Python list as a JSON string — portable across all DB backends."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps([str(v) for v in value])

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return json.loads(value)


class JSONVector(TypeDecorator):
    """Stores a float vector (e.g. a 512-d FashionCLIP embedding) as a JSON string."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps([float(v) for v in value])

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return json.loads(value)


class ClothingItem(Base):
    __tablename__ = "clothing_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)

    image_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))  # top, bottom, shoes, ...
    colors: Mapped[list[str] | None] = mapped_column(JSONList)
    style: Mapped[str | None] = mapped_column(String(100))  # casual, formal, sport, ...
    season: Mapped[str | None] = mapped_column(String(50))
    pattern: Mapped[str | None] = mapped_column(String(100))
    embedding_id: Mapped[str | None] = mapped_column(String(64))  # id in the Pinecone vector store
    # Local copy of the FashionCLIP embedding — the similarity-search fallback when
    # Pinecone isn't configured (see app/db/vector_store.py).
    embedding: Mapped[list[float] | None] = mapped_column(JSONVector)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="clothing_items")

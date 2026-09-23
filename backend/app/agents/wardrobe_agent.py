import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.agents.base import BaseAgent
from app.models.clothing_item import ClothingItem


class WardrobeAgent(BaseAgent):
    """Manages the digital wardrobe: add/remove items, organize, search, usage history."""

    name = "wardrobe_agent"

    def __init__(self, db: Session):
        self.db = db

    def run(self, *, user_id: uuid.UUID, **kwargs: Any) -> dict[str, Any]:
        items = (
            self.db.query(ClothingItem)
            .filter(ClothingItem.owner_id == user_id)
            .all()
        )
        return {"items": items}

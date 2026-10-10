import uuid
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.agents.base import BaseAgent
from app.db import vector_store
from app.models.clothing_item import ClothingItem
from app.models.scheduled_outfit import ScheduledOutfit
from app.models.wear_log import WearLog
from app.services.seasons import season_compatible

# Fields an owner may correct after the Vision Agent's guess. season_source is derived.
EDITABLE_FIELDS = {"category", "colors", "style", "season", "pattern"}


class MetadataAgent(BaseAgent):
    """Manages the digital wardrobe: add/remove/correct items, search and filter, and
    usage history (derived from the calendar, so there's no second counter to keep in
    sync). The routes stay thin — they authenticate and call this."""

    name = "metadata_agent"

    def __init__(self, db: Session):
        self.db = db

    def run(
        self,
        *,
        user_id: uuid.UUID,
        category: str | None = None,
        season: str | None = None,
        style: str | None = None,
        color: str | None = None,
        query: str | None = None,
        wearable_in: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Lists the owner's items, optionally filtered. `query` is a free-text search
        across category/style/season/pattern/colors. `season` is an exact match on the
        item's label; `wearable_in` keeps what can be worn in that season (items labeled
        toutes_saisons or not labeled at all pass — see seasons.season_compatible)."""
        items = self.db.query(ClothingItem).filter(ClothingItem.owner_id == user_id).all()

        def matches(item: ClothingItem) -> bool:
            if category and (item.category or "").lower() != category.lower():
                return False
            if season and item.season != season:
                return False
            if wearable_in and not season_compatible(item.season, wearable_in):
                return False
            if style and (item.style or "").lower() != style.lower():
                return False
            if color and color.lower() not in [c.lower() for c in item.colors or []]:
                return False
            if query:
                fields = [item.category, item.style, item.season, item.pattern, *(item.colors or [])]
                haystack = " ".join(f for f in fields if f).lower()
                return all(term in haystack for term in query.lower().split())
            return True

        return {"items": [item for item in items if matches(item)]}

    def get_item(self, *, user_id: uuid.UUID, item_id: uuid.UUID) -> ClothingItem | None:
        return (
            self.db.query(ClothingItem)
            .filter(ClothingItem.id == item_id, ClothingItem.owner_id == user_id)
            .first()
        )

    def add_item(
        self,
        *,
        user_id: uuid.UUID,
        image_url: str,
        attributes: dict[str, Any],
        season: str | None = None,
        category: str | None = None,
    ) -> ClothingItem:
        """Persists an item from the Vision Agent's output. A user-provided `season`
        wins over the model's suggestion; season_source records which one it was. A
        user-confirmed `category` likewise replaces the model's (and counts as certain)."""
        if category is not None:
            attributes = {
                **attributes,
                "category": category,
                "confidence": {**(attributes.get("confidence") or {}), "category": 1.0},
            }
        item_id = uuid.uuid4()
        # The Pinecone vector id *is* the ClothingItem id — one less id to keep in sync.
        vector_store.upsert_item_embedding(
            item_id, attributes["embedding"], owner_id=user_id, category=attributes["category"]
        )
        suggested = attributes.get("season")
        item = ClothingItem(
            id=item_id,
            owner_id=user_id,
            image_url=image_url,
            category=attributes["category"],
            colors=attributes["colors"],
            style=attributes["style"],
            pattern=attributes["pattern"],
            season=season or suggested,
            season_source="user" if season else ("vision" if suggested else None),
            attribute_confidence=attributes.get("confidence"),
            embedding_id=str(item_id) if vector_store.is_configured() else None,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_item(
        self, *, user_id: uuid.UUID, item_id: uuid.UUID, changes: dict[str, Any]
    ) -> ClothingItem | None:
        item = self.get_item(user_id=user_id, item_id=item_id)
        if item is None:
            return None
        for field, value in changes.items():
            if field in EDITABLE_FIELDS and value is not None:
                setattr(item, field, value)
        if changes.get("season") is not None:
            item.season_source = "user"
        self.db.commit()
        self.db.refresh(item)
        return item

    def remove_item(self, *, user_id: uuid.UUID, item_id: uuid.UUID) -> bool:
        item = self.get_item(user_id=user_id, item_id=item_id)
        if item is None:
            return False
        vector_store.delete_item_embedding(item.id)
        self.db.query(WearLog).filter(WearLog.item_id == item.id).delete()
        self.db.delete(item)
        self.db.commit()
        return True

    def log_worn(self, *, user_id: uuid.UUID, item_id: uuid.UUID, day: date | None = None) -> bool:
        """Records that the owner wore an item on `day` (default today). Idempotent per
        (item, day). False when the item isn't theirs."""
        if self.get_item(user_id=user_id, item_id=item_id) is None:
            return False
        day = day or date.today()
        exists = (
            self.db.query(WearLog).filter(WearLog.item_id == item_id, WearLog.date == day).first()
        )
        if exists is None:
            self.db.add(WearLog(owner_id=user_id, item_id=item_id, date=day))
            self.db.commit()
        return True

    def usage_history(self, *, user_id: uuid.UUID, today: date | None = None) -> dict[uuid.UUID, dict[str, Any]]:
        """Per item: on how many distinct days it was worn up to `today`, and the most
        recent one. A day counts if the item was in that day's planned outfit (calendar)
        or the owner marked it worn — counted once even if both. Never-worn items are
        absent."""
        today = today or date.today()
        days_by_item: dict[uuid.UUID, set[date]] = {}
        planned = (
            self.db.query(ScheduledOutfit)
            .filter(ScheduledOutfit.owner_id == user_id, ScheduledOutfit.date <= today)
            .all()
        )
        for outfit in planned:
            for item_id in outfit.item_ids:
                days_by_item.setdefault(item_id, set()).add(outfit.date)
        logs = (
            self.db.query(WearLog).filter(WearLog.owner_id == user_id, WearLog.date <= today).all()
        )
        for log in logs:
            days_by_item.setdefault(log.item_id, set()).add(log.date)
        return {
            item_id: {"wear_count": len(days), "last_worn": max(days)}
            for item_id, days in days_by_item.items()
        }

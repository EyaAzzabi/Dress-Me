import math
import uuid
from datetime import date
from typing import Any

from app.agents.base import BaseAgent
from app.models.clothing_item import ClothingItem
from app.services.seasons import season_compatible

# Which wardrobe `style` values fit each trip type — same vocabulary StyleProfileAgent
# already reports (Casual/Formal/Sports/Ethnic/Party/Smart Casual/Travel/Home). Not
# exhaustive by design: if too few items match, _select() falls back to the rest of
# the wardrobe rather than returning a half-empty list.
TRIP_STYLE_PREFERENCE = {
    "plage": {"Casual", "Sports", "Travel"},
    "business": {"Formal", "Smart Casual"},
    "tourisme": {"Casual", "Travel", "Smart Casual"},
}

# How many of each category a trip of `duration_days` needs, as a function of the
# day count — deliberately simple and explainable (re-wear bottoms/shoes, one top per
# day), not a learned model. veste/sac/accessoire are "nice to have, at most a
# couple" rather than scaled by trip length.
def _quantity_targets(duration_days: int, trip_type: str, season: str | None = None) -> dict[str, int]:
    return {
        "haut": duration_days,
        "bas": max(1, math.ceil(duration_days / 2)),
        "chaussures": 2,
        "veste": 0 if trip_type == "plage" or season == "ete" else 1,
        "sac": 1,
        "accessoire": 2,
    }


class PackingAgent(BaseAgent):
    """Suggests a packing list for a trip: picks real wardrobe items per category,
    capped at how many of each category a trip of that length plausibly needs.

    Within a category the order of preference is: pieces already planned in the
    calendar for the trip (always included), then pieces wearable in the trip's season,
    then pieces whose `style` fits the trip type, then pieces worn least / longest ago
    (so the list doesn't always bring the same favorites). Each criterion only
    reorders — if too few items qualify, the rest of the wardrobe fills in rather than
    returning a half-empty list. A heuristic, not a trained model — same philosophy as
    RecommendationAgent's visual-coherence scoring: explainable and grounded in real
    wardrobe data, not fabricated sophistication.
    """

    name = "packing_agent"

    def run(
        self,
        *,
        wardrobe_items: list[ClothingItem],
        duration_days: int,
        trip_type: str,
        season: str | None = None,
        usage: dict[uuid.UUID, dict[str, Any]] | None = None,
        required_item_ids: set[uuid.UUID] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        usage = usage or {}
        required_item_ids = required_item_ids or set()
        preferred_styles = TRIP_STYLE_PREFERENCE.get(trip_type, set())
        targets = _quantity_targets(duration_days, trip_type, season)

        by_category: dict[str, list[ClothingItem]] = {}
        for item in wardrobe_items:
            by_category.setdefault(item.category, []).append(item)

        def rank(item: ClothingItem) -> tuple:
            entry = usage.get(item.id)
            return (
                item.id not in required_item_ids,
                not season_compatible(getattr(item, "season", None), season),
                item.style not in preferred_styles,
                entry["wear_count"] if entry else 0,
                entry["last_worn"] if entry else date.min,
            )

        selected: list[ClothingItem] = []
        for category, candidates in by_category.items():
            required = [c for c in candidates if c.id in required_item_ids]
            quota = max(targets.get(category, 0), len(required))
            if quota <= 0:
                continue
            selected.extend(sorted(candidates, key=rank)[:quota])

        return {"item_ids": [item.id for item in selected]}

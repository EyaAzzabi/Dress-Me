import math
from typing import Any

from app.agents.base import BaseAgent
from app.models.clothing_item import ClothingItem

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
def _quantity_targets(duration_days: int, trip_type: str) -> dict[str, int]:
    return {
        "haut": duration_days,
        "bas": max(1, math.ceil(duration_days / 2)),
        "chaussures": 2,
        "veste": 0 if trip_type == "plage" else 1,
        "sac": 1,
        "accessoire": 2,
    }


class PackingAgent(BaseAgent):
    """Suggests a packing list for a trip: picks real wardrobe items per category,
    preferring ones whose `style` fits the trip type, capped at how many of each
    category a trip of that length plausibly needs. A heuristic, not a trained model
    — same philosophy as RecommendationAgent's visual-coherence scoring: explainable
    and grounded in real wardrobe data, not fabricated sophistication.
    """

    name = "packing_agent"

    def run(
        self, *, wardrobe_items: list[ClothingItem], duration_days: int, trip_type: str, **kwargs: Any
    ) -> dict[str, Any]:
        by_category: dict[str, list[ClothingItem]] = {}
        for item in wardrobe_items:
            by_category.setdefault(item.category, []).append(item)

        preferred_styles = TRIP_STYLE_PREFERENCE.get(trip_type, set())
        targets = _quantity_targets(duration_days, trip_type)

        selected: list[ClothingItem] = []
        for category, target in targets.items():
            if target <= 0:
                continue
            candidates = by_category.get(category, [])
            preferred = [c for c in candidates if c.style in preferred_styles]
            rest = [c for c in candidates if c not in preferred]
            selected.extend((preferred + rest)[:target])

        return {"item_ids": [item.id for item in selected]}

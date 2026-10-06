import uuid
from collections import Counter
from typing import Any

from sqlalchemy.orm import Session

from app.agents.base import BaseAgent
from app.agents.llm_agent import LLMAgent
from app.models.clothing_item import ClothingItem

TOP_N = 3


class StyleProfileAgent(BaseAgent):
    """Learns the user's style profile: favorite styles/colors, wardrobe composition.

    The facts (category/color/style frequency) are computed directly from the
    wardrobe — never left to an LLM to "count", since that's exactly the kind of thing
    an LLM can get subtly wrong for no benefit over real aggregation. The LLM (optional,
    see LLMAgent) only *phrases* those facts into a narrative; with no provider
    configured, the profile is still fully returned, just without the narrative.

    "Frequent occasions" and recommendation-feedback history (also named in the
    original docstring) aren't tracked by any table yet — not fabricated here.
    """

    name = "style_profile_agent"

    def __init__(self, db: Session):
        self.db = db
        self.llm_agent = LLMAgent()

    def run(self, *, user_id: uuid.UUID, **kwargs: Any) -> dict[str, Any]:
        items = self.db.query(ClothingItem).filter(ClothingItem.owner_id == user_id).all()

        if not items:
            return {
                "wardrobe_size": 0,
                "category_counts": {},
                "favorite_colors": [],
                "favorite_styles": [],
                "narrative": None,
            }

        category_counts = Counter(item.category for item in items if item.category)
        color_counts = Counter(color for item in items for color in (item.colors or []))
        style_counts = Counter(item.style for item in items if item.style)

        profile = {
            "wardrobe_size": len(items),
            "category_counts": dict(category_counts),
            "favorite_colors": [color for color, _ in color_counts.most_common(TOP_N)],
            "favorite_styles": [style for style, _ in style_counts.most_common(TOP_N)],
        }

        narrative = self.llm_agent.run(
            context=profile,
            instruction=(
                "In two or three sentences, describe this user's personal style based "
                "only on the wardrobe facts given."
            ),
        )["explanation"]
        profile["narrative"] = narrative
        return profile

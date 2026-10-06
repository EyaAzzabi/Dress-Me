from itertools import product
from typing import Any

import numpy as np

from app.agents.base import BaseAgent
from app.db import vector_store
from app.ml import compatibility_model
from app.models.clothing_item import ClothingItem

# Optional slots greedily filled with the single best-matching item per category, not
# enumerated combinatorially — keeps this O(wardrobe size) instead of exploding with
# every accessory/bag/jacket combination.
OPTIONAL_SLOTS = ["veste", "chaussures", "sac", "accessoire"]


STYLE_MATCH_BONUS = 0.1  # all pieces share the user's #1 favorite style


class RecommendationAgent(BaseAgent):
    """Generates outfits from the wardrobe: compatible combinations, a relevance
    score, and an explanation.

    Scoring has two parts:
    - Visual coherence: mean pairwise compatibility among the outfit's items, scored
      by a model trained on real Polyvore outfit co-occurrence (68,306 outfits — see
      app/ml/compatibility_model.py and ml/notebooks/09_compatibility_model.py).
      Honest result on held-out outfits: AUC 0.674 vs. 0.609 for raw cosine
      similarity — a real but modest improvement, not a dramatic one.
    - Style consistency: a small, explicit bonus when every piece in the outfit
      shares the same `style` label *and* that's the user's own top favorite style
      (from StyleProfileAgent) — rewards dressing like the user actually dresses,
      not just visual similarity, which a photo embedding alone can't tell you.
    """

    name = "recommendation_agent"

    def run(
        self, *, wardrobe_items: list[ClothingItem], occasion: str | None = None,
        favorite_styles: list[str] | None = None, top_k: int = 3, **kwargs: Any,
    ) -> dict[str, Any]:
        top_style = favorite_styles[0] if favorite_styles else None

        by_category: dict[str, list[ClothingItem]] = {}
        for item in wardrobe_items:
            by_category.setdefault(item.category, []).append(item)

        embeddings = vector_store.fetch_embeddings([item.id for item in wardrobe_items])
        if not embeddings:
            return {"outfits": [], "explanation": "No stored embeddings to build outfits from yet."}

        def vec(item: ClothingItem) -> np.ndarray | None:
            values = embeddings.get(str(item.id))
            return np.array(values) if values is not None else None

        bases: list[list[ClothingItem]] = []
        for haut, bas in product(by_category.get("haut", []), by_category.get("bas", [])):
            bases.append([haut, bas])
        for robe in by_category.get("robe", []):
            bases.append([robe])

        candidates = []
        for base in bases:
            base_vecs = [v for item in base if (v := vec(item)) is not None]
            if len(base_vecs) != len(base):
                continue  # an item in this base has no embedding — can't score it fairly

            outfit = list(base)
            outfit_vecs = list(base_vecs)

            for slot in OPTIONAL_SLOTS:
                slot_options = [(item, v) for item in by_category.get(slot, []) if (v := vec(item)) is not None]
                if not slot_options:
                    continue
                def avg_compat_with_base(pair, base_vecs=base_vecs):
                    return np.mean([compatibility_model.pair_compatibility(pair[1], bv) for bv in base_vecs])

                best_item, best_vec = max(slot_options, key=avg_compat_with_base)
                outfit.append(best_item)
                outfit_vecs.append(best_vec)

            visual_score = _mean_pairwise_compatibility(outfit_vecs)
            style_match = _matches_favorite_style(outfit, top_style)
            score = min(1.0, visual_score + (STYLE_MATCH_BONUS if style_match else 0.0))
            candidates.append((outfit, score, style_match))

        candidates.sort(key=lambda c: c[1], reverse=True)
        outfits = [
            {
                "item_ids": [item.id for item in outfit],
                "relevance_score": round(score, 2),
                "explanation": _explain(outfit, score, occasion, style_match, top_style),
            }
            for outfit, score, style_match in candidates[:top_k]
        ]
        return {"outfits": outfits}


def _matches_favorite_style(outfit: list[ClothingItem], top_style: str | None) -> bool:
    if top_style is None:
        return False
    return all(item.style == top_style for item in outfit)


def _mean_pairwise_compatibility(vectors: list[np.ndarray]) -> float:
    if len(vectors) < 2:
        return 1.0
    total, count = 0.0, 0
    for i in range(len(vectors)):
        for j in range(i + 1, len(vectors)):
            total += compatibility_model.pair_compatibility(vectors[i], vectors[j])
            count += 1
    return total / count


def _explain(
    outfit: list[ClothingItem], score: float, occasion: str | None,
    style_match: bool, top_style: str | None,
) -> str:
    pieces = ", ".join(item.category for item in outfit)
    for_occasion = f" for {occasion}" if occasion else ""
    style_note = f" — all in your usual {top_style} style" if style_match else ""

    if score >= 0.8:
        quality = "Strong visual match"
    elif score >= 0.6:
        quality = "Reasonable match"
    else:
        quality = "Loose match"
    return f"{quality} ({pieces}){for_occasion}{style_note}."

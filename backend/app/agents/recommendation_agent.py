import logging
import uuid
from datetime import date, timedelta
from itertools import product
from typing import Any

import numpy as np

from app.agents.base import BaseAgent
from app.core.config import get_settings
from app.db import vector_store
from app.ml import compatibility_model, ranking_model
from app.models.clothing_item import ClothingItem
from app.services import occasions, seasons
from app.services.outfit_constraints import filter_candidates_by_constraints

logger = logging.getLogger(__name__)

# Optional slots greedily filled with the single best-matching item per category, not
# enumerated combinatorially — keeps this O(wardrobe size) instead of exploding with
# every accessory/bag/jacket combination.
OPTIONAL_SLOTS = ["veste", "chaussures", "sac", "accessoire"]


STYLE_MATCH_BONUS = 0.1  # all pieces share the user's #1 favorite style
RECENT_WEAR_DAYS = 3  # a piece worn this recently is less appealing to suggest again
RECENT_WEAR_PENALTY = 0.05  # per recently worn piece in the outfit


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
    - Freshness: a small penalty per piece worn in the last few days (`usage`, from
      MetadataAgent.usage_history), so the same outfit isn't suggested two days running.
    """

    name = "recommendation_agent"

    def run(
        self, *, wardrobe_items: list[ClothingItem], occasion: str | None = None,
        favorite_styles: list[str] | None = None, top_k: int = 3,
        usage: dict[uuid.UUID, dict[str, Any]] | None = None, today: date | None = None,
        season: str | None = None, temperature: float | None = None, weather: str | None = None,
        occasion_category: str | None = None, formality: int | None = None,
        references: dict | None = None, ctx_vec: np.ndarray | None = None,
        llm_agent: Any = None, **kwargs: Any,
    ) -> dict[str, Any]:
        usage = usage or {}
        recent_cutoff = (today or date.today()) - timedelta(days=RECENT_WEAR_DAYS)
        top_style = favorite_styles[0] if favorite_styles else None

        # Resolve the shared context vector for this run. The orchestrator (FEAT-005)
        # computes ctx_vec once before the generate closure and passes it here to avoid
        # double computation (review-F1). When ctx_vec is None (direct calls / tests),
        # derive weather_band from temperature (review-F1/F3 — weather_band is NEVER a
        # kwarg, only derived) and look the vector up. weather_band is always derived
        # so it stays available for the deterministic explanation note below too.
        weather_band = occasions.weather_band(temperature)
        if ctx_vec is None:
            ctx_vec = ranking_model.context_vector(occasion_category, season, weather_band)
        ranking_enabled = get_settings().ranking_enabled
        historical = (references or {}).get("historical", []) if references else []

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
        used_accessories = set()  # Track used accessories for diversity
        used_base_items = set()  # Track used base items (haut/bas/robe) for diversity
        
        for base in bases:
            base_vecs = [v for item in base if (v := vec(item)) is not None]
            if len(base_vecs) != len(base):
                continue  # an item in this base has no embedding — can't score it fairly

            # Skip this base if any item is already heavily used
            # Allow each base item to appear maximum 1 time in top candidates
            if any(item.id in used_base_items for item in base):
                continue

            outfit = list(base)
            outfit_vecs = list(base_vecs)

            for slot in OPTIONAL_SLOTS:
                slot_options = [(item, v) for item in by_category.get(slot, []) if (v := vec(item)) is not None]
                if not slot_options:
                    continue
                
                # Filter out already used accessories to encourage diversity
                available_options = [
                    (item, v) for item, v in slot_options 
                    if item.id not in used_accessories
                ]
                
                # If all accessories already used, reuse them
                if not available_options:
                    available_options = slot_options
                
                def avg_compat_with_base(pair, base_vecs=base_vecs, base=base):
                    item, vec = pair
                    # Pass clothing items and context to compatibility model
                    scores = []
                    for i, base_item in enumerate(base):
                        score = compatibility_model.pair_compatibility(
                            vec, base_vecs[i],
                            item_a=item, item_b=base_item,
                            season=season, occasion=occasion
                        )
                        scores.append(score)
                    return np.mean(scores)

                best_item, best_vec = max(available_options, key=avg_compat_with_base)
                outfit.append(best_item)
                outfit_vecs.append(best_vec)
                used_accessories.add(best_item.id)  # Mark as used

            visual_score = _mean_pairwise_compatibility(outfit_vecs, outfit, season, occasion)
            style_match = _matches_favorite_style(outfit, top_style)
            recent = sum(
                1 for item in outfit
                if item.id in usage and usage[item.id]["last_worn"] > recent_cutoff
            )
            # Contextual features feed the learned ranker (ranking_model.score_outfit);
            # on the fallback path (RANKING_ENABLED=False / artifact absent) they are
            # computed but ignored, so the score is the exact existing heuristic
            # (review-F12). A failure mid-computation ranks this one outfit by the
            # heuristic (non-fatal WARNING) so the other candidates are unaffected.
            try:
                outfit_mean = np.mean(outfit_vecs, axis=0)
                context_fit = float(outfit_mean @ ctx_vec)
                season_compat = sum(
                    1 for it in outfit
                    if seasons.season_compatible(getattr(it, "season", None), season)
                ) / len(outfit)
                history_fit = max(
                    (float(ref["vec"] @ outfit_mean) for ref in historical),
                    default=0.0,
                )
                score = ranking_model.score_outfit(
                    visual=visual_score, context_fit=context_fit,
                    history_fit=history_fit, season_compat=season_compat,
                    style_match=style_match, recent=recent,
                    ranking_enabled=ranking_enabled,
                )
            except Exception:  # noqa: BLE001 — non-fatal: rank this outfit by the heuristic
                logger.warning(
                    "contextual feature computation failed for a candidate; "
                    "ranking it with the heuristic",
                    exc_info=True,
                )
                score = ranking_model.score_outfit(
                    visual=visual_score, style_match=style_match, recent=recent,
                    ranking_enabled=False,
                )
            candidates.append((outfit, score, style_match))
            
            # Mark base items as used for diversity
            for item in base:
                used_base_items.add(item.id)

        candidates.sort(key=lambda c: c[1], reverse=True)
        
        # Apply hard constraints: filter out outfits that violate occasion rules
        candidates = filter_candidates_by_constraints(
            candidates, occasion_category, formality
        )
        diverse_outfits = []
        used_items = set()
        
        for outfit, score, style_match in candidates:
            # Calculate how many items are already used in previous selections
            overlap = sum(1 for item in outfit if item.id in used_items)
            
            # Prefer outfits with less overlap (more diverse)
            if len(diverse_outfits) < top_k:
                diverse_outfits.append((outfit, score, style_match))
                # Mark items as used
                for item in outfit:
                    used_items.add(item.id)
            elif overlap <= 1:  # Allow some overlap but not too much
                # Check if this diverse outfit has a decent score
                if score >= diverse_outfits[-1][1] * 0.85:  # Within 15% of worst selected
                    diverse_outfits[-1] = (outfit, score, style_match)
                    # Update used items
                    for item in outfit:
                        used_items.add(item.id)
        
        outfits = [
            {
                "item_ids": [item.id for item in outfit],
                "relevance_score": round(score, 2),
                "explanation": _build_explanation(
                    llm_agent=llm_agent, outfit=outfit, score=score, occasion=occasion,
                    style_match=style_match, top_style=top_style, season=season,
                    weather=weather, occasion_category=occasion_category,
                    formality=formality, temperature=temperature, weather_band=weather_band,
                    references=references,
                ),
            }
            for outfit, score, style_match in diverse_outfits
        ]
        return {"outfits": outfits}


def _matches_favorite_style(outfit: list[ClothingItem], top_style: str | None) -> bool:
    if top_style is None:
        return False
    return all(item.style == top_style for item in outfit)


def _mean_pairwise_compatibility(vectors: list[np.ndarray], items: list = None, 
                                season: str | None = None, occasion: str | None = None) -> float:
    """Calculate mean pairwise compatibility with contextual features"""
    if len(vectors) < 2:
        return 1.0
    total, count = 0.0, 0
    for i in range(len(vectors)):
        for j in range(i + 1, len(vectors)):
            if items is not None and len(items) == len(vectors):
                # Use contextual compatibility
                compat = compatibility_model.pair_compatibility(
                    vectors[i], vectors[j],
                    item_a=items[i], item_b=items[j],
                    season=season, occasion=occasion
                )
            else:
                # Fallback to basic compatibility
                compat = compatibility_model.pair_compatibility(vectors[i], vectors[j])
            total += compat
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


def _build_explanation(
    *, llm_agent: Any, outfit: list[ClothingItem], score: float, occasion: str | None,
    style_match: bool, top_style: str | None, season: str | None, weather: str | None,
    occasion_category: str | None, formality: int | None, temperature: float | None,
    weather_band: str | None, references: dict | None,
) -> str:
    """Build the per-outfit explanation, truncated to ``Outfit.explanation``'s 2048
    chars (review-F7).

    When an LLM is injected (the orchestrator path with a configured provider) its
    natural-language explanation is used as-is. Otherwise — no LLM injected, provider
    ``none``, or an LLM/network failure — the deterministic template (``_explain``) is
    kept and, on that fallback path only, a single deterministic adjustment note is
    appended when the weather calls for it (review-F7: folded into ``explanation``,
    no new schema column).
    """
    if llm_agent is not None:
        facts = {
            "items": [
                {"category": it.category, "season": getattr(it, "season", None)}
                for it in outfit
            ],
            "scores": {"relevance": round(score, 2)},
            "context": {
                "occasion": occasion,
                "occasion_category": occasion_category,
                "season": season,
                "weather": weather,
                "temperature": temperature,
                "weather_band": weather_band,
                "formality": formality,
            },
            "references": _references_for_llm(references),
        }
        expl = llm_agent.explain_outfit(facts)
        if expl:
            return expl[:2048]
    text = _explain(outfit, score, occasion, style_match, top_style)
    if weather_band == "chaud" and any(
        it.category == "bas" and getattr(it, "season", None) == "hiver" for it in outfit
    ):
        text += " (il fera chaud : remplace le bas par une pièce plus légère)"
    return text[:2048]


def _references_for_llm(references: dict | None) -> dict | None:
    """Project the RAG references into a JSON-serializable structure for the LLM facts.

    The raw historical entries carry numpy ``vec`` arrays the model can't read and
    ``json.dumps`` can't serialize (uuids / dates likewise); this keeps only what a
    phrasing layer needs — item ids, scores, dates, seasons, and catalog names/brands
    — so ``LLMAgent.explain_outfit`` can actually phrase them rather than silently
    falling back to the template on a serialization error.
    """
    if not references:
        return None
    historical = [
        {
            "item_ids": [str(i) for i in ref.get("item_ids", [])],
            "score": ref.get("score"),
            "date": str(ref.get("date")),
            "season": ref.get("season"),
        }
        for ref in references.get("historical", [])
    ]
    catalog = {
        category: [
            {"name": m.get("name"), "brand": m.get("brand"), "category": m.get("category")}
            for m in matches
        ]
        for category, matches in references.get("catalog", {}).items()
    }
    return {"historical": historical, "catalog": catalog}

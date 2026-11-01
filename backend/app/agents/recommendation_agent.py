"""RecommendationAgent — LangGraph StateGraph (ReAct + Stylist/Critic loop).

Architecture
------------
8 nodes:
  analyze_context  -> extract_constraints -> search_candidates -> compose_outfit -> check_rules
  check_rules      -> critic_evaluate  (rules OK)
                   -> replan           (rules NOK, steps < max_steps)
                   -> finalize         (steps >= max_steps)
  critic_evaluate  -> finalize         (approved or max critic iterations)
                   -> replan           (not approved)
  replan           -> check_rules
  finalize         -> END

Every node returns a dict with state updates.
All LLM calls have a deterministic fallback.
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from datetime import date, timedelta
from typing import Any, TypedDict

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)

# Import compatibility_model at module level so tests can patch
# app.agents.recommendation_agent.compatibility_model.pair_compatibility
try:
    from app.ml import compatibility_model  # noqa: F401 — kept for test patchability
except Exception:  # noqa: BLE001
    compatibility_model = None  # type: ignore[assignment]

# Import vector_store at module level so tests can patch
# app.agents.recommendation_agent.vector_store.fetch_embeddings
try:
    from app.db import vector_store  # noqa: F401 — kept for test patchability
except Exception:  # noqa: BLE001
    vector_store = None  # type: ignore[assignment]

# Import outfit_compatibility_transformer at module level (optional dependency)
try:
    from app.ml import outfit_compatibility_transformer as outfit_transformer_module  # noqa: F401
except Exception:  # noqa: BLE001
    outfit_transformer_module = None  # type: ignore[assignment]

# Import preference_reward_model components at module level (optional dependency)
try:
    from app.ml.preference_reward_model import (  # noqa: F401
        PreferenceRewardModel as _PRM,
        load_or_init as _prm_load_or_init,
    )
except Exception:  # noqa: BLE001
    _PRM = None  # type: ignore[assignment]
    _prm_load_or_init = None  # type: ignore[assignment]

# Import preference_dataset at module level (optional dependency)
try:
    from app.ml.preference_dataset import build_preference_pairs as _build_preference_pairs  # noqa: F401
except Exception:  # noqa: BLE001
    _build_preference_pairs = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Formality-to-item-style mapping for constraint filtering
# ---------------------------------------------------------------------------

_FORMALITY_FILTER_RULES = {
    "casual": {"casual", "smart_casual"},
    "smart_casual": {"casual", "smart_casual", "formal"},
    "formal": {"formal", "smart_casual"},
}


def _apply_constraint_filters(
    items: list[Any],
    constraints: dict[str, Any],
    season: str | None = None,
) -> list[Any]:
    """Apply style/formality/season filters to candidates.
    
    Filters applied in order: style → formality → season.
    Each stage falls back to previous stage output if it yields zero results.
    
    Args:
        items: Initial wardrobe candidates (typically already color-filtered).
        constraints: Dict from constraint_parser.parse() with keys:
            colors, styles, occasions, formality, season, notes.
        season: Current season context (may override extracted season).
    
    Returns:
        Filtered items list (never empty — falls back to all items if all filters fail).
    """
    current = items

    # Stage 1: Style filtering
    constraint_styles = constraints.get("styles") or []
    if constraint_styles:
        filtered_by_style = []
        for it in current:
            item_style = getattr(it, "style", None) or ""
            # Match: item style is one of the constraint styles (case-insensitive)
            if any(item_style.lower() == cs.lower() for cs in constraint_styles):
                filtered_by_style.append(it)
        if filtered_by_style:
            current = filtered_by_style
            logger.info("Constraint filtering: %d → %d items (styles=%s)",
                        len(items), len(current), constraint_styles)

    # Stage 2: Formality filtering
    constraint_formality = constraints.get("formality")
    if constraint_formality and constraint_formality in _FORMALITY_FILTER_RULES:
        allowed_styles = _FORMALITY_FILTER_RULES[constraint_formality]
        filtered_by_formality = []
        for it in current:
            item_style = getattr(it, "style", None) or ""
            if item_style.lower() in {s.lower() for s in allowed_styles}:
                filtered_by_formality.append(it)
        if filtered_by_formality:
            current = filtered_by_formality
            logger.info("Constraint filtering: %d → %d items (formality=%s)",
                        len(items), len(current), constraint_formality)

    # Stage 3: Season filtering
    constraint_season = constraints.get("season") or season
    if constraint_season:
        filtered_by_season = []
        for it in current:
            item_season = getattr(it, "season", None) or ""
            if not item_season or item_season.lower() in (constraint_season.lower(), "toutes_saisons"):
                filtered_by_season.append(it)
        if filtered_by_season:
            current = filtered_by_season
            logger.info("Constraint filtering: %d → %d items (season=%s)",
                        len(items), len(current), constraint_season)

    return current if current else items  # Fallback to all items if all filters fail


# ---------------------------------------------------------------------------
# State TypedDict
# ---------------------------------------------------------------------------


class RecommendationState(TypedDict, total=False):
    # Input
    user_id: str
    occasion: Any          # str | None
    occasion_category: Any # str | None
    request_text: Any      # str | None (original user text, not parsed)
    city: Any              # str | None
    season: Any            # str | None
    temperature: Any       # float | None
    weather_band: Any      # str | None
    wardrobe_items: list
    favorite_styles: list
    usage: dict
    feedback_preferences: list
    references: Any
    ctx_vec: Any
    formality: Any
    db: Any
    llm_agent: Any

    # Working
    weather: Any           # str | None
    wardrobe_candidates: list
    style_guidelines: list
    extracted_constraints: Any  # dict from constraint_parser.parse(request_text)
    current_outfit: list
    outfit_rules: dict
    thoughts: list
    actions: list
    observations: list
    steps: int
    max_steps: int

    # Critic
    critic_score: Any
    critic_iterations: int
    max_critic_iterations: int

    # Output accumulator
    all_outfits: list
    final_outfit: Any
    error: Any
    reward_model: Any


# ---------------------------------------------------------------------------
# Node helpers
# ---------------------------------------------------------------------------


def _item_to_dict(item: Any) -> dict:
    """Convert a ClothingItem ORM object to a plain dict for the graph."""
    colors = getattr(item, "colors", None) or []
    if isinstance(colors, str):
        import json as _json
        try:
            colors = _json.loads(colors)
        except Exception:
            colors = [colors]
    return {
        "id": str(getattr(item, "id", "")),
        "category": getattr(item, "category", "") or "",
        "colors": colors,
        "style": getattr(item, "style", "") or "",
        "season": getattr(item, "season", "") or "",
    }


def _weather_band_from_temp(temperature: float | None) -> str | None:
    try:
        from app.services.occasions import weather_band
        return weather_band(temperature)
    except Exception:
        if temperature is None:
            return None
        if temperature < 14:
            return "froid"
        if temperature < 24:
            return "modere"
        return "chaud"


# ---------------------------------------------------------------------------
# Node 1 — analyze_context
# ---------------------------------------------------------------------------


def _node_analyze_context(state: RecommendationState) -> dict:
    from app.agents.recommendation_tools import get_weather
    from app.agents.recommendation_rag import StyleRAG

    updates: dict[str, Any] = {}
    thoughts = list(state.get("thoughts") or [])
    actions = list(state.get("actions") or [])
    observations = list(state.get("observations") or [])

    city = state.get("city")
    weather = state.get("weather")
    temperature = state.get("temperature")
    weather_band = state.get("weather_band")
    occasion = state.get("occasion")
    season = state.get("season")
    db = state.get("db")

    # Fetch weather if city provided and weather not yet known
    if city and not weather:
        result = get_weather(city=city, db=db)
        data = result.get("result") or {}
        temperature = data.get("main", {}).get("temp") or temperature
        desc = (data.get("weather") or [{}])[0].get("description", "")
        weather = f"{temperature}°C, {desc}" if temperature else desc
        weather_band = _weather_band_from_temp(temperature)
        updates["temperature"] = temperature
        updates["weather_band"] = weather_band
        updates["weather"] = weather
        thoughts.append(
            f"Analyse du contexte: occasion={occasion}, météo={weather}, saison={season}"
        )
        actions.append({"tool": "get_weather", "args": {"city": city}})
        observations.append(result)
    else:
        if temperature and not weather_band:
            weather_band = _weather_band_from_temp(temperature)
            updates["weather_band"] = weather_band
        thoughts.append(
            f"Analyse du contexte: occasion={occasion}, météo={weather}, saison={season}"
        )
        actions.append({"tool": "get_weather", "args": {"city": None}})
        observations.append({"tool_name": "get_weather", "result": None,
                              "reasoning": "city not provided", "error": None})

    # Retrieve style guidelines
    rag_query = f"{occasion or ''} {season or ''} {weather_band or ''}".strip()
    try:
        guidelines = StyleRAG().retrieve(rag_query, top_k=3)
    except Exception:
        logger.warning("StyleRAG failed in analyze_context", exc_info=True)
        guidelines = []
    updates["style_guidelines"] = guidelines

    updates["thoughts"] = thoughts
    updates["actions"] = actions
    updates["observations"] = observations
    return updates


# ---------------------------------------------------------------------------
# Node 1.5 — extract_constraints
# ---------------------------------------------------------------------------


def _node_extract_constraints(state: RecommendationState) -> dict:
    """Extract style/color/occasion constraints from request_text."""
    request_text = state.get("request_text")
    constraints: dict[str, Any] = {}

    if request_text:
        try:
            from app.ml.constraint_parser import ConstraintParser
            parser = ConstraintParser()
            constraints = parser.parse(request_text)
            logger.info("Extracted constraints: %s", constraints)
        except Exception as exc:
            logger.warning("Constraint extraction failed: %s", exc, exc_info=True)
            constraints = {
                "colors": [],
                "styles": [],
                "occasions": [],
                "formality": None,
                "season": None,
                "notes": None,
            }
    else:
        constraints = {
            "colors": [],
            "styles": [],
            "occasions": [],
            "formality": None,
            "season": None,
            "notes": None,
        }

    return {"extracted_constraints": constraints}


# ---------------------------------------------------------------------------
# Node 3 — search_candidates (actually node 2, after extraction)
# ---------------------------------------------------------------------------


def _node_search_candidates(state: RecommendationState) -> dict:
    from app.agents.recommendation_tools import filter_wardrobe

    thoughts = list(state.get("thoughts") or [])
    actions = list(state.get("actions") or [])
    observations = list(state.get("observations") or [])

    user_id = state.get("user_id") or ""
    season = state.get("season")
    db = state.get("db")
    wardrobe_items = list(state.get("wardrobe_items") or [])
    extracted_constraints = state.get("extracted_constraints") or {}

    thoughts.append("Recherche des candidats dans la garde-robe")

    items: list[Any] = []

    # If we have a DB session, use filter_wardrobe tool
    if db and user_id:
        result = filter_wardrobe(user_id=user_id, season=season, db=db)
        items = result.get("result") or []
        if not items:
            # Fallback: no season constraint
            result2 = filter_wardrobe(user_id=user_id, db=db)
            items = result2.get("result") or []
        actions.append({"tool": "filter_wardrobe",
                        "args": {"user_id": user_id, "season": season}})
        observations.append(result)
    else:
        # Use wardrobe_items passed directly (orchestrator path)
        items = wardrobe_items
        # Apply season filter heuristically
        if season:
            filtered = [
                it for it in items
                if not getattr(it, "season", None)
                or getattr(it, "season") in (season, "toutes_saisons")
            ]
            items = filtered if filtered else items
        result = {
            "tool_name": "filter_wardrobe",
            "result": items,
            "reasoning": f"Used wardrobe_items directly ({len(items)} items)",
            "error": None,
        }
        actions.append({"tool": "filter_wardrobe",
                        "args": {"from_wardrobe_items": True, "season": season}})
        observations.append(result)

    # Apply color/style preferences based on extracted constraints
    items_before_filter = len(items)
    constraint_colors = extracted_constraints.get("colors") or []

    if constraint_colors:
        # Filter: keep items that have at least one color matching any requested color
        filtered_by_color = []
        for it in items:
            item_colors = getattr(it, "colors", None) or []
            if isinstance(item_colors, str):
                import json as _json
                try:
                    item_colors = _json.loads(item_colors)
                except Exception:
                    item_colors = [item_colors]
            
            # Check if any requested color is in item's colors (case-insensitive substring match)
            has_match = False
            for req_color in constraint_colors:
                for item_color in item_colors:
                    if req_color.lower() in str(item_color).lower():
                        has_match = True
                        break
                if has_match:
                    break
            
            if has_match:
                filtered_by_color.append(it)
        
        # Only use filtered list if we have results, otherwise fall back to all items
        if filtered_by_color:
            items = filtered_by_color
            logger.info("Constraint filtering: %d → %d items (colors=%s)",
                        items_before_filter, len(items), constraint_colors)
        else:
            logger.info("Constraint filtering: no items matched colors=%s, keeping all %d items",
                        constraint_colors, items_before_filter)

    # Apply style/formality/season constraints (if extraction succeeded)
    if extracted_constraints and any(extracted_constraints.get(k) for k in ["styles", "formality", "season"]):
        items = _apply_constraint_filters(items, extracted_constraints, season=season)

    return {
        "wardrobe_candidates": items,
        "thoughts": thoughts,
        "actions": actions,
        "observations": observations,
    }


# ---------------------------------------------------------------------------
# Node 3 — compose_outfit
# ---------------------------------------------------------------------------


def _select_best_item(
    candidates: list[Any],
    base_items: list[Any],
    season: str | None,
    occasion: str | None,
    random_seed: float | None = None,
) -> Any | None:
    """Pick a candidate based on compatibility scores.
    
    If random_seed is provided, use stochastic selection from top-3 to add variety.
    Otherwise, always pick the best (deterministic).
    """
    if not candidates:
        return None
    try:
        import numpy as np

        # Use module-level imports (may be patched by tests)
        _compat = compatibility_model
        _vs = vector_store

        base_vecs = []
        for it in base_items:
            embs = _vs.fetch_embeddings([it.id]) if _vs else {}
            v = embs.get(str(it.id))
            if v is not None:
                base_vecs.append(np.array(v))

        if not base_vecs or _compat is None:
            # Stochastic pick from top candidates if seed provided
            if random_seed is not None and len(candidates) > 1:
                import random
                random.seed(int(random_seed * 1000000))
                return random.choice(candidates[:min(3, len(candidates))])
            return candidates[0]

        scores = []
        for cand in candidates:
            embs = _vs.fetch_embeddings([cand.id]) if _vs else {}
            cv = embs.get(str(cand.id))
            if cv is None:
                scores.append(-1.0)
                continue
            cv_arr = np.array(cv)
            pair_scores = [
                _compat.pair_compatibility(
                    cv_arr, bv, item_a=cand, item_b=base_items[i],
                    season=season, occasion=occasion
                )
                for i, bv in enumerate(base_vecs)
            ]
            scores.append(float(np.mean(pair_scores)))
        
        # Stochastic selection from top-3 if seed provided
        if random_seed is not None and len(candidates) > 1:
            import random
            random.seed(int(random_seed * 1000000))
            # Get top-3 indices
            top_indices = np.argsort(scores)[-3:][::-1]
            top_indices = [i for i in top_indices if scores[i] >= 0]
            if top_indices:
                chosen_idx = random.choice(top_indices)
                return candidates[chosen_idx]
        
        # Deterministic: return best
        best_idx = np.argmax(scores)
        if scores[best_idx] >= 0:
            return candidates[best_idx]
        return candidates[0]
    except Exception:
        if random_seed is not None and len(candidates) > 1:
            import random
            random.seed(int(random_seed * 1000000))
            return random.choice(candidates[:min(3, len(candidates))])
        return candidates[0]


def _compose_outfit_deterministic(
    wardrobe_candidates: list[Any],
    season: str | None,
    occasion: str | None,
    exclude_ids: set[str],
    **kwargs: Any,
) -> list[dict]:
    """Greedy heuristic: pick one haut/robe, one bas (if no robe), one chaussures."""
    by_cat: dict[str, list[Any]] = {}
    for it in wardrobe_candidates:
        cat = getattr(it, "category", "") or ""
        if str(getattr(it, "id", "")) in exclude_ids:
            continue
        by_cat.setdefault(cat, []).append(it)

    outfit: list[Any] = []

    # Add randomness: shuffle candidates within each category based on random_seed
    random_seed = kwargs.get("random_seed")
    if random_seed is not None:
        import random
        random.seed(int(random_seed * 1000000))
        for key in by_cat:
            random.shuffle(by_cat[key])

    # Prefer robe if available
    robes = by_cat.get("robe", [])
    hauts = by_cat.get("haut", [])
    bas_list = by_cat.get("bas", [])
    shoes = by_cat.get("chaussures", [])

    if robes:
        robe = _select_best_item(robes, [], season, occasion)
        if robe:
            outfit.append(robe)
    else:
        haut = _select_best_item(hauts, [], season, occasion)
        if haut:
            outfit.append(haut)
        bas = _select_best_item(bas_list, outfit, season, occasion)
        if bas:
            outfit.append(bas)

    shoe = _select_best_item(shoes, outfit, season, occasion)
    if shoe:
        outfit.append(shoe)

    return [_item_to_dict(it) for it in outfit]


def _node_compose_outfit(state: RecommendationState) -> dict:
    thoughts = list(state.get("thoughts") or [])
    actions = list(state.get("actions") or [])
    observations = list(state.get("observations") or [])

    candidates = list(state.get("wardrobe_candidates") or [])
    llm_agent = state.get("llm_agent")
    occasion = state.get("occasion")
    occasion_category = state.get("occasion_category")
    weather_band = state.get("weather_band")
    season = state.get("season")
    style_guidelines = state.get("style_guidelines") or []

    # exclude items already used in previous outfit iterations
    all_outfits = state.get("all_outfits") or []
    used_ids: set[str] = set()
    for prev in all_outfits:
        for iid in (prev.get("item_ids") or []):
            used_ids.add(str(iid))

    outfit_items: list[dict] = []

    # --- LLM path ---
    if llm_agent is not None:
        try:
            cand_dicts = [_item_to_dict(it) for it in candidates if str(getattr(it, "id", "")) not in used_ids]
            system_msg = {
                "role": "system",
                "content": (
                    "Tu es un styliste expert. Compose une tenue complète à partir "
                    "des pièces disponibles en respectant les guidelines de style."
                ),
            }
            user_msg = {
                "role": "user",
                "content": (
                    f"Occasion: {occasion_category or occasion}, "
                    f"météo: {weather_band}, saison: {season}\n\n"
                    "Guidelines:\n" + "\n".join(f"• {g}" for g in style_guidelines) + "\n\n"
                    "Pièces disponibles (JSON):\n" +
                    "\n".join(
                        f"  id={it['id']} cat={it['category']} "
                        f"colors={it['colors']} style={it['style']} season={it['season']}"
                        for it in cand_dicts[:40]
                    ) + "\n\n"
                    "Réponds avec un JSON: {\"ids\": [\"<id1>\", \"<id2>\", ...]}"
                ),
            }
            raw = llm_agent._chat([system_msg, user_msg])
            raw_text = raw if isinstance(raw, str) else str(raw)
            start = raw_text.find("{")
            end = raw_text.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(raw_text[start:end])
                ids = [str(i) for i in (parsed.get("ids") or [])]
                id_set = {str(getattr(it, "id", "")) for it in candidates}
                valid_ids = [i for i in ids if i in id_set]
                if valid_ids:
                    id_lookup = {str(getattr(it, "id", "")): it for it in candidates}
                    outfit_items = [_item_to_dict(id_lookup[i]) for i in valid_ids if i in id_lookup]
        except Exception:
            logger.warning("compose_outfit LLM failed; using deterministic fallback", exc_info=True)

    # --- Deterministic fallback ---
    if not outfit_items:
        random_seed = state.get("_random_seed")
        outfit_items = _compose_outfit_deterministic(candidates, season, occasion, used_ids, random_seed=random_seed)

    thoughts.append(
        f"Composition de la tenue: {len(outfit_items)} pièces sélectionnées"
    )
    actions.append({
        "tool": "compose_outfit",
        "args": {
            "candidates_count": len(candidates),
            "used_llm": llm_agent is not None and bool(outfit_items),
        },
    })
    observations.append({
        "tool_name": "compose_outfit",
        "result": [it.get("id") for it in outfit_items],
        "reasoning": f"Selected {len(outfit_items)} items",
        "error": None,
    })

    return {
        "current_outfit": outfit_items,
        "thoughts": thoughts,
        "actions": actions,
        "observations": observations,
    }


# ---------------------------------------------------------------------------
# Node 4 — check_rules
# ---------------------------------------------------------------------------


def _node_check_rules(state: RecommendationState) -> dict:
    from app.agents.recommendation_tools import check_outfit_rules

    thoughts = list(state.get("thoughts") or [])
    actions = list(state.get("actions") or [])
    observations = list(state.get("observations") or [])

    current_outfit = state.get("current_outfit") or []
    result = check_outfit_rules(current_outfit)

    thoughts.append(
        f"Vérification des règles: {result['result']}"
    )
    actions.append({"tool": "check_outfit_rules",
                    "args": {"items_count": len(current_outfit)}})
    observations.append(result)

    return {
        "outfit_rules": result.get("result", {}),
        "steps": (state.get("steps") or 0) + 1,
        "thoughts": thoughts,
        "actions": actions,
        "observations": observations,
    }


# ---------------------------------------------------------------------------
# Node 5 — critic_evaluate
# ---------------------------------------------------------------------------


def _node_critic_evaluate(state: RecommendationState) -> dict:
    from app.agents.recommendation_critic import CriticAgent

    thoughts = list(state.get("thoughts") or [])
    actions = list(state.get("actions") or [])
    observations = list(state.get("observations") or [])

    current_outfit = state.get("current_outfit") or []
    usage = state.get("usage") or {}
    season = state.get("season")

    # Compute recent item IDs (worn in last 3 days)
    recent_cutoff = date.today() - timedelta(days=3)
    recent_item_ids = [
        str(k)
        for k, v in usage.items()
        if v.get("last_worn") and v["last_worn"] > recent_cutoff
    ]

    context = {
        "occasion": state.get("occasion"),
        "occasion_category": state.get("occasion_category"),
        "weather_band": state.get("weather_band"),
        "temperature": state.get("temperature"),
        "season": season,
        "recent_item_ids": recent_item_ids,
    }

    critic = CriticAgent(llm_agent=state.get("llm_agent"))
    score = critic.evaluate(
        outfit_items=current_outfit,
        context=context,
        style_guidelines=state.get("style_guidelines") or [],
    )

    thoughts.append(
        f"Évaluation Critic: total={score['total']}/25, "
        f"approved={score['approved']}, feedback={score['feedback']}"
    )
    actions.append({"tool": "critic_evaluate",
                    "args": {"items_count": len(current_outfit)}})
    observations.append({
        "tool_name": "critic_evaluate",
        "result": score,
        "reasoning": f"total={score['total']}/25, approved={score['approved']}",
        "error": None,
    })

    return {
        "critic_score": score,
        "critic_iterations": (state.get("critic_iterations") or 0) + 1,
        "thoughts": thoughts,
        "actions": actions,
        "observations": observations,
    }


# ---------------------------------------------------------------------------
# Node 6 — replan
# ---------------------------------------------------------------------------


def _node_replan(state: RecommendationState) -> dict:
    thoughts = list(state.get("thoughts") or [])
    actions = list(state.get("actions") or [])
    observations = list(state.get("observations") or [])

    critic_score = state.get("critic_score") or {}
    outfit_rules = state.get("outfit_rules") or {}
    feedback = critic_score.get("feedback", "")
    issues = outfit_rules.get("issues", [])

    thoughts.append(f"Critique reçue : {feedback}. Re-planification en cours.")
    actions.append({"tool": "replan", "args": {"issues": issues}})

    current_outfit = list(state.get("current_outfit") or [])
    candidates = list(state.get("wardrobe_candidates") or [])
    season = state.get("season")
    occasion = state.get("occasion")

    # Build current category set
    current_cats = {it.get("category", "") for it in current_outfit}
    current_ids = {it.get("id", "") for it in current_outfit}

    by_cat: dict[str, list[Any]] = {}
    for it in candidates:
        cat = getattr(it, "category", "") or ""
        if str(getattr(it, "id", "")) not in current_ids:
            by_cat.setdefault(cat, []).append(it)

    # Fix missing chaussures
    if "chaussures" not in current_cats and by_cat.get("chaussures"):
        shoe = _select_best_item(
            by_cat["chaussures"],
            [],
            season,
            occasion,
        )
        if shoe:
            current_outfit.append(_item_to_dict(shoe))

    # Fix missing haut/robe
    if not current_cats & {"haut", "robe"}:
        tops = by_cat.get("haut", []) + by_cat.get("robe", [])
        if tops:
            top = _select_best_item(tops, [], season, occasion)
            if top:
                current_outfit.append(_item_to_dict(top))

    # Fix missing bas
    if "bas" not in current_cats and "robe" not in {it.get("category") for it in current_outfit}:
        if by_cat.get("bas"):
            bas = _select_best_item(by_cat["bas"], [], season, occasion)
            if bas:
                current_outfit.append(_item_to_dict(bas))

    observations.append({
        "tool_name": "replan",
        "result": {"outfit_len": len(current_outfit)},
        "reasoning": "Corrected outfit based on issues",
        "error": None,
    })

    return {
        "current_outfit": current_outfit,
        "thoughts": thoughts,
        "actions": actions,
        "observations": observations,
    }


# ---------------------------------------------------------------------------
# DL scoring helper
# ---------------------------------------------------------------------------


def _compute_dl_score(
    state: RecommendationState,
    current_outfit: list[dict],
    relevance_score: float,
) -> dict:
    """Compute the DL/RLHF composite score for an outfit.

    Returns a dict with keys: transformer_compatibility, preference_reward,
    combined, alpha, beta.  Falls back gracefully if torch or modules unavailable.
    """
    _ALPHA = 0.6
    _BETA = 0.4
    _fallback = {
        "transformer_compatibility": relevance_score,
        "preference_reward": 0.5,
        "combined": relevance_score,
        "alpha": _ALPHA,
        "beta": _BETA,
    }

    try:
        import numpy as np

        # (a) Collect item_ids from current_outfit
        item_ids: list[Any] = []
        for it in current_outfit:
            raw_id = it.get("id", "")
            try:
                item_ids.append(uuid.UUID(str(raw_id)))
            except Exception:
                item_ids.append(raw_id)

        # (b) Fetch embeddings
        _vs = vector_store
        emb_dict: dict = {}
        if _vs is not None and item_ids:
            try:
                emb_dict = _vs.fetch_embeddings(item_ids)
            except Exception:
                emb_dict = {}

        # (c) Build embeddings list
        embeddings: list[Any] = [
            np.array(emb_dict[str(iid)])
            for iid in item_ids
            if str(iid) in emb_dict
        ]

        # (d) Transformer compatibility score
        _otr = outfit_transformer_module
        if _otr is not None and len(embeddings) >= 2:
            transformer_compatibility = float(_otr.score_outfit(embeddings))
        else:
            transformer_compatibility = relevance_score

        # (e) Preference reward score (sigmoid-normalised to [0, 1])
        model = state.get("reward_model")
        if (
            model is not None
            and getattr(model, "_trained", False)
            and len(embeddings) >= 1
        ):
            raw = model.predict_reward(embeddings)
            preference_reward = float(1.0 / (1.0 + math.exp(-raw)))
        else:
            preference_reward = 0.5

        # (f) Combined score
        combined = _ALPHA * transformer_compatibility + _BETA * preference_reward

        return {
            "transformer_compatibility": transformer_compatibility,
            "preference_reward": preference_reward,
            "combined": combined,
            "alpha": _ALPHA,
            "beta": _BETA,
        }
    except Exception:
        return _fallback


# ---------------------------------------------------------------------------
# _maybe_train_reward_model
# ---------------------------------------------------------------------------


def _maybe_train_reward_model(state: RecommendationState) -> Any:
    """Attempt to train (or reload) the per-user reward model from feedback pairs.

    Returns the trained PreferenceRewardModel, or None if unavailable / no data.
    """
    try:
        if _build_preference_pairs is None or _prm_load_or_init is None:
            return None

        db = state.get("db")
        user_id = state.get("user_id") or ""
        if not db or not user_id:
            return None

        pairs = _build_preference_pairs(db, user_id, vector_store)
        if not pairs:
            return None

        model = _prm_load_or_init(user_id)
        from app.ml.preference_reward_model import train_from_feedback as _train_fw
        from app.ml.preference_reward_model import save as _prm_save
        _train_fw(model, pairs)
        _prm_save(model, user_id)
        return model
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Node 7 — finalize
# ---------------------------------------------------------------------------


def _node_finalize(state: RecommendationState) -> dict:
    thoughts = list(state.get("thoughts") or [])
    actions = list(state.get("actions") or [])
    observations = list(state.get("observations") or [])

    current_outfit = state.get("current_outfit") or []
    critic_score = state.get("critic_score")
    style_guidelines = state.get("style_guidelines") or []
    occasion = state.get("occasion")
    season = state.get("season")
    weather = state.get("weather")
    weather_band = state.get("weather_band")
    llm_agent = state.get("llm_agent")

    # Build item_ids as UUIDs (preserve original UUIDs from ClothingItem)
    item_ids: list[Any] = []
    for it in current_outfit:
        raw_id = it.get("id", "")
        try:
            item_ids.append(uuid.UUID(str(raw_id)))
        except Exception:
            item_ids.append(raw_id)

    # Relevance score from critic total
    if critic_score and critic_score.get("total") is not None:
        relevance_score = round(critic_score["total"] / 25, 2)
    else:
        relevance_score = 0.5

    # Compute DL/RLHF composite score
    dl_score = _compute_dl_score(state, current_outfit, relevance_score)

    # Build explanation
    explanation = _build_explanation(
        llm_agent=llm_agent,
        current_outfit=current_outfit,
        occasion=occasion,
        request_text=state.get("request_text"),
        season=season,
        weather=weather,
        weather_band=weather_band,
        relevance_score=relevance_score,
        critic_score=critic_score,
        style_guidelines=style_guidelines,
    )

    # Build ReAct trace
    zipped = zip(
        thoughts,
        actions if actions else [{}] * len(thoughts),
        observations if observations else [{}] * len(thoughts),
    )
    react_trace = [
        {"thought": t, "action": a, "observation": o}
        for t, a, o in zipped
    ]

    outfit_dict = {
        "item_ids": item_ids,
        "relevance_score": relevance_score,
        "explanation": explanation,
        "critic_score": critic_score,
        "critic_feedback": critic_score.get("feedback") if critic_score else None,
        "critic_iterations": state.get("critic_iterations") or 0,
        "react_trace": react_trace,
        "style_guidelines_used": style_guidelines,
        "dl_score": dl_score,
    }

    all_outfits = list(state.get("all_outfits") or [])
    all_outfits.append(outfit_dict)

    thoughts.append("Finalisation de la tenue.")
    actions.append({"tool": "finalize", "args": {}})
    observations.append({
        "tool_name": "finalize",
        "result": {"item_ids_count": len(item_ids)},
        "reasoning": "Outfit finalized",
        "error": None,
    })

    return {
        "all_outfits": all_outfits,
        "final_outfit": outfit_dict,
        "thoughts": thoughts,
        "actions": actions,
        "observations": observations,
    }


def _build_explanation(
    *,
    llm_agent: Any,
    current_outfit: list[dict] | None = None,
    occasion: str | None,
    request_text: str | None = None,
    season: str | None,
    weather: str | None,
    weather_band: str | None,
    relevance_score: float = 0.5,
    critic_score: dict | None = None,
    style_guidelines: list[str] | None = None,
    # Legacy compatibility args (ignored in new path)
    outfit: Any = None,
    score: float | None = None,
    style_match: bool = False,
    top_style: str | None = None,
    occasion_category: str | None = None,
    formality: int | None = None,
    temperature: float | None = None,
    references: Any = None,
) -> str:
    """Build a natural-language explanation for the outfit."""
    # Legacy compatibility: accept old-style ClothingItem list via 'outfit'
    if current_outfit is None and outfit is not None:
        if isinstance(outfit, list):
            current_outfit = [_item_to_dict(it) if not isinstance(it, dict) else it for it in outfit]
        else:
            current_outfit = []
    if current_outfit is None:
        current_outfit = []
    if score is not None and relevance_score == 0.5:
        relevance_score = score
    if style_guidelines is None:
        style_guidelines = []
    if occasion_category is not None and occasion is None:
        occasion = occasion_category
    if temperature is not None and weather_band is None:
        weather_band = _weather_band_from_temp(temperature)
    pieces = ", ".join(it.get("category", "?") for it in current_outfit)
    for_occasion = f" pour {occasion}" if occasion else ""
    weather_note = f", météo {weather_band}" if weather_band else ""
    score_pct = int(relevance_score * 100)
    base = (
        f"Tenue composée de {len(current_outfit)} pièces ({pieces}){for_occasion}"
        f"{weather_note}. Score : {score_pct}%."
    )
    if style_guidelines:
        base += f" Guideline appliquée : {style_guidelines[0]}"

    if llm_agent is not None:
        try:
            # Use request_text (original user phrase) if available, otherwise use parsed occasion
            effective_occasion = request_text or occasion or "une occasion"
            
            # Enrich facts with more context for better LLM generation
            facts = {
                "items": current_outfit,
                "item_details": {
                    "count": len(current_outfit),
                    "categories": [it.get("category", "?") for it in current_outfit],
                    "colors": [color for it in current_outfit for color in (it.get("colors") or [])],
                },
                "scores": {
                    "relevance": relevance_score,
                    **({"critic": critic_score} if critic_score else {}),
                },
                "context": {
                    "user_request": effective_occasion,  # Original user phrase
                    "parsed_occasion": occasion,  # Parsed occasion category
                    "season": season,
                    "weather": weather,
                    "weather_band": weather_band,
                },
                "guidelines": style_guidelines or [],
            }
            expl = llm_agent.explain_outfit(facts)
            if expl:
                return str(expl)[:2048]
        except Exception:
            pass

    return base[:2048]


# ---------------------------------------------------------------------------
# Conditional edge functions
# ---------------------------------------------------------------------------


def _route_check_rules(state: RecommendationState) -> str:
    steps = state.get("steps") or 0
    max_steps = state.get("max_steps") or 10
    rules = state.get("outfit_rules") or {}
    issues = rules.get("issues", [])

    if steps >= max_steps:
        return "finalize"
    if issues:
        return "replan"
    return "critic_evaluate"


def _route_critic_evaluate(state: RecommendationState) -> str:
    critic_score = state.get("critic_score") or {}
    critic_iterations = state.get("critic_iterations") or 0
    max_critic_iterations = state.get("max_critic_iterations") or 3

    if critic_score.get("approved") or critic_iterations >= max_critic_iterations:
        return "finalize"
    return "replan"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def _build_graph():
    try:
        from langgraph.graph import StateGraph, END

        graph = StateGraph(RecommendationState)

        graph.add_node("analyze_context", _node_analyze_context)
        graph.add_node("extract_constraints", _node_extract_constraints)
        graph.add_node("search_candidates", _node_search_candidates)
        graph.add_node("compose_outfit", _node_compose_outfit)
        graph.add_node("check_rules", _node_check_rules)
        graph.add_node("critic_evaluate", _node_critic_evaluate)
        graph.add_node("replan", _node_replan)
        graph.add_node("finalize", _node_finalize)

        graph.set_entry_point("analyze_context")
        graph.add_edge("analyze_context", "extract_constraints")
        graph.add_edge("extract_constraints", "search_candidates")
        graph.add_edge("search_candidates", "compose_outfit")
        graph.add_edge("compose_outfit", "check_rules")

        graph.add_conditional_edges(
            "check_rules",
            _route_check_rules,
            {
                "critic_evaluate": "critic_evaluate",
                "replan": "replan",
                "finalize": "finalize",
            },
        )
        graph.add_conditional_edges(
            "critic_evaluate",
            _route_critic_evaluate,
            {
                "finalize": "finalize",
                "replan": "replan",
            },
        )
        graph.add_edge("replan", "check_rules")
        graph.add_edge("finalize", END)

        return graph.compile()
    except Exception as exc:
        logger.warning("LangGraph build failed: %s", exc)
        return None


_GRAPH = None


def _get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_graph()
    return _GRAPH


# ---------------------------------------------------------------------------
# RecommendationAgent
# ---------------------------------------------------------------------------


class RecommendationAgent(BaseAgent):
    """Generates outfits using a LangGraph ReAct + Stylist/Critic loop.

    Preserves the orchestrator contract exactly:
    run(**kwargs) -> {"outfits": [{item_ids, relevance_score, explanation, ...}]}
    """

    name = "recommendation_agent"

    def run(
        self,
        *,
        wardrobe_items: list,
        occasion: str | None = None,
        request_text: str | None = None,
        favorite_styles: list | None = None,
        top_k: int = 3,
        usage: dict | None = None,
        today: date | None = None,
        season: str | None = None,
        temperature: float | None = None,
        weather: str | None = None,
        occasion_category: str | None = None,
        formality: int | None = None,
        references: dict | None = None,
        ctx_vec: Any = None,
        llm_agent: Any = None,
        city: str | None = None,
        feedback_preferences: list | None = None,
        db: Any = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        # Resolve user_id: prefer from wardrobe_items, else from db, else empty string
        user_id = ""
        if wardrobe_items:
            first = wardrobe_items[0]
            uid = getattr(first, "owner_id", None)
            if uid is not None:
                user_id = str(uid)

        # Compute weather_band if not provided
        from app.services.occasions import weather_band as _wb
        computed_wb = _wb(temperature)

        # Guard: empty wardrobe → no outfits
        if not wardrobe_items:
            return {"outfits": []}

        # Build initial state
        base_state: RecommendationState = {
            "user_id": user_id,
            "occasion": occasion,
            "request_text": request_text,
            "occasion_category": occasion_category,
            "city": city,
            "season": season,
            "temperature": temperature,
            "weather_band": computed_wb,
            "wardrobe_items": list(wardrobe_items),
            "favorite_styles": list(favorite_styles or []),
            "usage": dict(usage or {}),
            "feedback_preferences": list(feedback_preferences or []),
            "references": references,
            "ctx_vec": ctx_vec,
            "formality": formality,
            "db": db,
            "llm_agent": llm_agent,
            # Working state
            "weather": weather,
            "wardrobe_candidates": [],
            "style_guidelines": [],
            "extracted_constraints": {},
            "current_outfit": [],
            "outfit_rules": {},
            "thoughts": [],
            "actions": [],
            "observations": [],
            "steps": 0,
            "max_steps": 10,
            # Critic
            "critic_score": None,
            "critic_iterations": 0,
            "max_critic_iterations": 3,
            # Output
            "all_outfits": [],
            "final_outfit": None,
            "error": None,
        }

        graph = _get_graph()

        # Train/reload reward model once per run() call
        reward_model = _maybe_train_reward_model(base_state)
        if reward_model is not None:
            base_state["reward_model"] = reward_model

        collected_outfits: list[dict] = []

        for i in range(top_k):
            try:
                if graph is None:
                    raise RuntimeError("LangGraph graph could not be compiled")

                # Create fresh state per iteration (exclude already-used items
                # by carrying all_outfits forward)
                state = dict(base_state)
                state["all_outfits"] = collected_outfits
                # Reset per-run working state
                state["current_outfit"] = []
                state["outfit_rules"] = {}
                state["thoughts"] = []
                state["actions"] = []
                state["observations"] = []
                state["steps"] = 0
                state["critic_score"] = None
                state["critic_iterations"] = 0
                # Add randomness seed for variation across iterations
                import random
                state["_random_seed"] = random.random()

                final_state = graph.invoke(state)
                outfit = final_state.get("final_outfit")
                if outfit:
                    # Deduplicate: skip if exact same set of items already collected
                    new_set = frozenset(str(iid) for iid in (outfit.get("item_ids") or []))
                    already = any(
                        frozenset(str(iid) for iid in (o.get("item_ids") or [])) == new_set
                        for o in collected_outfits
                    )
                    if not already and new_set:
                        collected_outfits.append(outfit)
            except Exception as exc:
                logger.warning(
                    "RecommendationAgent graph iteration %d failed: %s", i, exc, exc_info=True
                )
                # Deterministic fallback for this iteration
                fallback = self._fallback_outfit(wardrobe_items, season, occasion)
                if fallback:
                    fb_set = frozenset(str(iid) for iid in (fallback.get("item_ids") or []))
                    already = any(
                        frozenset(str(iid) for iid in (o.get("item_ids") or [])) == fb_set
                        for o in collected_outfits
                    )
                    if not already and fb_set:
                        collected_outfits.append(fallback)
                break  # one fallback is enough

        if not collected_outfits:
            fallback = self._fallback_outfit(wardrobe_items, season, occasion)
            if fallback:
                collected_outfits.append(fallback)

        return {"outfits": collected_outfits}

    # ------------------------------------------------------------------
    # Deterministic fallback
    # ------------------------------------------------------------------

    def _fallback_outfit(
        self,
        wardrobe_items: list,
        season: str | None,
        occasion: str | None,
    ) -> dict | None:
        """Return a single outfit from first available haut/bas/chaussures."""
        if not wardrobe_items:
            return None

        by_cat: dict[str, list] = {}
        for it in wardrobe_items:
            cat = getattr(it, "category", "") or ""
            by_cat.setdefault(cat, []).append(it)

        outfit: list[Any] = []
        for cat in ("haut", "robe", "bas", "chaussures"):
            items = by_cat.get(cat, [])
            if items and (cat != "bas" or "robe" not in {getattr(i, "category", "") for i in outfit}):
                outfit.append(items[0])
                if len(outfit) >= 3:
                    break

        if not outfit:
            outfit = wardrobe_items[:3]

        item_ids = []
        for it in outfit:
            try:
                item_ids.append(uuid.UUID(str(getattr(it, "id", ""))))
            except Exception:
                item_ids.append(getattr(it, "id", ""))

        pieces = ", ".join(getattr(it, "category", "?") for it in outfit)
        return {
            "item_ids": item_ids,
            "relevance_score": 0.5,
            "explanation": f"Tenue proposée par défaut ({pieces}).",
            "critic_score": None,
            "critic_feedback": None,
            "critic_iterations": 0,
            "react_trace": [],
            "style_guidelines_used": [],
            "dl_score": {
                "transformer_compatibility": 0.5,
                "preference_reward": 0.5,
                "combined": 0.5,
                "alpha": 0.6,
                "beta": 0.4,
            },
        }

"""Tool layer for RecommendationAgent (LangGraph rewrite).

Six Pydantic-validated tools replace the old MCP-based approach.
Every tool returns:
  {tool_name: str, result: Any, reasoning: str, error: str | None}
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.services.weather import WeatherService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic input models
# ---------------------------------------------------------------------------

class GetWeatherInput(BaseModel):
    city: str
    date: str | None = None  # ISO date, optional


class SearchWardrobeInput(BaseModel):
    user_id: str
    query: str
    filters: dict | None = None


class FilterWardrobeInput(BaseModel):
    user_id: str
    category: str | None = None
    color: str | None = None
    season: str | None = None


class GetUserPreferencesInput(BaseModel):
    user_id: str


class CheckOutfitRulesInput(BaseModel):
    items: list[dict]  # each: {id, category, colors, style, season}


class RecordFeedbackInput(BaseModel):
    outfit_id: str
    user_id: str
    rating: Literal["like", "dislike", "worn"]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def get_weather(
    city: str,
    date: str | None = None,
    db: Session | None = None,
) -> dict:
    """Fetch current weather for a city.

    Falls back to WeatherService._get_fallback_weather when the API key is
    missing or the request fails.
    """
    try:
        svc = WeatherService()
        data = svc.get_current_weather(city)
        if data is None:
            data = svc._get_fallback_weather(city)
            reasoning = f"API unavailable for '{city}'; using seasonal fallback"
        else:
            temp = data.get("main", {}).get("temp")
            desc = data.get("weather", [{}])[0].get("description", "")
            reasoning = f"Fetched weather for '{city}': {temp}°C, {desc}"
        return {"tool_name": "get_weather", "result": data, "reasoning": reasoning, "error": None}
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_weather failed: %s", exc)
        try:
            fallback = WeatherService()._get_fallback_weather(city)
        except Exception:
            fallback = {"main": {"temp": 20.0}, "weather": [{"description": "unknown"}]}
        return {
            "tool_name": "get_weather",
            "result": fallback,
            "reasoning": "Exception; using hardcoded fallback",
            "error": str(exc),
        }


def search_wardrobe(
    user_id: str,
    query: str,
    filters: dict | None = None,
    db: Session | None = None,
) -> dict:
    """Query ClothingItem by owner_id, then rank by TF-IDF cosine similarity.

    If *db* is None (test / no-DB environment) returns an empty result list.
    """
    try:
        from app.models.clothing_item import ClothingItem as _CI
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np
        import uuid as _uuid

        if db is None:
            return {
                "tool_name": "search_wardrobe",
                "result": [],
                "reasoning": "No DB session; returning empty",
                "error": None,
            }

        uid = _uuid.UUID(user_id)
        q = db.query(_CI).filter(_CI.owner_id == uid)

        # Optional hard-filters from filters dict
        if filters:
            if filters.get("category"):
                q = q.filter(_CI.category == filters["category"])
            if filters.get("season"):
                q = q.filter(_CI.season == filters["season"])
            if filters.get("style"):
                q = q.filter(_CI.style == filters["style"])

        items = q.all()
        if not items:
            return {
                "tool_name": "search_wardrobe",
                "result": [],
                "reasoning": "No items found for user",
                "error": None,
            }

        def _text(item: _CI) -> str:
            colors = " ".join(item.colors or [])
            return f"{item.category or ''} {item.style or ''} {item.season or ''} {colors}"

        corpus = [_text(it) for it in items]
        vec = TfidfVectorizer().fit(corpus)
        matrix = vec.transform(corpus)
        query_vec = vec.transform([query])
        sims = cosine_similarity(query_vec, matrix).flatten()
        order = np.argsort(sims)[::-1]
        ranked = [items[i] for i in order]

        reasoning = (
            f"TF-IDF search over {len(items)} items for query '{query}'; "
            f"top match score {sims[order[0]]:.2f}"
        )
        return {
            "tool_name": "search_wardrobe",
            "result": ranked,
            "reasoning": reasoning,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("search_wardrobe failed: %s", exc)
        return {
            "tool_name": "search_wardrobe",
            "result": [],
            "reasoning": "Exception during search",
            "error": str(exc),
        }


def filter_wardrobe(
    user_id: str,
    category: str | None = None,
    color: str | None = None,
    season: str | None = None,
    db: Session | None = None,
) -> dict:
    """SQLAlchemy query ClothingItem with optional category / color / season filters."""
    try:
        from app.models.clothing_item import ClothingItem as _CI
        import uuid as _uuid

        if db is None:
            return {
                "tool_name": "filter_wardrobe",
                "result": [],
                "reasoning": "No DB session; returning empty",
                "error": None,
            }

        uid = _uuid.UUID(user_id)
        q = db.query(_CI).filter(_CI.owner_id == uid)

        if category:
            q = q.filter(_CI.category == category)
        if season:
            # season may be None/toutes_saisons — handle gracefully
            q = q.filter(
                (_CI.season == season)
                | (_CI.season == "toutes_saisons")
                | (_CI.season.is_(None))
            )
        if color:
            # colors is stored as JSON list text; use ilike on the raw JSON column
            q = q.filter(_CI.colors.ilike(f'%"{color}"%'))  # type: ignore[attr-defined]

        items = q.all()
        reasoning = (
            f"Filtered wardrobe for user {user_id}: "
            f"category={category}, color={color}, season={season} → {len(items)} items"
        )
        return {
            "tool_name": "filter_wardrobe",
            "result": items,
            "reasoning": reasoning,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("filter_wardrobe failed: %s", exc)
        return {
            "tool_name": "filter_wardrobe",
            "result": [],
            "reasoning": "Exception during filter",
            "error": str(exc),
        }


def get_user_preferences(
    user_id: str,
    db: Session | None = None,
) -> dict:
    """Compute favorite styles/colors from ClothingItem + last 10 feedback entries."""
    try:
        from app.models.clothing_item import ClothingItem as _CI
        from app.models.recommendation_feedback import RecommendationFeedback as _RF
        from app.models.outfit import Outfit as _O
        import uuid as _uuid

        if db is None:
            return {
                "tool_name": "get_user_preferences",
                "result": {
                    "favorite_styles": [],
                    "favorite_colors": [],
                    "feedback_history": [],
                },
                "reasoning": "No DB session",
                "error": None,
            }

        uid = _uuid.UUID(user_id)
        items = db.query(_CI).filter(_CI.owner_id == uid).all()

        style_counter: Counter[str] = Counter()
        color_counter: Counter[str] = Counter()
        for it in items:
            if it.style:
                style_counter[it.style] += 1
            for c in (it.colors or []):
                color_counter[c] += 1

        feedback_rows = (
            db.query(_RF)
            .join(_O, _RF.outfit_id == _O.id)
            .filter(_O.owner_id == uid)
            .order_by(_RF.updated_at.desc())
            .limit(10)
            .all()
        )
        feedback_history = [
            {"outfit_id": str(fb.outfit_id), "rating": fb.rating}
            for fb in feedback_rows
        ]

        result = {
            "favorite_styles": [s for s, _ in style_counter.most_common(5)],
            "favorite_colors": [c for c, _ in color_counter.most_common(5)],
            "feedback_history": feedback_history,
        }
        return {
            "tool_name": "get_user_preferences",
            "result": result,
            "reasoning": f"Computed from {len(items)} items, {len(feedback_history)} feedback entries",
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_user_preferences failed: %s", exc)
        return {
            "tool_name": "get_user_preferences",
            "result": {"favorite_styles": [], "favorite_colors": [], "feedback_history": []},
            "reasoning": "Exception; returning empty preferences",
            "error": str(exc),
        }


def check_outfit_rules(items: list[dict]) -> dict:
    """Deterministic completeness + color-harmony + season-clash check.

    *items* is a list of dicts: {id, category, colors, style, season}.

    Returns:
        {tool_name, result: {complete, color_ok, issues}, reasoning, error}
    """
    issues: list[str] = []

    # --- completeness ---
    categories = {it.get("category", "") for it in items}
    has_top = bool(categories & {"haut", "robe"})
    has_bottom = bool(categories & {"bas", "robe"})
    has_shoes = "chaussures" in categories

    if not has_top:
        issues.append("Manque un haut ou une robe")
    if not has_bottom:
        issues.append("Manque un bas ou une robe")
    if not has_shoes:
        issues.append("Manque des chaussures")

    complete = not issues  # will be refined with color / season below

    # --- color harmony ---
    all_colors: list[str] = []
    for it in items:
        raw = it.get("colors", [])
        if isinstance(raw, list):
            all_colors.extend(raw)
        elif isinstance(raw, str):
            all_colors.append(raw)

    dominant = list(dict.fromkeys(all_colors))  # deduplicate preserving order
    color_ok = len(dominant) <= 3
    if not color_ok:
        issues.append(f"Trop de couleurs dominantes ({len(dominant)} > 3)")

    # --- season clash ---
    seasons_in_outfit = {it.get("season") for it in items if it.get("season") not in (None, "toutes_saisons")}
    season_clash = "ete" in seasons_in_outfit and "hiver" in seasons_in_outfit
    if season_clash:
        issues.append("Mélange été/hiver dans la même tenue")

    rules_ok = complete and color_ok and not season_clash
    result = {"complete": complete, "color_ok": color_ok, "issues": issues}

    reasoning = (
        "Outfit rules: "
        + (f"complete={complete}, color_ok={color_ok}, season_clash={season_clash}. "
           f"Issues: {issues or 'none'}")
    )
    return {
        "tool_name": "check_outfit_rules",
        "result": result,
        "reasoning": reasoning,
        "error": None,
    }


def record_feedback(
    outfit_id: str,
    user_id: str,
    rating: str,
    db: Session | None = None,
) -> dict:
    """Upsert a RecommendationFeedback row. No-op when db is None."""
    if db is None:
        return {
            "tool_name": "record_feedback",
            "result": None,
            "reasoning": "No DB session; feedback not recorded",
            "error": None,
        }
    try:
        from app.models.recommendation_feedback import RecommendationFeedback as _RF
        import uuid as _uuid

        oid = _uuid.UUID(outfit_id)
        uid = _uuid.UUID(user_id)

        existing = db.query(_RF).filter(_RF.outfit_id == oid).first()
        if existing:
            existing.rating = rating  # type: ignore[assignment]
        else:
            fb = _RF(owner_id=uid, outfit_id=oid, rating=rating)
            db.add(fb)
        db.commit()
        return {
            "tool_name": "record_feedback",
            "result": {"outfit_id": outfit_id, "rating": rating},
            "reasoning": f"Upserted feedback '{rating}' for outfit {outfit_id}",
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("record_feedback failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return {
            "tool_name": "record_feedback",
            "result": None,
            "reasoning": "Exception during upsert",
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# MCP_TOOL_SCHEMAS — kept for reference / forward-compatibility
# ---------------------------------------------------------------------------
MCP_TOOL_SCHEMAS: dict[str, dict] = {
    "get_weather": {
        "name": "get_weather",
        "description": "Fetch current weather for a city",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "date": {"type": ["string", "null"]},
            },
            "required": ["city"],
        },
    },
    "search_wardrobe": {
        "name": "search_wardrobe",
        "description": "Semantic TF-IDF search over the user's wardrobe",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "query": {"type": "string"},
                "filters": {"type": ["object", "null"]},
            },
            "required": ["user_id", "query"],
        },
    },
    "filter_wardrobe": {
        "name": "filter_wardrobe",
        "description": "SQLAlchemy filter on ClothingItem by category/color/season",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "category": {"type": ["string", "null"]},
                "color": {"type": ["string", "null"]},
                "season": {"type": ["string", "null"]},
            },
            "required": ["user_id"],
        },
    },
    "get_user_preferences": {
        "name": "get_user_preferences",
        "description": "Derive favorite styles/colors and last feedback from the DB",
        "inputSchema": {
            "type": "object",
            "properties": {"user_id": {"type": "string"}},
            "required": ["user_id"],
        },
    },
    "check_outfit_rules": {
        "name": "check_outfit_rules",
        "description": "Deterministic completeness and color harmony check",
        "inputSchema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "category": {"type": "string"},
                            "colors": {"type": "array", "items": {"type": "string"}},
                            "style": {"type": "string"},
                            "season": {"type": "string"},
                        },
                    },
                }
            },
            "required": ["items"],
        },
    },
    "record_feedback": {
        "name": "record_feedback",
        "description": "Upsert a like/dislike/worn feedback row",
        "inputSchema": {
            "type": "object",
            "properties": {
                "outfit_id": {"type": "string"},
                "user_id": {"type": "string"},
                "rating": {"type": "string", "enum": ["like", "dislike", "worn"]},
            },
            "required": ["outfit_id", "user_id", "rating"],
        },
    },
}

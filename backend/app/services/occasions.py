"""Occasion vocabulary and weather bands shared by the three enrichment axes of the
RecommendationAgent (fine-tuning ranking, contextual RAG, prompt engineering + LLM).

This module is the *deterministic fallback* for parsing a free-text occasion into one
of a fixed vocabulary of categories. ``parse_occasion_rules`` always returns a category
from ``OCCASION_CATEGORIES`` (never ``None``, never out-of-vocabulary), so downstream
code (``ranking_model.context_vector`` indexing, ``ContextAgent`` enrichment) can rely
on a valid key. When the LLM is on (axe 3), ``LLMAgent.parse_occasion`` is tried first
and this rules-based parser is the fallback when it returns ``None``.

Keyword matching is **by token** (whole words), not by substring, to avoid false
positives such as ``"mer"`` matching inside ``"commercial"`` (review-F3).
"""

import re

from app.services.seasons import COLD_BELOW_C, HOT_FROM_C

# Eight occasion categories — enough to index the precomputed context vectors, narrow
# enough to precompute every (occasion, season, weather_band) combination.
OCCASION_CATEGORIES = [
    "mariage",
    "soiree",
    "travail",
    "casual_quotidien",
    "sport",
    "plage",
    "voyage",
    "ceremonie",
]

# (min_inclusive, max_exclusive) temperature bounds in °C; None = unbounded on that
# side. Coherent with seasons.COLD_BELOW_C (14) / HOT_FROM_C (24): froid ~ hiver,
# modere ~ mi_saison, chaud ~ ete — the same thresholds the season helpers use.
WEATHER_BANDS = {
    "froid": (None, COLD_BELOW_C),
    "modere": (COLD_BELOW_C, HOT_FROM_C),
    "chaud": (HOT_FROM_C, None),
}


def weather_band(temperature: float | None) -> str | None:
    """Map a temperature (°C) to a weather band name, or ``None`` when unknown.

    Bounds mirror the season thresholds: <14 -> "froid", 14..<24 -> "modere",
    >=24 -> "chaud". A ``None`` temperature (none measured) -> ``None``.
    """
    if temperature is None:
        return None
    for name, (low, high) in WEATHER_BANDS.items():
        if (low is None or temperature >= low) and (high is None or temperature < high):
            return name
    return None


# Keyword matching uses whole-word tokens so a short keyword such as "mer" cannot match
# inside "commercial". \w is Unicode-aware in Python 3 (matches accented letters); the
# explicit accents make the intent obvious and guard against any re.ASCII surprise.
_TOKEN_SPLIT = re.compile(r"[^\wàâäéèêëïîôöùûüç]+", re.UNICODE)


def _tokens(text: str | None) -> set[str]:
    if text is None:
        return set()
    return {tok for tok in _TOKEN_SPLIT.split(text.lower()) if tok}


# Cascade table: the first matching row wins (evaluated top to bottom), so order
# matters. Each row maps FR/EN keywords to (occasion_category, formality, dress_code).
# Every row yields a category from OCCASION_CATEGORIES; the final fallback covers
# no-match and None text. Token matching (review-F3); injective (review-F7):
# one text -> exactly one row.
_OCCASION_RULES = (
    (("mariage", "wedding"), "mariage", 5, "tenue de cérémonie"),
    (
        ("church", "funeral", "baptême", "bapteme", "ceremonie", "cérémonie", "communion"),
        "ceremonie",
        5,
        "tenue de cérémonie",
    ),
    (
        (
            "soirée", "soiree", "party", "sortie", "disco", "boîte", "boite",
            "club", "dîner", "diner", "restaurant", "dinner",
        ),
        "soiree",
        3,
        "chic",
    ),
    (
        ("travail", "bureau", "meeting", "réunion", "reunion", "entretien", "interview", "job"),
        "travail",
        4,
        "business casual",
    ),
    (
        ("sport", "gym", "fitness", "running", "footing", "entraînement", "entrainement"),
        "sport",
        1,
        "sportwear",
    ),
    (("plage", "beach", "mer", "baignade", "pool", "piscine"), "plage", 1, "décontracté"),
    (
        ("voyage", "trip", "vacances", "airport", "aéroport", "avion", "train"),
        "voyage",
        2,
        "confortable",
    ),
)

_FALLBACK_CATEGORY = "casual_quotidien"
_FALLBACK_FORMALITY = 2
_FALLBACK_DRESS_CODE = None


def parse_occasion_rules(text: str | None) -> dict:
    """Deterministic, injective parser: a free-text occasion -> exactly one category.

    Returns ``{"occasion_category", "formality", "dress_code"}`` where
    ``occasion_category`` is always a member of ``OCCASION_CATEGORIES`` (never
    ``None``, never out-of-vocabulary). Keyword matching is by whole-word token
    (review-F3), evaluated in cascade — the first matching row wins — with a
    deterministic fallback to ``casual_quotidien`` when ``text`` is ``None`` or no
    keyword matches.
    """
    tokens = _tokens(text)
    for keywords, category, formality, dress_code in _OCCASION_RULES:
        if any(keyword in tokens for keyword in keywords):
            return {
                "occasion_category": category,
                "formality": formality,
                "dress_code": dress_code,
            }
    return {
        "occasion_category": _FALLBACK_CATEGORY,
        "formality": _FALLBACK_FORMALITY,
        "dress_code": _FALLBACK_DRESS_CODE,
    }

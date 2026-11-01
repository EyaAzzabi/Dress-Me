"""CriticAgent — LLM-as-a-Judge with a deterministic fallback.

Evaluates an outfit on a 5-criterion grid (5 pts each, 25 max).
Approved when total >= 15.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_WEATHER_BAND_SEASONS = {
    "chaud": {"ete", "printemps"},
    "froid": {"hiver", "automne"},
    "modere": {"printemps", "automne", "toutes_saisons"},
}

_FORMAL_CATEGORIES = {"mariage", "ceremonie", "soiree", "travail"}
_CASUAL_CATEGORIES = {"casual_quotidien", "sport", "plage", "voyage"}

_CRITERION_LABELS = {
    "meteo": "Météo adaptée",
    "occasion": "Occasion appropriée",
    "couleurs": "Harmonie des couleurs",
    "completude": "Tenue complète",
    "fraicheur": "Fraîcheur",
}


class CriticAgent:
    """Evaluate a proposed outfit and return a structured score dict."""

    def __init__(self, llm_agent: Any | None = None) -> None:
        self._llm = llm_agent

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        outfit_items: list[dict],
        context: dict,
        style_guidelines: list[str],
    ) -> dict:
        """Evaluate the outfit.

        Parameters
        ----------
        outfit_items:
            List of dicts: {id, category, colors, style, season}.
        context:
            {occasion, occasion_category, weather_band, temperature,
             season, recent_item_ids}.
        style_guidelines:
            Up to 3 strings from StyleRAG.retrieve().

        Returns
        -------
        {scores: {meteo,occasion,couleurs,completude,fraicheur},
         total: int, approved: bool, feedback: str}
        """
        # Try LLM path first
        if self._llm is not None:
            try:
                result = self._llm_score(outfit_items, context, style_guidelines)
                if result is not None:
                    return result
            except Exception:  # noqa: BLE001
                logger.warning("CriticAgent LLM path failed; using deterministic fallback", exc_info=True)

        return self._deterministic_score(outfit_items, context)

    # ------------------------------------------------------------------
    # LLM path
    # ------------------------------------------------------------------

    def _llm_score(
        self,
        outfit_items: list[dict],
        context: dict,
        style_guidelines: list[str],
    ) -> dict | None:
        items_text = "\n".join(
            f"  - id={it.get('id')} category={it.get('category')} "
            f"colors={it.get('colors')} style={it.get('style')} season={it.get('season')}"
            for it in outfit_items
        )
        guidelines_text = "\n".join(f"  • {g}" for g in style_guidelines) or "  (none)"

        system_msg = {
            "role": "system",
            "content": (
                "Tu es un critique de mode expert. "
                "Tu dois évaluer une tenue sur 5 critères, chacun noté de 0 à 5. "
                "Réponds UNIQUEMENT avec un JSON valide correspondant au schéma demandé."
            ),
        }
        user_msg = {
            "role": "user",
            "content": (
                f"Tenue proposée:\n{items_text}\n\n"
                f"Contexte: occasion={context.get('occasion')}, "
                f"occasion_category={context.get('occasion_category')}, "
                f"weather_band={context.get('weather_band')}, "
                f"temperature={context.get('temperature')}°C, "
                f"season={context.get('season')}\n\n"
                f"Guidelines de style:\n{guidelines_text}\n\n"
                "Évalue sur ces 5 critères (0–5 chacun):\n"
                "  meteo      — pièces adaptées à la météo/température\n"
                "  occasion   — style approprié à l'occasion\n"
                "  couleurs   — harmonie des couleurs\n"
                "  completude — tenue complète (haut/robe + bas/robe + chaussures)\n"
                "  fraicheur  — pièces non portées récemment\n\n"
                "Réponds avec ce JSON exact:\n"
                '{"scores": {"meteo": <int>, "occasion": <int>, "couleurs": <int>, '
                '"completude": <int>, "fraicheur": <int>}, '
                '"total": <int>, "approved": <bool>, "feedback": "<une phrase>"}'
            ),
        }

        raw = self._llm._chat(
            [system_msg, user_msg],
            json_mode=True,
            timeout=10.0,
        )
        if not raw:
            return None

        data = json.loads(raw) if isinstance(raw, str) else raw
        # Validate required keys
        scores = data["scores"]
        for key in ("meteo", "occasion", "couleurs", "completude", "fraicheur"):
            if key not in scores:
                raise ValueError(f"Missing criterion: {key}")

        total = int(sum(scores[k] for k in scores))
        approved = total >= 15
        return {
            "scores": {k: int(v) for k, v in scores.items()},
            "total": total,
            "approved": approved,
            "feedback": str(data.get("feedback", "")),
        }

    # ------------------------------------------------------------------
    # Deterministic fallback
    # ------------------------------------------------------------------

    def _deterministic_score(
        self,
        outfit_items: list[dict],
        context: dict,
    ) -> dict:
        scores: dict[str, int] = {}

        # ---- meteo ----
        weather_band = context.get("weather_band") or ""
        good_seasons = _WEATHER_BAND_SEASONS.get(weather_band, set())
        item_seasons = {
            it.get("season")
            for it in outfit_items
            if it.get("season") not in (None, "toutes_saisons")
        }
        if not item_seasons or not good_seasons:
            scores["meteo"] = 3  # unknown → neutral
        elif item_seasons.issubset(good_seasons):
            scores["meteo"] = 5
        elif item_seasons & good_seasons:
            scores["meteo"] = 3
        else:
            scores["meteo"] = 1

        # ---- occasion ----
        occasion_cat = context.get("occasion_category") or ""
        cats = {it.get("category", "") for it in outfit_items}
        has_shoes = "chaussures" in cats
        if occasion_cat in _FORMAL_CATEGORIES and has_shoes:
            scores["occasion"] = 5
        elif occasion_cat in _FORMAL_CATEGORIES and not has_shoes:
            scores["occasion"] = 3
        else:
            scores["occasion"] = 4  # casual → generally fine

        # ---- couleurs ----
        all_colors: list[str] = []
        for it in outfit_items:
            raw = it.get("colors", [])
            if isinstance(raw, list):
                all_colors.extend(raw)
            elif isinstance(raw, str):
                all_colors.append(raw)
        n_colors = len(set(all_colors))
        if n_colors <= 2:
            scores["couleurs"] = 5
        elif n_colors == 3:
            scores["couleurs"] = 4
        elif n_colors == 4:
            scores["couleurs"] = 2
        else:
            scores["couleurs"] = 1

        # ---- completude ----
        cats_set = {it.get("category", "") for it in outfit_items}
        has_top = bool(cats_set & {"haut", "robe"})
        has_bot = bool(cats_set & {"bas", "robe"})
        if has_top and has_bot and has_shoes:
            scores["completude"] = 5
        elif has_top and has_bot:
            scores["completude"] = 3
        else:
            scores["completude"] = 1

        # ---- fraicheur ----
        recent_ids = set(context.get("recent_item_ids") or [])
        outfit_ids = {it.get("id") for it in outfit_items if it.get("id")}
        overlap = len(outfit_ids & recent_ids)
        if overlap == 0:
            scores["fraicheur"] = 5
        elif overlap == 1:
            scores["fraicheur"] = 3
        else:
            scores["fraicheur"] = 1

        total = sum(scores.values())
        approved = total >= 15

        # Build feedback from lowest-scoring criterion
        worst = min(scores, key=lambda k: scores[k])
        feedback_map = {
            "meteo": "Les pièces ne sont pas toutes adaptées à la météo actuelle.",
            "occasion": "La tenue manque de cohérence avec l'occasion visée.",
            "couleurs": "Trop de couleurs différentes — réduis à 3 au maximum.",
            "completude": "La tenue n'est pas complète (haut, bas et chaussures nécessaires).",
            "fraicheur": "Certaines pièces ont été portées récemment.",
        }
        feedback = feedback_map.get(worst, "La tenue peut être améliorée.")
        if approved:
            feedback = "Tenue validée par le Critic. " + feedback

        return {
            "scores": scores,
            "total": total,
            "approved": approved,
            "feedback": feedback,
        }

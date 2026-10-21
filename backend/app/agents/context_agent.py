from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent
from app.agents.llm_agent import LLMAgent
from app.services import occasions
from app.services.seasons import normalize_season, season_from_temperature
from app.services.weather import WeatherService


class ContextAgent(BaseAgent):
    """Resolves the request's situational context: occasion, weather, season,
    and any explicit constraints (color, style, dress code, budget).

    Per the architecture doc (docs/), intended approach is LLM + rules: an LLM
    parses free-text context (e.g. "je vais a un mariage ce soir") into structured
    fields, validated/completed by rule-based lookups (e.g. the weather service).
    The free-text parsing side is LLMAgent's job, not this one — this agent only does
    the rule-based completion: filling in `weather` from a real lookup when the caller
    gives a `city` but not `weather` directly. `season` is normalized to the wardrobe
    vocabulary (ete / hiver / mi_saison) and, when not given, inferred from the looked-up
    temperature — so downstream agents can filter the wardrobe on it.

    Enriched (axe 3) to also return ``occasion_category`` / ``formality`` / ``dress_code``
    (parsed by the injected ``LLMAgent`` when a provider is configured, else the
    deterministic ``occasions.parse_occasion_rules`` fallback) plus ``temperature`` and
    ``weather_band`` (derived from the looked-up temperature). The legacy keys
    ``occasion`` / ``weather`` / ``season`` are preserved unchanged for backward
    compatibility (review-F6), so existing consumers keep working.
    """

    name = "context_agent"

    def __init__(self, llm_agent: LLMAgent | None = None) -> None:
        self.weather_service = WeatherService()
        # Injected for testability; default constructed for production. The LLM is
        # optional everywhere: provider == "none" -> parse_occasion returns None and we
        # fall back to occasions.parse_occasion_rules without any network call.
        self.llm_agent = llm_agent or LLMAgent()

    def run(
        self, *, occasion: str | None = None, weather: str | None = None,
        season: str | None = None, city: str | None = None,
    ) -> dict[str, Any]:
        temperature = None
        if weather is None and city is not None:
            data = self._lookup(city)
            if data is not None:
                weather, temperature = self._describe(data), data["main"]["temp"]
        season = normalize_season(season)
        if season is None and temperature is not None:
            season = season_from_temperature(temperature)
        # Parse the occasion after the lookup so the hints reflect the resolved
        # season/weather (review-F9). LLM first when available, else deterministic rules.
        parsed = self.llm_agent.parse_occasion(
            occasion, {"season": season, "weather": weather}
        )
        if parsed is None:
            parsed = occasions.parse_occasion_rules(occasion)
        return {
            "occasion": occasion,
            "weather": weather,
            "season": season,
            "temperature": temperature,
            "weather_band": occasions.weather_band(temperature),
            "occasion_category": parsed["occasion_category"],
            "formality": parsed["formality"],
            "dress_code": parsed["dress_code"],
        }

    def _lookup(self, city: str) -> dict | None:
        return self.weather_service.get_current_weather(city)  # None: no API key, or lookup failed

    @staticmethod
    def _describe(data: dict) -> str:
        return f"{data['weather'][0]['description']}, {data['main']['temp']:.0f}°C"

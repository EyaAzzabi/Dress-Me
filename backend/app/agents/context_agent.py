from typing import Any

from app.agents.base import BaseAgent
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
    """

    name = "context_agent"

    def __init__(self) -> None:
        self.weather_service = WeatherService()

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
        return {"occasion": occasion, "weather": weather, "season": season}

    def _lookup(self, city: str) -> dict | None:
        return self.weather_service.get_current_weather(city)  # None: no API key, or lookup failed

    @staticmethod
    def _describe(data: dict) -> str:
        return f"{data['weather'][0]['description']}, {data['main']['temp']:.0f}°C"

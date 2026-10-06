from typing import Any

from app.agents.base import BaseAgent
from app.services.weather import WeatherService


class ContextAgent(BaseAgent):
    """Resolves the request's situational context: occasion, weather, season,
    and any explicit constraints (color, style, dress code, budget).

    Per the architecture doc (docs/), intended approach is LLM + rules: an LLM
    parses free-text context (e.g. "je vais a un mariage ce soir") into structured
    fields, validated/completed by rule-based lookups (e.g. the weather service).
    The free-text parsing side is LLMAgent's job, not this one — this agent only does
    the rule-based completion: filling in `weather` from a real lookup when the caller
    gives a `city` but not `weather` directly.
    """

    name = "context_agent"

    def __init__(self) -> None:
        self.weather_service = WeatherService()

    def run(
        self, *, occasion: str | None = None, weather: str | None = None,
        season: str | None = None, city: str | None = None,
    ) -> dict[str, Any]:
        if weather is None and city is not None:
            weather = self._lookup_weather(city)
        return {"occasion": occasion, "weather": weather, "season": season}

    def _lookup_weather(self, city: str) -> str | None:
        data = self.weather_service.get_current_weather(city)
        if data is None:  # no OPENWEATHER_API_KEY configured, or the lookup failed
            return None
        description = data["weather"][0]["description"]
        temp = data["main"]["temp"]
        return f"{description}, {temp:.0f}°C"

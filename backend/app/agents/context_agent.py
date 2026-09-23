from typing import Any

from app.agents.base import BaseAgent


class ContextAgent(BaseAgent):
    """Resolves the request's situational context: occasion, weather, season,
    and any explicit constraints (color, style, dress code, budget).
    """

    name = "context_agent"

    def run(self, *, occasion: str | None = None, weather: str | None = None, season: str | None = None) -> dict[str, Any]:
        # TODO: enrich with the weather service when weather isn't provided
        return {"occasion": occasion, "weather": weather, "season": season}

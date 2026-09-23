from typing import Any

from app.agents.base import BaseAgent
from app.core.config import get_settings


class LLMAgent(BaseAgent):
    """Optional agent that turns structured agent outputs into natural-language
    explanations and conversational responses (GPT / LLaMA / Mistral).
    """

    name = "llm_agent"

    def __init__(self) -> None:
        self.settings = get_settings()

    def run(self, *, context: dict[str, Any]) -> dict[str, Any]:
        if self.settings.llm_provider == "none":
            return {"explanation": None}
        # TODO: call the configured LLM provider with `context` to produce
        # a natural-language explanation / conversational reply
        raise NotImplementedError

from typing import Any

import httpx

from app.agents.base import BaseAgent
from app.core.config import get_settings

# All three providers speak the same OpenAI-compatible chat/completions schema —
# including self-hosted Llama via vLLM/Ollama/Together — so one client handles all of
# them. openai/mistral have one well-known host; "llama" has none, so both
# llm_base_url and llm_model must be set explicitly for it (see Settings).
_PROVIDER_DEFAULTS = {
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    "mistral": {"base_url": "https://api.mistral.ai/v1", "model": "mistral-small-latest"},
    "llama": {"base_url": None, "model": None},
}


class LLMAgent(BaseAgent):
    """Optional agent that turns structured agent outputs into natural-language
    explanations and conversational responses (GPT / LLaMA / Mistral).

    Never asked to compute or invent facts (wardrobe counts, scores, ...) — those come
    from real aggregation elsewhere (e.g. StyleProfileAgent) and are only *phrased* here.
    Returns {"explanation": None} rather than raising when no provider is configured
    (the default for a prototype deployment), so callers can treat the narrative as
    optional without special-casing "none" everywhere.
    """

    name = "llm_agent"

    def __init__(self) -> None:
        self.settings = get_settings()

    def run(self, *, context: dict[str, Any], instruction: str) -> dict[str, Any]:
        if self.settings.llm_provider == "none":
            return {"explanation": None}

        base_url, model = self._resolve_provider()
        response = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.settings.llm_api_key}"},
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are DressMe's styling assistant. Use only the facts given "
                            "in the user message — never invent counts, items, or scores "
                            "that weren't provided."
                        ),
                    },
                    {"role": "user", "content": f"{instruction}\n\nFacts:\n{context}"},
                ],
                "temperature": 0.7,
            },
            timeout=20.0,
        )
        response.raise_for_status()
        explanation = response.json()["choices"][0]["message"]["content"]
        return {"explanation": explanation}

    def _resolve_provider(self) -> tuple[str, str]:
        provider = self.settings.llm_provider
        if provider not in _PROVIDER_DEFAULTS:
            raise ValueError(f"Unknown llm_provider: {provider!r}")

        defaults = _PROVIDER_DEFAULTS[provider]
        base_url = self.settings.llm_base_url or defaults["base_url"]
        model = self.settings.llm_model or defaults["model"]
        if not base_url or not model:
            raise ValueError(
                f"llm_provider={provider!r} needs LLM_BASE_URL and LLM_MODEL set explicitly "
                "(no single standard host/model for self-hosted Llama)."
            )
        return base_url, model

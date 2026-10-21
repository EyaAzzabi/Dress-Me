from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.agents.base import BaseAgent
from app.agents.prompts import explain_outfit_prompt, occasion_parse_prompt
from app.core.config import get_settings
from app.services.occasions import OCCASION_CATEGORIES

logger = logging.getLogger(__name__)

# Controlled vocabulary for the dress_code field the occasion-parsing LLM may return
# (review-F8): a free-form string from the model is validated against this small set,
# and anything outside it is dropped to None rather than rejected wholesale (a bad
# dress_code shouldn't void an otherwise-valid parse — ContextAgent falls back to the
# rules' dress_code only when the whole parse is None).
_DRESS_CODE_VOCABULARY = {
    "tenue de cérémonie",
    "chic",
    "business casual",
    "sportwear",
    "décontracté",
    "confortable",
}

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

        messages = [
            {
                "role": "system",
                "content": (
                    "You are DressMe's styling assistant. Use only the facts given "
                    "in the user message — never invent counts, items, or scores "
                    "that weren't provided."
                ),
            },
            {"role": "user", "content": f"{instruction}\n\nFacts:\n{context}"},
        ]
        explanation = self._chat(messages)
        return {"explanation": explanation}

    def parse_occasion(
        self, raw_occasion: str | None, context_hints: dict[str, Any]
    ) -> dict[str, Any] | None:
        # provider == "none" guard is the FIRST line, before _chat/_resolve_provider,
        # so no httpx.post is ever emitted when the LLM is off (review-F11) — the
        # test_no_provider_returns_none_without_a_network_call invariant holds here too.
        if self.settings.llm_provider == "none":
            return None
        try:
            content = self._chat(
                occasion_parse_prompt(raw_occasion, context_hints), json_mode=True
            )
            parsed = json.loads(content)
        except Exception:
            # HTTP non-2xx (raise_for_status), timeout, invalid JSON, missing fields —
            # any failure falls back to the deterministic rules parser in ContextAgent.
            logger.warning(
                "LLMAgent.parse_occasion: LLM/JSON failure, falling back to rules",
                exc_info=True,
            )
            return None

        category = parsed.get("occasion_category")
        if category not in OCCASION_CATEGORIES:
            logger.warning(
                "LLMAgent.parse_occasion: occasion_category %r not in vocabulary, "
                "falling back to rules",
                category,
            )
            return None
        formality = parsed.get("formality")
        # bool is a subclass of int in Python — reject it explicitly; a JSON true/false
        # is not a valid formality. Only a real int in [1, 5] is accepted.
        if isinstance(formality, bool) or not isinstance(formality, int) or not 1 <= formality <= 5:
            logger.warning(
                "LLMAgent.parse_occasion: formality %r out of range [1,5], "
                "falling back to rules",
                formality,
            )
            return None
        dress_code = parsed.get("dress_code")
        # review-F8: sanitize a free-form dress_code against the controlled vocabulary;
        # an out-of-vocab value is dropped to None, not treated as a hard failure.
        if dress_code not in _DRESS_CODE_VOCABULARY:
            dress_code = None
        return {
            "occasion_category": category,
            "formality": formality,
            "dress_code": dress_code,
        }

    def explain_outfit(self, facts: dict[str, Any]) -> str | None:
        # provider == "none" guard FIRST, before _chat (review-F11): no network call.
        if self.settings.llm_provider == "none":
            return None
        try:
            return self._chat(explain_outfit_prompt(facts))
        except Exception:
            logger.warning(
                "LLMAgent.explain_outfit: LLM failure, falling back to template",
                exc_info=True,
            )
            return None

    def _chat(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
        timeout: float = 20.0,
    ) -> str:
        """POST the messages to the provider's /chat/completions and return the text.

        Shared by ``run``, ``parse_occasion`` and ``explain_outfit``. Raises on any
        non-2xx (``raise_for_status``) or transport error; callers that have a fallback
        wrap this in try/except (``parse_occasion``/``explain_outfit``), while ``run``
        lets it propagate to its existing tests.
        """
        base_url, model = self._resolve_provider()
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        response = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.settings.llm_api_key}"},
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

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

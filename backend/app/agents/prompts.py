"""Structured prompt builders for the DressMe LLMAgent (axe 3 — prompt engineering).

These are pure functions: they only assemble the ``messages`` list for an
OpenAI-compatible ``/chat/completions`` call and never touch the network. That keeps
them unit-testable in isolation (see ``tests/test_prompts.py``) and lets the
``LLMAgent`` stay a thin client: it owns the ``provider == "none"`` guard and the HTTP
call, these own the wording.

Two capabilities, two builders (one LLM call per capability, per the design):

- ``occasion_parse_prompt`` — turn free-text occasion into a single JSON object
  ``{"occasion_category", "formality", "dress_code", "notes"}``. The caller passes
  already-known hints (season/weather) so the model can disambiguate; ``json_mode`` is
  set on the request by ``LLMAgent.parse_occasion`` (``response_format`` is a request
  field, not a message), not here.
- ``explain_outfit_prompt`` — in 1-2 sentences, explain why an outfit fits the
  occasion/weather using *only* the provided facts, and add up to 1-2 concrete
  adjustment suggestions with their reason. Never invent pieces, scores or counts.
"""

from __future__ import annotations

import json
from typing import Any

_OCCASION_PARSE_SYSTEM = (
    "Tu es l'assistant stylistique DressMe. À partir du texte libre, renvoie "
    'uniquement un JSON {"occasion_category": <une des 8 catégories>, '
    '"formality": <1-5>, "dress_code": <str|null>, "notes": <str|null>}. '
    "Si incertain, choisis casual_quotidien. N'invente rien d'autre."
)

_EXPLAIN_OUTFIT_SYSTEM = (
    "Tu es l'assistant stylistique DressMe. Génère une description narrative et engageante "
    "de la tenue qui explique pourquoi elle convient parfaitement à l'occasion et aux conditions "
    "(météo, saison). Utilise les faits fournis pour justifier les choix, sans inventer de pièces "
    "ou scores. Sois spécifique : par exemple, explique pourquoi une couleur ou une pièce "
    "fonctionne pour cette occasion. 2–3 phrases, engageantes et naturelles."
)


def occasion_parse_prompt(
    raw_occasion: str | None, context_hints: dict[str, Any]
) -> list[dict[str, str]]:
    """Build the messages for parsing a free-text occasion into structured JSON.

    The user message carries the raw occasion text plus the context already known
    upstream (season/weather from ``ContextAgent``), so the model can disambiguate
    ambiguous phrases. ``response_format`` json_object is set on the HTTP request by
    the caller, not in these messages.
    """
    raw = raw_occasion if raw_occasion is not None else ""
    hints = json.dumps(context_hints or {}, ensure_ascii=False, sort_keys=True)
    user = f"Occasion : {raw}\nIndices : {hints}"
    return [
        {"role": "system", "content": _OCCASION_PARSE_SYSTEM},
        {"role": "user", "content": user},
    ]


def explain_outfit_prompt(facts: dict[str, Any]) -> list[dict[str, str]]:
    """Build the messages for explaining an outfit from the provided facts only.

    The facts (items, scores, context, historical/catalogue references) are
    serialized as JSON in the user message; the system message forbids inventing
    pieces, scores or counts that were not provided, keeping the LLM a phrasing layer.
    """
    user_request = facts.get("context", {}).get("user_request") or "une occasion"
    user_msg = (
        f"Tu dois générer une description NATURELLE et ENGAGEANTE pour cette tenue "
        f"qui convient à: {user_request}\n\n"
        f"Utilise UNIQUEMENT les faits fournis (pièces, couleurs, styles). "
        f"Ne sois pas robuste ou pédant — sois plutôt personnel et naturel.\n\n"
        f"Faits disponibles (JSON):\n{json.dumps(facts or {}, ensure_ascii=False, sort_keys=True)}"
    )
    return [
        {"role": "system", "content": _EXPLAIN_OUTFIT_SYSTEM},
        {"role": "user", "content": user_msg},
    ]

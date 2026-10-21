"""Tests for the structured prompt builders (FEAT-004, axe 3).

These are pure functions — no network — so the tests only assert the shape and
content of the returned ``messages`` list (roles + system/user contents). The
system messages are the verbatim wording the design pins; the user messages carry
the raw occasion/hints or the serialized facts.
"""

import json

from app.agents.prompts import explain_outfit_prompt, occasion_parse_prompt

_OCCASION_PARSE_SYSTEM = (
    "Tu es l'assistant stylistique DressMe. À partir du texte libre, renvoie "
    'uniquement un JSON {"occasion_category": <une des 8 catégories>, '
    '"formality": <1-5>, "dress_code": <str|null>, "notes": <str|null>}. '
    "Si incertain, choisis casual_quotidien. N'invente rien d'autre."
)

_EXPLAIN_OUTFIT_SYSTEM = (
    "Tu es l'assistant stylistique DressMe. En 1–2 phrases, explique pourquoi "
    "cette tenue convient à l'occasion/météo, en n'utilisant que les faits fournis. "
    "N'invente jamais de pièces, scores ou comptes non fournis. Si justifié, "
    "ajoute 1–2 suggestions d'ajustement concrètes avec leur raison."
)


def test_occasion_parse_prompt_returns_system_then_user_messages():
    messages = occasion_parse_prompt(
        "je vais a un mariage ce soir", {"season": "ete", "weather": None}
    )

    assert len(messages) == 2
    assert messages[0] == {"role": "system", "content": _OCCASION_PARSE_SYSTEM}
    assert messages[1]["role"] == "user"
    # The user message carries the raw occasion text and the context hints.
    assert "je vais a un mariage ce soir" in messages[1]["content"]
    assert "ete" in messages[1]["content"]


def test_occasion_parse_prompt_handles_none_occasion_without_crashing():
    messages = occasion_parse_prompt(None, {"season": None, "weather": None})

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


def test_explain_outfit_prompt_returns_system_then_user_messages():
    facts = {"occasion": "mariage", "weather_band": "chaud", "score": 0.8}
    messages = explain_outfit_prompt(facts)

    assert len(messages) == 2
    assert messages[0] == {"role": "system", "content": _EXPLAIN_OUTFIT_SYSTEM}
    assert messages[1]["role"] == "user"
    # The user message is the facts serialized as JSON (decodable, round-trips).
    assert json.loads(messages[1]["content"]) == facts


def test_explain_outfit_prompt_handles_empty_facts():
    messages = explain_outfit_prompt({})

    assert len(messages) == 2
    assert messages[1]["content"] == "{}"

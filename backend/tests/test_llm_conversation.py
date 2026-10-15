"""Flexible conversation regression tests: prose, memory and reference boundaries."""
from copy import deepcopy
import json

import httpx
import pytest

from app.agents.llm_agent import LLMAgent
from app.core.config import Settings
from app.services.llm_conversation import build_conversation_plan

FACTS = {"question": "Comment styler ce bas noir ?", "selected_item_ref": "p1",
         "items": [{"ref": "p1", "category": "bas", "colors": ["noir"]},
                   {"ref": "p2", "category": "haut", "colors": ["blanc"]}],
         "history": [{"role": "user", "content": "Je veux être à l'aise."},
                     {"role": "assistant", "content": "Partons sur une tenue simple et confortable."}]}
ANSWER = {"answer": "Tu peux créer un contraste net avec ton haut blanc, puis adapter la mise en tenue à ton occasion.",
          "ideas": [{"title": "Contraste simple", "advice": "Associe le bas noir au haut blanc. Rentre légèrement le haut si sa coupe le permet.",
                     "item_refs": ["p1", "p2"], "optional_additions": []}],
          "item_refs": ["p1", "p2"], "follow_up": "Tu veux une version quotidienne ou plus habillée ?"}


def test_real_generated_advice_is_allowed_instead_of_prebuilt_sentences():
    parsed = json.loads(build_conversation_plan(FACTS).render(json.dumps(ANSWER)))
    assert parsed == ANSWER
    assert "Rentre légèrement" in parsed["ideas"][0]["advice"]


def test_nonexistent_wardrobe_references_are_rejected():
    answer = deepcopy(ANSWER)
    answer["ideas"][0]["item_refs"].append("invented-jacket")
    with pytest.raises(ValueError):
        build_conversation_plan(FACTS).render(json.dumps(answer))


def test_only_my_wardrobe_cannot_introduce_optional_additions():
    answer = deepcopy(ANSWER)
    answer["ideas"][0]["optional_additions"] = ["Une ceinture à prévoir"]
    with pytest.raises(ValueError):
        build_conversation_plan({**FACTS, "wardrobe_only": True}).render(json.dumps(answer))
    assert build_conversation_plan(FACTS).render(json.dumps(answer))


def test_extra_score_or_verdict_fields_are_forbidden():
    with pytest.raises(ValueError):
        build_conversation_plan(FACTS).render(json.dumps({**ANSWER, "verdict": "recommended"}))


def test_internal_aliases_do_not_appear_in_displayed_prose():
    answer = {**ANSWER, "answer": "Associe p1 à p2 (p2)."}
    parsed = json.loads(build_conversation_plan(FACTS).render(json.dumps(answer)))
    assert parsed["answer"] == "Associe bas noir à haut blanc."


def test_model_receives_full_dialogue_and_latest_question_last():
    messages = build_conversation_plan(FACTS).messages(json.dumps({"facts": FACTS}))
    assert messages[-1] == {"role": "user", "content": FACTS["question"]}
    assert messages[-2] == FACTS["history"][-1]
    assert messages[0]["role"] == "system" and "conseil" in messages[0]["content"]


def test_empty_wardrobe_allows_general_fashion_advice():
    facts = {"question": "Comment choisir des couleurs pour un entretien ?", "items": []}
    answer = {"answer": "Tu peux partir d'une base sobre et ajouter une touche de couleur discrète.", "ideas": [], "item_refs": [], "follow_up": "Dans quel secteur ?"}
    assert build_conversation_plan(facts).render(json.dumps(answer))


def test_generic_bottom_does_not_become_a_confirmed_pair_of_trousers():
    answer = json.loads(build_conversation_plan(FACTS).render(json.dumps({**ANSWER, "answer": "Ton pantalon noir peut servir de base."})))
    assert answer["answer"] == "Ton bas noir peut servir de base."
    # An explicit user clarification can supply the missing garment type.
    facts = {**FACTS, "question": "C'est un pantalon noir, comment le porter ?"}
    assert build_conversation_plan(facts).render(json.dumps({**ANSWER, "answer": "Ton pantalon noir peut être porté avec le haut blanc."}))


def test_one_bounded_repair_corrects_an_unknown_wardrobe_reference(monkeypatch):
    settings = Settings(_env_file=None, llm_provider="groq", llm_api_key="test-placeholder", llm_model="openai/gpt-oss-120b")
    requests = []
    def post(url, **kw):
        requests.append(kw["json"].copy())
        answer = {**ANSWER, "item_refs": ["invented-jacket"]} if len(requests) == 1 else ANSWER
        return httpx.Response(200, request=httpx.Request("POST", url), json={"choices": [{"message": {"content": json.dumps(answer)}, "finish_reason": "stop"}]})
    monkeypatch.setattr("httpx.post", post)
    LLMAgent.clear_cache()
    try:
        result = LLMAgent(settings=settings).run(task="assistant", context=FACTS, instruction="", cache_scope="repair-test")
        assert json.loads(result["explanation"]) == ANSWER
        assert len(requests) == 2 and "n'existe pas" in requests[1]["messages"][-1]["content"]
    finally:
        LLMAgent.clear_cache()


def test_conversation_provider_uses_generated_schema_and_memory_cache(monkeypatch):
    settings = Settings(_env_file=None, llm_provider="groq", llm_api_key="test-placeholder", llm_model="openai/gpt-oss-120b")
    requests = []
    def post(url, **kw):
        requests.append(kw["json"])
        return httpx.Response(200, request=httpx.Request("POST", url), json={"choices": [{"message": {"content": json.dumps(ANSWER)}, "finish_reason": "stop"}]})
    monkeypatch.setattr("httpx.post", post)
    LLMAgent.clear_cache()
    try:
        agent = LLMAgent(settings=settings)
        for _ in range(2):
            assert json.loads(agent.run(task="assistant", context=FACTS, instruction="Conseil", cache_scope="user1")["explanation"]) == ANSWER
        assert len(requests) == 1
        assert requests[0]["response_format"]["json_schema"]["name"] == "dressme_conversation"
        assert requests[0]["reasoning_effort"] == "medium"
        assert requests[0]["max_completion_tokens"] == 3072
        assert requests[0]["messages"][-2]["role"] == "assistant"
        agent.run(task="assistant", context={**FACTS, "question": "Et le soir ?"}, instruction="Conseil", cache_scope="user1")
        assert len(requests) == 2
    finally:
        LLMAgent.clear_cache()


def test_native_json_generation_failure_has_one_locally_validated_fallback(monkeypatch):
    settings = Settings(_env_file=None, llm_provider="groq", llm_api_key="test-placeholder", llm_model="openai/gpt-oss-120b")
    formats = []
    def post(url, **kw):
        formats.append(kw["json"]["response_format"]["type"])
        if len(formats) == 1:
            return httpx.Response(400, request=httpx.Request("POST", url), json={"error": {"code": "json_validate_failed"}})
        return httpx.Response(200, request=httpx.Request("POST", url), json={"choices": [{"message": {"content": json.dumps(ANSWER)}}]})
    monkeypatch.setattr("httpx.post", post)
    LLMAgent.clear_cache()
    try:
        result = LLMAgent(settings=settings).run(task="assistant", context=FACTS, instruction="", cache_scope="native-json-test")
        assert json.loads(result["explanation"]) == ANSWER
        assert formats == ["json_schema", "json_object"]
    finally:
        LLMAgent.clear_cache()

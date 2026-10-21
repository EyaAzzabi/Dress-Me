import httpx
import pytest

from app.agents.llm_agent import LLMAgent
from app.core.config import Settings


def _agent_with_settings(monkeypatch, **overrides) -> LLMAgent:
    overrides.setdefault("llm_provider", "none")
    settings = Settings(**overrides)
    monkeypatch.setattr("app.agents.llm_agent.get_settings", lambda: settings)
    return LLMAgent()


def test_no_provider_returns_none_without_a_network_call(monkeypatch):
    called = False

    def fail_if_called(*a, **k):
        nonlocal called
        called = True

    monkeypatch.setattr("httpx.post", fail_if_called)
    agent = _agent_with_settings(monkeypatch, llm_provider="none")

    result = agent.run(context={"wardrobe_size": 3}, instruction="describe this wardrobe")

    assert result == {"explanation": None}
    assert not called


def test_openai_provider_uses_default_host_and_model(monkeypatch):
    captured = {}

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "A clean, casual wardrobe."}}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return _FakeResponse()

    monkeypatch.setattr("httpx.post", fake_post)
    agent = _agent_with_settings(monkeypatch, llm_provider="openai", llm_api_key="sk-test")

    result = agent.run(context={"wardrobe_size": 3}, instruction="describe this wardrobe")

    assert result == {"explanation": "A clean, casual wardrobe."}
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["json"]["model"] == "gpt-4o-mini"


def test_llama_without_base_url_raises_a_clear_error(monkeypatch):
    agent = _agent_with_settings(monkeypatch, llm_provider="llama")

    with pytest.raises(ValueError, match="LLM_BASE_URL"):
        agent.run(context={}, instruction="describe this wardrobe")


def test_llama_with_explicit_base_url_and_model_works(monkeypatch):
    captured = {}

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return _FakeResponse()

    monkeypatch.setattr("httpx.post", fake_post)
    agent = _agent_with_settings(
        monkeypatch, llm_provider="llama",
        llm_base_url="http://localhost:11434/v1", llm_model="llama3",
    )

    result = agent.run(context={}, instruction="describe this wardrobe")

    assert result == {"explanation": "ok"}
    assert captured["url"] == "http://localhost:11434/v1/chat/completions"
    assert captured["json"]["model"] == "llama3"


# --- parse_occasion / explain_outfit (FEAT-004, axe 3) -------------------------
#
# The provider == "none" guard must be the FIRST line of parse_occasion and
# explain_outfit, before any httpx.post (review-F11). When the LLM is configured,
# parse_occasion validates the JSON against the occasion vocabulary and recovers
# (returns None) on any HTTP/JSON/out-of-vocab/formality failure so ContextAgent can
# fall back to the deterministic rules.


def _fake_post_with_content(content):
    """Return a fake httpx.post whose response body yields ``content``."""
    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": content}}]}

    def fake_post(url, **kwargs):
        return _FakeResponse()

    return fake_post


def test_parse_occasion_returns_none_without_a_network_call_when_provider_none(monkeypatch):
    called = False

    def fail_if_called(*a, **k):
        nonlocal called
        called = True

    monkeypatch.setattr("httpx.post", fail_if_called)
    agent = _agent_with_settings(monkeypatch, llm_provider="none")

    result = agent.parse_occasion("je vais a un mariage", {"season": None, "weather": None})

    assert result is None
    assert not called


def test_explain_outfit_returns_none_without_a_network_call_when_provider_none(monkeypatch):
    called = False

    def fail_if_called(*a, **k):
        nonlocal called
        called = True

    monkeypatch.setattr("httpx.post", fail_if_called)
    agent = _agent_with_settings(monkeypatch, llm_provider="none")

    result = agent.explain_outfit({"occasion": "mariage"})

    assert result is None
    assert not called


def test_parse_occasion_validates_and_returns_the_structured_dict(monkeypatch):
    captured = {}
    content = '{"occasion_category":"mariage","formality":5,"dress_code":"tenue de cérémonie","notes":null}'

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return _fake_post_with_content(content)(url, **kwargs)

    monkeypatch.setattr("httpx.post", fake_post)
    agent = _agent_with_settings(monkeypatch, llm_provider="mistral", llm_api_key="key")

    result = agent.parse_occasion("wedding", {"season": None, "weather": None})

    assert result == {
        "occasion_category": "mariage",
        "formality": 5,
        "dress_code": "tenue de cérémonie",
    }
    assert captured["url"] == "https://api.mistral.ai/v1/chat/completions"
    # json_mode is set on the request so the provider returns a JSON object.
    assert captured["json"]["response_format"] == {"type": "json_object"}
    # notes is intentionally dropped — only the three consumed keys are returned.
    assert "notes" not in result


def test_parse_occasion_recovers_with_none_on_invalid_json(monkeypatch):
    monkeypatch.setattr("httpx.post", _fake_post_with_content("not valid json"))
    agent = _agent_with_settings(monkeypatch, llm_provider="mistral", llm_api_key="key")

    assert agent.parse_occasion("mariage", {}) is None


def test_parse_occasion_recovers_with_none_on_out_of_vocab_category(monkeypatch):
    content = '{"occasion_category":"disco_party","formality":3,"dress_code":"chic"}'
    monkeypatch.setattr("httpx.post", _fake_post_with_content(content))
    agent = _agent_with_settings(monkeypatch, llm_provider="mistral", llm_api_key="key")

    assert agent.parse_occasion("sortie", {}) is None


def test_parse_occasion_recovers_with_none_on_formality_out_of_range(monkeypatch):
    content = '{"occasion_category":"mariage","formality":9,"dress_code":"tenue de cérémonie"}'
    monkeypatch.setattr("httpx.post", _fake_post_with_content(content))
    agent = _agent_with_settings(monkeypatch, llm_provider="mistral", llm_api_key="key")

    assert agent.parse_occasion("mariage", {}) is None


def test_parse_occasion_sanitizes_out_of_vocab_dress_code_to_none(monkeypatch):
    # review-F8: an out-of-vocab dress_code is dropped to None, not a hard failure —
    # the rest of the parse stays valid.
    content = '{"occasion_category":"mariage","formality":5,"dress_code":"nimporte quoi"}'
    monkeypatch.setattr("httpx.post", _fake_post_with_content(content))
    agent = _agent_with_settings(monkeypatch, llm_provider="mistral", llm_api_key="key")

    result = agent.parse_occasion("mariage", {})

    assert result == {"occasion_category": "mariage", "formality": 5, "dress_code": None}


def test_explain_outfit_returns_the_llm_text_when_configured(monkeypatch):
    monkeypatch.setattr("httpx.post", _fake_post_with_content("Une tenue chic pour le mariage."))
    agent = _agent_with_settings(monkeypatch, llm_provider="mistral", llm_api_key="key")

    result = agent.explain_outfit({"occasion": "mariage", "score": 0.8})

    assert result == "Une tenue chic pour le mariage."


def test_explain_outfit_recovers_with_none_on_http_error(monkeypatch):
    request = httpx.Request("POST", "https://api.mistral.ai/v1/chat/completions")
    response = httpx.Response(500, request=request)

    class _ErrorResponse:
        def raise_for_status(self):
            raise httpx.HTTPStatusError("server error", request=request, response=response)

        def json(self):
            return {}

    monkeypatch.setattr("httpx.post", lambda *a, **k: _ErrorResponse())
    agent = _agent_with_settings(monkeypatch, llm_provider="mistral", llm_api_key="key")

    assert agent.explain_outfit({"occasion": "mariage"}) is None

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

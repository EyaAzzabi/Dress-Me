"""Offline provider contract, grounding, quota recovery and cache regression tests."""
from concurrent.futures import ThreadPoolExecutor
import json
import logging
from unittest.mock import Mock

import httpx
import pytest
from pydantic import ValidationError

from app.agents.llm_agent import LLMAgent
from app.core.config import Settings

PROFILE = {"wardrobe_size": 3, "category_counts": {"haut": 2, "bas": 1},
           "favorite_colors": ["noir"], "favorite_styles": ["Casual"]}


def selection(*facts):
    return json.dumps({"sentences": [{"fact": f, "variant": 0} for f in facts]})


def response(content=None, status=200, headers=None, data=None):
    if data is None:
        data = {"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}
    return httpx.Response(status, json=data, headers=headers,
                          request=httpx.Request("POST", "https://provider.test/chat/completions"))


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch):
    LLMAgent.clear_cache()
    monkeypatch.setattr("app.agents.llm_agent.time.sleep", lambda _: None)
    monkeypatch.setattr("app.agents.llm_agent.random.uniform", lambda *a: 0)
    yield
    LLMAgent.clear_cache()


def agent(**kw):
    return LLMAgent(settings=Settings(_env_file=None,
        **{"llm_provider": "groq", "llm_api_key": "unit-test-placeholder", **kw}))


def run(a, **kw):
    return a.run(context=PROFILE, instruction="Décris le profil", **kw)["explanation"]


def test_no_provider_returns_none_without_network(monkeypatch):
    post = Mock(side_effect=AssertionError("Network forbidden"))
    monkeypatch.setattr("httpx.post", post)
    assert run(agent(llm_provider="none")) is None
    post.assert_not_called()


@pytest.mark.parametrize("provider,host,model", [
    ("groq", "https://api.groq.com/openai/v1", "openai/gpt-oss-20b"),
    ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.8-flash"),
    ("ollama", "http://localhost:11434/v1", "qwen2.5:3b"),
    ("openai", "https://api.openai.com/v1", "gpt-4o-mini"),
    ("mistral", "https://api.mistral.ai/v1", "mistral-small-latest"),
])
def test_provider_contract(monkeypatch, provider, host, model):
    post = Mock(return_value=response(selection("composition", "colors")))
    monkeypatch.setattr("httpx.post", post)
    text = run(agent(llm_provider=provider))
    assert text == "Ta garde-robe compte 3 pièces. Les couleurs les plus présentes sont : noir."
    args, kw = post.call_args
    assert args == (host + "/chat/completions",)
    assert kw["json"]["model"] == model
    assert kw["timeout"].connect <= 3
    assert kw["timeout"].read == 8
    assert kw["follow_redirects"] is False
    if provider == "groq":
        schema = kw["json"]["response_format"]["json_schema"]
        assert schema["strict"] is True
        assert schema["schema"]["additionalProperties"] is False
        assert kw["json"]["reasoning_effort"] == "low"
    else:
        assert kw["json"]["response_format"] == {"type": "json_object"}


def test_llama_explicit_url_model_no_auth_required(monkeypatch):
    post = Mock(return_value=response(selection("composition")))
    monkeypatch.setattr("httpx.post", post)
    a = agent(llm_provider="llama", llm_api_key=None,
              llm_base_url="http://localhost:11434/v1/", llm_model="llama3")
    assert run(a)
    assert post.call_args.kwargs["headers"] == {}
    assert post.call_args.kwargs["json"]["model"] == "llama3"


@pytest.mark.parametrize("options", [
    {"llm_provider": "unknown"}, {"llm_provider": "llama"}, {"llm_api_key": None},
    {"llm_base_url": "http://remote.example/v1"},
    {"llm_base_url": "https://key:secret@provider.test/v1"},
    {"llm_base_url": "https://provider.test/v1?key=secret"},
    {"llm_base_url": "file:///tmp/llm"},
])
def test_invalid_configuration_falls_back_without_request(monkeypatch, options):
    post = Mock()
    monkeypatch.setattr("httpx.post", post)
    assert run(agent(**options)) is None
    post.assert_not_called()


def test_llama_diagnostic_preserves_clear_configuration_error():
    with pytest.raises(ValueError, match="LLM_BASE_URL"):
        agent(llm_provider="llama")._resolve_provider()


@pytest.mark.parametrize("field,value", [("llm_timeout_seconds", 0), ("llm_max_retries", 3),
    ("llm_cache_max_entries", 0), ("llm_max_backoff_seconds", 11)])
def test_invalid_resource_limits_rejected(field, value):
    with pytest.raises(ValidationError):
        agent(**{field: value})


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_non_retryable_http_failures(monkeypatch, status):
    post = Mock(return_value=response(status=status))
    monkeypatch.setattr("httpx.post", post)
    assert run(agent()) is None
    assert post.call_count == 1


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
def test_transient_failure_retries_and_recovers(monkeypatch, status):
    post = Mock(side_effect=[response(status=status), response(selection("composition"))])
    monkeypatch.setattr("httpx.post", post)
    assert run(agent()) == "Ta garde-robe compte 3 pièces."
    assert post.call_count == 2


@pytest.mark.parametrize("exc", [httpx.ReadTimeout("sensitive"), httpx.ConnectError("sensitive")])
def test_transport_failures_are_bounded(monkeypatch, exc):
    post = Mock(side_effect=exc)
    monkeypatch.setattr("httpx.post", post)
    assert run(agent(llm_max_retries=2)) is None
    assert post.call_count == 3
    # Provider cooldown also protects different facts/users from a failure storm.
    assert run(agent(), cache_scope="other") is None
    assert post.call_count == 3


def test_exponential_backoff_and_retry_after(monkeypatch):
    delays = []
    monkeypatch.setattr("app.agents.llm_agent.time.sleep", delays.append)
    post = Mock(side_effect=[response(status=503), response(status=429, headers={"retry-after": "0.7"}),
                             response(selection("composition"))])
    monkeypatch.setattr("httpx.post", post)
    assert run(agent(llm_max_retries=2))
    assert delays == [0.25, 0.7]


def test_long_retry_after_falls_back_instead_of_blocking(monkeypatch):
    post = Mock(return_value=response(status=429, headers={"retry-after": "60"}))
    monkeypatch.setattr("httpx.post", post)
    assert run(agent()) is None
    assert run(agent(), cache_scope="another") is None
    assert post.call_count == 1


@pytest.mark.parametrize("data", [None, {}, {"choices": []}, {"choices": [None]},
    {"choices": [{"message": {}}]}, {"choices": [{"message": {"content": []}}]}])
def test_malformed_envelope(monkeypatch, data):
    post = Mock(return_value=httpx.Response(200, json=data,
                request=httpx.Request("POST", "https://test")))
    monkeypatch.setattr("httpx.post", post)
    assert run(agent()) is None
    assert post.call_count == 1


@pytest.mark.parametrize("content", ["", "   ", "Pas de JSON", "null", "[]", "{}",
    '"manteau rouge"', '{"sentences":[]}',
    '{"sentences":[{"fact":"invented_price","variant":0}]}',
    '{"sentences":[{"fact":"composition","variant":99}]}',
    '{"sentences":[{"fact":"composition","variant":true}]}',
    '{"sentences":[{"fact":"composition","variant":0,"text":"10 robes rouges"}]}',
    '{"sentences":[{"fact":"composition","variant":0}],"price":99}',
    selection("colors"), selection("composition", "composition"), "x" * 12001])
def test_untrusted_model_prose_never_reaches_user(monkeypatch, content):
    post = Mock(return_value=response(content))
    monkeypatch.setattr("httpx.post", post)
    assert run(agent()) is None
    assert post.call_count == 1


def test_truncated_generation_rejected(monkeypatch):
    data = {"choices": [{"message": {"content": selection("composition")}, "finish_reason": "length"}]}
    monkeypatch.setattr("httpx.post", Mock(return_value=response(data=data)))
    assert run(agent()) is None


def test_non_json_http_body_rejected(monkeypatch):
    monkeypatch.setattr("httpx.post", Mock(return_value=httpx.Response(200, text="<html>oops</html>",
        request=httpx.Request("POST", "https://test"))))
    assert run(agent()) is None


def test_cache_shared_across_instances_but_invalidated_by_facts_and_scope(monkeypatch):
    post = Mock(return_value=response(selection("composition")))
    monkeypatch.setattr("httpx.post", post)
    assert run(agent(), cache_scope="user1")
    assert run(agent(), cache_scope="user1")
    assert post.call_count == 1
    assert run(agent(), cache_scope="user2")
    changed = {**PROFILE, "wardrobe_size": 4}
    assert agent().run(context=changed, instruction="Décris le profil", cache_scope="user1")["explanation"]
    assert run(agent(llm_model="different"), cache_scope="user1")
    assert post.call_count == 4


def test_cache_expiry_negative_cache_and_bounded_size(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("app.agents.llm_agent.time.monotonic", lambda: clock[0])
    post = Mock(return_value=response("malformed"))
    monkeypatch.setattr("httpx.post", post)
    a = agent(llm_cache_max_entries=2)
    assert run(a) is None
    assert run(a) is None
    assert post.call_count == 1
    clock[0] += 16
    post.return_value = response(selection("composition"))
    assert run(a)
    clock[0] += 3601
    assert run(a)
    assert post.call_count == 3
    for i in range(5):
        run(a, cache_scope=str(i))
    assert len(LLMAgent._cache) == 2


def test_concurrent_identical_requests_are_single_flight(monkeypatch):
    post = Mock(return_value=response(selection("composition")))
    monkeypatch.setattr("httpx.post", post)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: run(agent(), cache_scope="same"), range(12)))
    assert all(results)
    assert post.call_count == 1


def test_grounded_json_prompt_and_safe_logs(monkeypatch, caplog):
    post = Mock(return_value=response(status=401))
    monkeypatch.setattr("httpx.post", post)
    with caplog.at_level(logging.INFO):
        assert run(agent()) is None
    payload = json.loads(post.call_args.kwargs["json"]["messages"][1]["content"])
    assert payload["facts"] == PROFILE
    assert "français" in post.call_args.kwargs["json"]["messages"][0]["content"]
    assert "unit-test-placeholder" not in caplog.text
    assert caplog.records[-1].llm_event == "http_failure"
    assert "unit-test-placeholder" not in repr(agent().settings)


def test_bad_facts_and_unknown_task_do_not_call_provider(monkeypatch):
    post = Mock()
    monkeypatch.setattr("httpx.post", post)
    a = agent()
    for facts, task in [({}, "style_profile"), (PROFILE, "unknown"), ({"items": []}, "outfit")]:
        assert a.run(context=facts, instruction="", task=task) == {"explanation": None}
    post.assert_not_called()


def test_environment_file_configuration(tmp_path):
    env = tmp_path / ".env"
    env.write_text("LLM_PROVIDER=ollama\nLLM_MODEL=qwen2.5:3b\nLLM_TIMEOUT_SECONDS=4\n", encoding="utf-8")
    settings = Settings(_env_file=env)
    assert settings.llm_provider == "ollama" and settings.llm_model == "qwen2.5:3b"
    assert settings.llm_timeout_seconds == 4


def test_real_http_serialization_against_loopback_server():
    """Exercises actual httpx I/O without any external account or paid request."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    captured = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            captured["path"] = self.path
            captured["authorization"] = self.headers.get("Authorization")
            captured["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            raw = json.dumps({"choices": [{"message": {"content": selection("composition", "styles")}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        a = agent(llm_provider="ollama", llm_api_key=None,
                  llm_base_url=f"http://127.0.0.1:{server.server_port}/v1")
        text = run(a)
        assert "3 pièces" in text and "Casual" in text
        assert captured["path"] == "/v1/chat/completions"
        assert captured["authorization"] is None
        assert json.loads(captured["body"]["messages"][1]["content"])["facts"] == PROFILE
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_missing_optional_proxy_dependency_is_safe_fallback(monkeypatch):
    monkeypatch.setattr("httpx.post", Mock(side_effect=ImportError("socksio is unavailable")))
    assert run(agent()) is None

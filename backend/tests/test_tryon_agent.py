import pytest

from app.agents.tryon_agent import TryOnAgent
from app.core.config import Settings


def _agent_with_settings(monkeypatch, **overrides) -> TryOnAgent:
    # Both default to unset here regardless of the real .env (which has them set for
    # local dev/testing) — tests opt in to a configured agent explicitly instead.
    overrides.setdefault("replicate_api_token", None)
    overrides.setdefault("replicate_tryon_model_version", None)
    settings = Settings(**overrides)
    monkeypatch.setattr("app.agents.tryon_agent.get_settings", lambda: settings)
    return TryOnAgent()


def test_unconfigured_raises_a_clear_error(monkeypatch):
    agent = _agent_with_settings(monkeypatch)

    assert not agent.is_configured()
    with pytest.raises(RuntimeError, match="isn't configured"):
        agent.run(person_image_url="https://x/person.jpg", garment_image_url="https://x/garment.jpg")


def test_successful_generation_polls_until_succeeded(monkeypatch):
    agent = _agent_with_settings(
        monkeypatch, replicate_api_token="r8_test", replicate_tryon_model_version="abc123"
    )

    calls = {"get_count": 0}

    class _CreateResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"urls": {"get": "https://api.replicate.com/v1/predictions/xyz"}}

    class _PollResponse:
        def __init__(self, status, output=None):
            self._status = status
            self._output = output

        def raise_for_status(self):
            pass

        def json(self):
            return {"status": self._status, "output": self._output}

    def fake_post(url, **kwargs):
        assert kwargs["json"]["version"] == "abc123"
        assert kwargs["json"]["input"] == {
            "human_img": "https://x/person.jpg",
            "garm_img": "https://x/garment.jpg",
        }
        assert kwargs["headers"]["Authorization"] == "Token r8_test"
        return _CreateResponse()

    def fake_get(url, **kwargs):
        calls["get_count"] += 1
        # First poll: still running. Second poll: done.
        if calls["get_count"] == 1:
            return _PollResponse("processing")
        return _PollResponse("succeeded", output=["https://result.img/output.png"])

    monkeypatch.setattr("httpx.post", fake_post)
    monkeypatch.setattr("httpx.get", fake_get)
    monkeypatch.setattr("time.sleep", lambda _: None)

    result = agent.run(person_image_url="https://x/person.jpg", garment_image_url="https://x/garment.jpg")

    assert result == {"result_image_url": "https://result.img/output.png"}
    assert calls["get_count"] == 2


def test_failed_generation_raises(monkeypatch):
    agent = _agent_with_settings(
        monkeypatch, replicate_api_token="r8_test", replicate_tryon_model_version="abc123"
    )

    class _Response:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self._data

    monkeypatch.setattr(
        "httpx.post", lambda *a, **k: _Response({"urls": {"get": "https://x/pred"}})
    )
    monkeypatch.setattr(
        "httpx.get", lambda *a, **k: _Response({"status": "failed", "error": "bad input"})
    )

    with pytest.raises(RuntimeError, match="bad input"):
        agent.run(person_image_url="https://x/person.jpg", garment_image_url="https://x/garment.jpg")

import pytest

from app.agents.tryon_agent import TryOnAgent
from app.core.config import Settings


def _agent_with_settings(monkeypatch, **overrides) -> TryOnAgent:
    # Both default to unset here regardless of the real .env (which has them set for
    # local dev/testing) — tests opt in to a configured agent explicitly instead.
    overrides.setdefault("tryon_provider", "replicate")
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


def test_auto_provider_prefers_replicate_only_when_its_credentials_exist(monkeypatch):
    free = _agent_with_settings(monkeypatch, tryon_provider="auto")
    paid = _agent_with_settings(
        monkeypatch, tryon_provider="auto", replicate_api_token="r8_x", replicate_tryon_model_version="v1"
    )

    assert free.provider == "huggingface"
    assert paid.provider == "replicate"


def test_huggingface_chain_dresses_garments_in_order_and_stores_the_result(monkeypatch, tmp_path):
    agent = _agent_with_settings(monkeypatch, tryon_provider="huggingface", local_storage_dir=str(tmp_path))
    calls = []

    class _Job:
        def __init__(self, out):
            self.out = out

        def result(self, timeout=None):
            return [{"image": self.out, "caption": None}]

    class _Client:
        def __init__(self, space, hf_token=None, verbose=False):
            assert space == "levihsu/OOTDiffusion"

        def submit(self, person, garment, category, *rest, api_name):
            calls.append((person, garment, category, api_name))
            out = tmp_path / f"step{len(calls)}.png"
            out.write_bytes(b"png-bytes")
            return _Job(str(out))

    import gradio_client

    monkeypatch.setattr(gradio_client, "Client", _Client)
    monkeypatch.setattr(gradio_client, "handle_file", lambda path: f"file:{path}")

    result = agent.run_outfit(
        person_image_url="https://x/avatar.jpg",
        garments=[("https://x/pants.jpg", "lower_body"), ("https://x/top.jpg", "upper_body")],
    )

    assert [c[2] for c in calls] == ["Lower-body", "Upper-body"]
    assert calls[0][0] == "file:https://x/avatar.jpg"
    assert calls[1][0].startswith("file:") and calls[1][0].endswith("step1.png")  # chained on the previous result
    assert all(c[3] == "/process_dc" for c in calls)
    assert result["persisted"] is True and "/media/" in result["result_image_url"]


def test_huggingface_failure_becomes_a_runtime_error_with_quota_advice(monkeypatch, tmp_path):
    agent = _agent_with_settings(monkeypatch, tryon_provider="huggingface", local_storage_dir=str(tmp_path))

    class _Client:
        def __init__(self, *a, **k):
            raise ValueError("You have exceeded your GPU quota")

    import gradio_client

    monkeypatch.setattr(gradio_client, "Client", _Client)

    with pytest.raises(RuntimeError, match="HF_TOKEN"):
        agent.run_outfit(person_image_url="https://x/a.jpg", garments=[("https://x/g.jpg", "upper_body")])

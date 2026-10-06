"""Exercises the real FashionCLIP pipeline end-to-end (model download + inference,
no mocking of app.ml.vision_model) — slow and network-dependent on first run (downloads
patrickjohncyh/fashion-clip from Hugging Face), unlike the rest of the suite. Only
app.agents.vision_agent's own HTTP image fetch is mocked, so the test doesn't depend on
a live external image URL.
"""

from pathlib import Path

import pytest

from app.agents import vision_agent as vision_agent_module
from app.agents.vision_agent import VisionAgent
from app.ml.vision_model import CATEGORY_CLASSIFIER_PATH

TEST_IMAGES_DIR = Path(__file__).resolve().parents[2] / "ml" / "data" / "raw" / "tunisian_images"

pytestmark = pytest.mark.skipif(
    not CATEGORY_CLASSIFIER_PATH.exists() or not TEST_IMAGES_DIR.exists(),
    reason="category_classifier.joblib or ml/data/raw/tunisian_images not available locally",
)


class _FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self) -> None:
        pass


def test_run_returns_structured_attributes(monkeypatch):
    image_path = next(TEST_IMAGES_DIR.glob("*.jpg"))
    monkeypatch.setattr(
        vision_agent_module.httpx, "get", lambda *a, **k: _FakeResponse(image_path.read_bytes())
    )

    result = VisionAgent().run(image_url="https://example.invalid/test.jpg")

    assert result["category"] in {
        "haut", "bas", "robe", "veste", "chaussures", "sac", "accessoire", "hors_perimetre",
    }
    assert isinstance(result["colors"], list) and len(result["colors"]) == 1
    assert isinstance(result["pattern"], str)
    assert isinstance(result["style"], str)
    # VisionAgent only analyzes — persistence (Pinecone upsert) is the caller's job
    # (see app/api/routes/wardrobe.py), so the raw embedding is returned, not an id.
    assert result["embedding"].shape == (512,)

import io
import uuid
import numpy as np
import pytest
from PIL import Image

from app.agents.metadata_agent import MetadataAgent
from app.ml import background_removal, garment_segmentation
from app.models.user import User


class _FakeStorage:
    def __init__(self):
        self.uploads = []

    def is_configured(self):
        return True

    def upload_image(self, content, content_type):
        self.uploads.append((content, content_type))
        return f"http://storage/cleaned-{len(self.uploads)}.jpg"


class _FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass


@pytest.fixture
def test_image_bytes():
    img = Image.new("RGB", (100, 100), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_process_and_upload_non_http_returns_original():
    assert background_removal.process_and_upload_clean_image("u") == "u"
    assert background_removal.process_and_upload_clean_image("") == ""


def test_process_and_upload_clean_image_with_rembg(monkeypatch, test_image_bytes):
    # Mock rembg
    class _MockRembg:
        @staticmethod
        def remove(b):
            rgba = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
            buf = io.BytesIO()
            rgba.save(buf, format="PNG")
            return buf.getvalue()

    monkeypatch.setattr(background_removal, "_remove_bg_with_rembg", lambda b: _MockRembg.remove(b))
    monkeypatch.setattr("httpx.get", lambda *a, **k: _FakeResponse(test_image_bytes))

    storage = _FakeStorage()
    result = background_removal.process_and_upload_clean_image("http://test/input.jpg", storage)

    assert result == "http://storage/cleaned-1.jpg"
    assert len(storage.uploads) == 1


def test_process_and_upload_clean_image_with_segformer_fallback(monkeypatch, test_image_bytes):
    # Simulate rembg not installed
    monkeypatch.setattr(background_removal, "_remove_bg_with_rembg", lambda b: None)
    monkeypatch.setattr("httpx.get", lambda *a, **k: _FakeResponse(test_image_bytes))

    # Segformer produces garment mask
    labels = np.zeros((100, 100), dtype=np.int64)
    labels[20:80, 20:80] = 4  # Top (Upper-clothes)
    monkeypatch.setattr(garment_segmentation, "_label_map", lambda img: labels)

    storage = _FakeStorage()
    result = background_removal.process_and_upload_clean_image("http://test/input.jpg", storage)

    assert result == "http://storage/cleaned-1.jpg"
    assert len(storage.uploads) == 1


def test_fallback_when_no_garment_detected(monkeypatch, test_image_bytes):
    monkeypatch.setattr(background_removal, "_remove_bg_with_rembg", lambda b: None)
    monkeypatch.setattr("httpx.get", lambda *a, **k: _FakeResponse(test_image_bytes))

    # All background (0)
    labels = np.zeros((100, 100), dtype=np.int64)
    monkeypatch.setattr(garment_segmentation, "_label_map", lambda img: labels)

    storage = _FakeStorage()
    result = background_removal.process_and_upload_clean_image("http://test/input.jpg", storage)

    # Returns original url unchanged
    assert result == "http://test/input.jpg"
    assert len(storage.uploads) == 0


def test_metadata_agent_uses_cleaned_image(monkeypatch, test_image_bytes):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.db.base import Base
    import app.models  # noqa: F401

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    user = User(email="test@dressme.ai", hashed_password="pw")
    db.add(user)
    db.commit()

    storage = _FakeStorage()
    agent = MetadataAgent(db, storage=storage)

    # Mock background removal to return a new clean url
    monkeypatch.setattr(
        background_removal,
        "process_and_upload_clean_image",
        lambda url, s: "http://storage/clean.jpg" if url == "http://storage/raw.jpg" else url,
    )

    attrs = {
        "category": "haut",
        "colors": ["noir"],
        "style": "Casual",
        "pattern": "uni",
        "season": "ete",
        "confidence": {"category": 0.95},
        "embedding": np.zeros(512),
    }

    item = agent.add_item(
        user_id=user.id,
        image_url="http://storage/raw.jpg",
        attributes=attrs,
        remove_bg=True,
    )

    assert item.image_url == "http://storage/clean.jpg"

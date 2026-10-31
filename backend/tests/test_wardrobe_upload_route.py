import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.main import app

client = TestClient(app)


class _FakeUser:
    id = uuid.uuid4()


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    yield
    app.dependency_overrides.pop(get_current_user, None)


def test_upload_returns_503_when_storage_unconfigured(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.wardrobe.storage_service.is_configured", lambda: False
    )

    response = client.post(
        "/api/v1/wardrobe/upload", files={"file": ("photo.jpg", b"fake-bytes", "image/jpeg")}
    )

    assert response.status_code == 503


def test_upload_returns_the_image_url_when_configured(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.wardrobe.storage_service.is_configured", lambda: True
    )
    monkeypatch.setattr(
        "app.api.routes.wardrobe.storage_service.upload_image",
        lambda content, content_type: "https://example.com/fake-key",
    )

    response = client.post(
        "/api/v1/wardrobe/upload", files={"file": ("photo.jpg", b"fake-bytes", "image/jpeg")}
    )

    assert response.status_code == 200
    assert response.json() == {"image_url": "https://example.com/fake-key"}

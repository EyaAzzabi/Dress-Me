import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.api.deps import get_current_user
from app.api.routes import tryon as tryon_route
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.clothing_item import ClothingItem
from app.models.user import User


@pytest.fixture
def setup(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    user = User(email="tryon@example.com", hashed_password="pw", avatar_photo_url="https://media/avatar.jpg")
    db.add(user)
    db.commit()
    top = ClothingItem(owner_id=user.id, image_url="https://media/top.jpg", category="haut")
    bottom = ClothingItem(owner_id=user.id, image_url="https://media/bottom.jpg", category="bas")
    dress = ClothingItem(owner_id=user.id, image_url="https://media/dress.jpg", category="robe")
    shoes = ClothingItem(owner_id=user.id, image_url="https://media/shoes.jpg", category="chaussures")
    db.add_all([top, bottom, dress, shoes])
    db.commit()

    calls = []
    monkeypatch.setattr(tryon_route.tryon_agent, "is_configured", lambda: True)
    monkeypatch.setattr(
        tryon_route.tryon_agent,
        "run_outfit",
        lambda **kwargs: calls.append(kwargs) or {"result_image_url": "https://media/result.jpg"},
    )
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app), top, bottom, dress, shoes, calls
    app.dependency_overrides.clear()
    db.close()
    engine.dispose()


def test_single_bottom_is_sent_as_lower_body(setup):
    client, _, bottom, _, _, calls = setup

    response = client.post("/api/v1/tryon/", json={"garment_item_id": str(bottom.id)})

    assert response.status_code == 200, response.text
    assert calls[0]["garments"] == [("https://media/bottom.jpg", "lower_body")]


def test_multiple_garments_use_stable_layer_order(setup):
    client, top, bottom, _, _, calls = setup

    response = client.post(
        "/api/v1/tryon/",
        json={"garment_item_ids": [str(top.id), str(bottom.id)]},
    )

    assert response.status_code == 200, response.text
    assert calls[0]["garments"] == [
        ("https://media/bottom.jpg", "lower_body"),
        ("https://media/top.jpg", "upper_body"),
    ]


def test_unsupported_category_is_rejected_instead_of_misfitted(setup):
    client, _, _, _, shoes, calls = setup

    response = client.post("/api/v1/tryon/", json={"garment_item_id": str(shoes.id)})

    assert response.status_code == 422
    assert calls == []


def test_unconfigured_tryon_returns_clear_service_error(setup, monkeypatch):
    client, _, bottom, _, _, calls = setup
    monkeypatch.setattr(tryon_route.tryon_agent, "is_configured", lambda: False)

    response = client.post("/api/v1/tryon/", json={"garment_item_id": str(bottom.id)})

    assert response.status_code == 503
    assert "pas configuré" in response.json()["detail"]
    assert calls == []


def test_generation_failure_is_returned_as_bad_gateway(setup, monkeypatch):
    client, _, bottom, _, _, _ = setup

    def fail(**kwargs):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(tryon_route.tryon_agent, "run_outfit", fail)
    response = client.post("/api/v1/tryon/", json={"garment_item_id": str(bottom.id)})

    assert response.status_code == 502
    assert "model unavailable" in response.json()["detail"]


def test_dress_cannot_be_combined_with_top_or_bottom(setup):
    client, top, bottom, dress, _, calls = setup

    response = client.post(
        "/api/v1/tryon/",
        json={"garment_item_ids": [str(dress.id), str(bottom.id), str(top.id)]},
    )

    assert response.status_code == 422
    assert calls == []

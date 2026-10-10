import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — registers all models on Base.metadata
from app.agents import metadata_agent as metadata_module
from app.api.deps import get_current_user
from app.api.routes import wardrobe as wardrobe_route
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.user import User


def _attributes(category="robe", confidence=0.42):
    return {
        "category": category, "colors": ["beige"], "pattern": "uni", "style": "Casual",
        "season": "ete", "category_uncertain": confidence < 0.5,
        "confidence": {"category": confidence, "colors": 0.9, "pattern": 0.7, "style": 0.4, "season": 0.9},
        "embedding": np.zeros(512),
    }


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    user = User(email="a@b.c", hashed_password="x")
    db.add(user)
    db.commit()
    upserts = []
    monkeypatch.setattr(
        metadata_module.vector_store, "upsert_item_embedding", lambda *a, **k: upserts.append(k)
    )
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    test_client = TestClient(app)
    test_client.upserts = upserts
    yield test_client
    app.dependency_overrides.clear()


def _vision_returns(monkeypatch, attributes):
    monkeypatch.setattr(wardrobe_route.vision_agent, "run", lambda image_url: attributes)


def test_uncertain_category_is_refused_with_a_machine_readable_reason(client, monkeypatch):
    _vision_returns(monkeypatch, _attributes("robe", 0.42))

    response = client.post("/api/v1/wardrobe/", json={"image_url": "https://x/outfit.jpg"})

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "low_category_confidence"
    assert detail["suggested_category"] == "robe" and detail["confidence"] == 0.42
    assert client.get("/api/v1/wardrobe/").json() == []  # nothing was saved


def test_owner_confirmed_category_is_saved_as_certain(client, monkeypatch):
    _vision_returns(monkeypatch, _attributes("robe", 0.42))

    response = client.post("/api/v1/wardrobe/", json={"image_url": "https://x/outfit.jpg", "category": "bas"})

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["category"] == "bas"
    assert body["attribute_confidence"]["category"] == 1.0
    assert client.upserts[0]["category"] == "bas"  # the vector store gets the confirmed one too


def test_confident_category_is_accepted_without_asking(client, monkeypatch):
    _vision_returns(monkeypatch, _attributes("haut", 0.91))

    response = client.post("/api/v1/wardrobe/", json={"image_url": "https://x/tee.jpg"})

    assert response.status_code == 201 and response.json()["category"] == "haut"


def test_unknown_category_value_is_rejected_by_validation(client, monkeypatch):
    _vision_returns(monkeypatch, _attributes("haut", 0.91))

    response = client.post("/api/v1/wardrobe/", json={"image_url": "https://x/a.jpg", "category": "chapeau"})

    assert response.status_code == 422

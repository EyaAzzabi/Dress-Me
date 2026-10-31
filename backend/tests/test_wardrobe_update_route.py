import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — registers all models on Base.metadata
from app.api.deps import get_current_user
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.clothing_item import ClothingItem
from app.models.user import User


@pytest.fixture
def setup():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    user = User(email="a@b.c", hashed_password="x")
    other = User(email="d@e.f", hashed_password="x")
    db.add_all([user, other])
    db.commit()
    item = ClothingItem(
        owner_id=user.id, image_url="u", category="haut", colors=["noir"], season="ete",
        season_source="vision", attribute_confidence={"category": 0.9},
    )
    db.add(item)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app), item, other, db
    app.dependency_overrides.clear()


def test_patch_updates_fields_and_marks_season_as_user(setup):
    client, item, _, _ = setup

    response = client.patch(
        f"/api/v1/wardrobe/{item.id}", json={"season": "hiver", "colors": ["bleu", "blanc"]}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["season"] == "hiver" and body["season_source"] == "user"
    assert body["colors"] == ["bleu", "blanc"]
    assert body["category"] == "haut"  # untouched
    assert body["attribute_confidence"] == {"category": 0.9}


def test_patch_rejects_unknown_season(setup):
    client, item, _, _ = setup

    assert client.patch(f"/api/v1/wardrobe/{item.id}", json={"season": "printemps"}).status_code == 422


def test_patch_other_users_item_is_404(setup):
    client, _, other, db = setup
    foreign = ClothingItem(owner_id=other.id, image_url="u")
    db.add(foreign)
    db.commit()

    assert client.patch(f"/api/v1/wardrobe/{foreign.id}", json={"style": "Formal"}).status_code == 404

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.agents.metadata_agent import MetadataAgent
from app.api.deps import get_current_user
from app.api.routes import wardrobe as wardrobe_route
from app.db import vector_store
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.user import User


@pytest.fixture
def setup(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    user = User(email="wardrobe@example.com", hashed_password="pw")
    db.add(user)
    db.commit()

    analyzed_urls = []
    monkeypatch.setattr(wardrobe_route.vision_agent, "run", lambda **kw: analyzed_urls.append(kw["image_url"]) or {
        "category": "chaussures",
        "colors": ["blanc"],
        "style": "Casual",
        "pattern": "uni",
        "season": "ete",
        "confidence": {"category": 0.95},
        "embedding": np.zeros(512),
    })
    monkeypatch.setattr(vector_store, "upsert_item_embedding", lambda *args, **kwargs: None)
    # raising=False: MetadataAgent has no remove_background today (background removal is the opt-in
    # add_item(remove_bg=True) path); this guard fails the test if one is ever wired into the add route.
    monkeypatch.setattr(
        MetadataAgent, "remove_background", lambda *args: pytest.fail("original photo was altered"), raising=False
    )
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app), analyzed_urls
    app.dependency_overrides.clear()
    db.close()
    engine.dispose()


def test_added_item_keeps_original_photo_for_display_and_tryon(setup):
    client, analyzed_urls = setup
    original_url = "https://media/light-shoes.jpg"

    response = client.post("/api/v1/wardrobe/", json={"image_url": original_url})

    assert response.status_code == 201, response.text
    assert analyzed_urls == [original_url]
    assert response.json()["image_url"] == original_url

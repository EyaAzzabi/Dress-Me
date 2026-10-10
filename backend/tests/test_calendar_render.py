from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — registers all models on Base.metadata
from app.agents.tryon_agent import garments_for_outfit
from app.api.deps import get_current_user
from app.api.routes import calendar as calendar_route
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.clothing_item import ClothingItem
from app.models.user import User

DAY = date(2026, 10, 12)


class _Item:
    def __init__(self, category, url):
        self.category, self.image_url = category, url


def test_garments_follow_layer_order_and_skip_unwearable_pieces():
    items = [_Item("veste", "j"), _Item("sac", "bag"), _Item("haut", "t"), _Item("bas", "b"), _Item("haut", "t2")]

    assert garments_for_outfit(items) == [("b", "lower_body"), ("t", "upper_body"), ("j", "upper_body")]
    assert garments_for_outfit([_Item("robe", "d")]) == [("d", "dresses")]
    assert garments_for_outfit([_Item("sac", "bag")]) == []


@pytest.fixture
def setup(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    user = User(email="a@b.c", hashed_password="x", avatar_photo_url="https://media/avatar.jpg")
    db.add(user)
    db.commit()
    top = ClothingItem(owner_id=user.id, image_url="https://media/top.jpg", category="haut")
    bottom = ClothingItem(owner_id=user.id, image_url="https://media/bottom.jpg", category="bas")
    db.add_all([top, bottom])
    db.commit()

    calls = []
    monkeypatch.setattr(calendar_route.tryon_agent, "is_configured", lambda: True)
    monkeypatch.setattr(
        calendar_route.tryon_agent,
        "run_outfit",
        lambda **kw: calls.append(kw) or {"result_image_url": "https://replicate/out.jpg"},
    )
    monkeypatch.setattr(calendar_route.storage_service, "is_configured", lambda: True)
    monkeypatch.setattr(calendar_route.storage_service, "upload_image", lambda b, t: "https://media/render.jpg")

    class _Resp:
        content = b"img"
        headers = {"content-type": "image/jpeg"}

        def raise_for_status(self):
            pass

    monkeypatch.setattr(calendar_route.httpx, "get", lambda *a, **k: _Resp())
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    client = TestClient(app)
    client.put(f"/api/v1/calendar/{DAY}", json={"item_ids": [str(top.id), str(bottom.id)]})
    yield client, user, top, bottom, db, calls
    app.dependency_overrides.clear()


def test_render_stores_picture_and_reuses_it_until_the_outfit_changes(setup):
    client, user, top, bottom, db, calls = setup

    first = client.post(f"/api/v1/calendar/{DAY}/render")
    again = client.post(f"/api/v1/calendar/{DAY}/render")
    listed = client.get("/api/v1/calendar/", params={"start": DAY, "end": DAY}).json()

    assert first.status_code == 200, first.text
    assert first.json()["render_image_url"] == "https://media/render.jpg"
    assert again.json()["render_image_url"] == "https://media/render.jpg"
    assert len(calls) == 1  # the second request cost nothing
    assert calls[0]["garments"] == [("https://media/bottom.jpg", "lower_body"), ("https://media/top.jpg", "upper_body")]
    assert listed[0]["render_image_url"] == "https://media/render.jpg"

    client.put(f"/api/v1/calendar/{DAY}", json={"item_ids": [str(top.id)]})  # change the outfit
    assert client.get(f"/api/v1/calendar/{DAY}").json()["render_image_url"] is None


def test_render_hidden_when_avatar_photo_changes(setup):
    client, user, *_ = setup
    client.post(f"/api/v1/calendar/{DAY}/render")

    user.avatar_photo_url = "https://media/new-avatar.jpg"

    assert client.get(f"/api/v1/calendar/{DAY}").json()["render_image_url"] is None


def test_render_requires_avatar_and_a_plan(setup):
    client, user, *_ = setup

    assert client.post("/api/v1/calendar/2026-11-01/render").status_code == 404
    user.avatar_photo_url = None
    assert client.post(f"/api/v1/calendar/{DAY}/render").status_code == 422


def test_render_failure_is_a_502_not_a_500(setup, monkeypatch):
    client, *_ = setup

    def boom(**kw):
        raise RuntimeError("Replicate request failed (402)")

    monkeypatch.setattr(calendar_route.tryon_agent, "run_outfit", boom)

    response = client.post(f"/api/v1/calendar/{DAY}/render")

    assert response.status_code == 502 and "402" in response.json()["detail"]

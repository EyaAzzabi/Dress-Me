"""Tests for RLHF API endpoints — POST /rlhf/feedback and GET /rlhf/stats."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.api.deps import get_current_user
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.outfit import Outfit
from app.models.user import User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def setup(monkeypatch):
    """Create in-memory SQLite DB, two users, and two outfits; override deps."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    item1 = uuid.uuid4()
    item2 = uuid.uuid4()

    user_a = User(email="rlhf_a@example.com", hashed_password="pw")
    user_b = User(email="rlhf_b@example.com", hashed_password="pw")
    db.add_all([user_a, user_b])
    db.flush()

    outfit_a = Outfit(
        owner_id=user_a.id,
        item_ids=[item1, item2],
        occasion="casual",
    )
    outfit_b = Outfit(
        owner_id=user_b.id,
        item_ids=[item1],
        occasion="sport",
    )
    db.add_all([outfit_a, outfit_b])
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user_a

    yield TestClient(app), db, user_a, user_b, outfit_a, outfit_b, item1, item2

    app.dependency_overrides.clear()
    db.close()
    engine.dispose()


# ---------------------------------------------------------------------------
# POST /rlhf/feedback — success
# ---------------------------------------------------------------------------


def test_feedback_returns_201(setup):
    client, db, user_a, user_b, outfit_a, outfit_b, item1, item2 = setup
    response = client.post(
        "/api/v1/rlhf/feedback",
        json={"outfit_id": str(outfit_a.id), "rating": 4},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["rating"] == 4
    assert body["is_new"] is True
    assert body["total_feedbacks_by_user"] == 1


def test_feedback_is_always_new_row(setup):
    """Submitting feedback twice for the same outfit creates two rows (FIX-5)."""
    client, db, user_a, user_b, outfit_a, outfit_b, item1, item2 = setup
    payload = {"outfit_id": str(outfit_a.id), "rating": 3}
    r1 = client.post("/api/v1/rlhf/feedback", json=payload)
    r2 = client.post("/api/v1/rlhf/feedback", json=payload)
    assert r1.status_code == 201
    assert r2.status_code == 201
    # Two distinct IDs
    assert r1.json()["id"] != r2.json()["id"]
    # total_feedbacks_by_user increases
    assert r2.json()["total_feedbacks_by_user"] == 2


# ---------------------------------------------------------------------------
# POST /rlhf/feedback — error cases
# ---------------------------------------------------------------------------


def test_feedback_404_unknown_outfit(setup):
    client, *_ = setup
    response = client.post(
        "/api/v1/rlhf/feedback",
        json={"outfit_id": str(uuid.uuid4()), "rating": 3},
    )
    assert response.status_code == 404


def test_feedback_403_not_owner(setup):
    """user_a tries to rate outfit_b which belongs to user_b."""
    client, db, user_a, user_b, outfit_a, outfit_b, item1, item2 = setup
    response = client.post(
        "/api/v1/rlhf/feedback",
        json={"outfit_id": str(outfit_b.id), "rating": 3},
    )
    assert response.status_code == 403


def test_feedback_422_invalid_rating_too_low(setup):
    client, db, user_a, user_b, outfit_a, outfit_b, item1, item2 = setup
    response = client.post(
        "/api/v1/rlhf/feedback",
        json={"outfit_id": str(outfit_a.id), "rating": 0},
    )
    assert response.status_code == 422


def test_feedback_422_invalid_rating_too_high(setup):
    client, db, user_a, user_b, outfit_a, outfit_b, item1, item2 = setup
    response = client.post(
        "/api/v1/rlhf/feedback",
        json={"outfit_id": str(outfit_a.id), "rating": 6},
    )
    assert response.status_code == 422


def test_feedback_422_unknown_item_liked(setup):
    """items_liked references an item not in the outfit."""
    client, db, user_a, user_b, outfit_a, outfit_b, item1, item2 = setup
    response = client.post(
        "/api/v1/rlhf/feedback",
        json={
            "outfit_id": str(outfit_a.id),
            "rating": 4,
            "items_liked": [{"id": str(uuid.uuid4())}],
        },
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /rlhf/stats — no data
# ---------------------------------------------------------------------------


def test_stats_empty_returns_zeros(setup):
    """Stats endpoint must not crash when rlhf_feedback table is empty."""
    client, *_ = setup
    response = client.get("/api/v1/rlhf/stats")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_feedbacks"] == 0
    assert body["average_rating"] == 0.0
    # rating_distribution always has all 5 keys
    rd = body["rating_distribution"]
    for key in ["1", "2", "3", "4", "5"]:
        assert key in rd, f"Missing key {key} in rating_distribution"
        assert rd[key] == 0
    assert body["recent_feedbacks"] == []
    assert body["most_liked_items"] == []
    assert body["most_disliked_items"] == []
    assert body["avg_rating_trend"] == []


def test_stats_readiness_keys_present(setup):
    client, *_ = setup
    body = client.get("/api/v1/rlhf/stats").json()
    r = body["readiness_for_training"]
    assert "has_sufficient_data" in r
    assert "pair_count" in r
    assert "next_threshold" in r
    assert "last_trained_at" in r


# ---------------------------------------------------------------------------
# GET /rlhf/stats — with data
# ---------------------------------------------------------------------------


def test_stats_with_data(setup):
    client, db, user_a, user_b, outfit_a, outfit_b, item1, item2 = setup
    # Submit some feedback
    client.post("/api/v1/rlhf/feedback", json={"outfit_id": str(outfit_a.id), "rating": 5})
    client.post("/api/v1/rlhf/feedback", json={"outfit_id": str(outfit_a.id), "rating": 3})

    body = client.get("/api/v1/rlhf/stats").json()
    assert body["total_feedbacks"] == 2
    assert body["average_rating"] == 4.0
    assert body["rating_distribution"]["5"] == 1
    assert body["rating_distribution"]["3"] == 1
    assert len(body["recent_feedbacks"]) == 2


# ---------------------------------------------------------------------------
# GET /rlhf/stats?format=csv
# ---------------------------------------------------------------------------


def test_stats_csv_content_type(setup):
    client, *_ = setup
    response = client.get("/api/v1/rlhf/stats?format=csv")
    assert response.status_code == 200, response.text
    assert "text/csv" in response.headers.get("content-type", "")


def test_stats_csv_has_content_disposition(setup):
    client, *_ = setup
    response = client.get("/api/v1/rlhf/stats?format=csv")
    assert "attachment" in response.headers.get("content-disposition", "")
    assert "retours_rlhf.csv" in response.headers.get("content-disposition", "")


# ---------------------------------------------------------------------------
# Acceptance-criteria checks (import-level)
# ---------------------------------------------------------------------------


def test_router_prefix():
    from app.api.routes.rlhf import router

    assert router.prefix == "/rlhf"


def test_rlhf_routes_registered_in_app():
    from app.main import app as fastapi_app

    paths = [r.path for r in fastapi_app.routes]
    assert any("rlhf" in p and "feedback" in p for p in paths)
    assert any("rlhf" in p and "stats" in p for p in paths)

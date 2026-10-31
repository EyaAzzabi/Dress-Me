import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.purchase_history import PurchaseHistoryEntry
from app.models.user import User

client = TestClient(app)


def _result(category="haut", verdict="recommended", score=72):
    return {
        "verdict": verdict, "score": score, "compatibility_score": score / 100,
        "explanation": "Bon achat !",
        "item": {"category": category, "color": "noir", "pattern": None, "style": None},
    }


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    users = [User(id=uuid.uuid4(), email=f"u{i}@x.tn", hashed_password="x") for i in range(2)]
    session.add_all(users)
    session.commit()
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: users[0]
    session.users = users
    yield session
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)
    session.close()


@pytest.fixture
def evaluate(monkeypatch):
    def set_result(result):
        monkeypatch.setattr("app.api.routes.purchase.AgentOrchestrator.evaluate_purchase",
                            lambda self, **kwargs: result)
    return set_result


def test_each_check_is_saved_to_the_history(db, evaluate):
    evaluate(_result())

    client.post("/api/v1/purchase/check", json={"image_url": "http://x/crop.jpg", "price": 59.0})
    history = client.get("/api/v1/purchase/history").json()

    assert len(history) == 1
    assert history[0]["image_url"] == "http://x/crop.jpg"
    assert history[0]["price"] == 59.0
    assert (history[0]["verdict"], history[0]["score"]) == ("recommended", 72)
    assert history[0]["result"]["explanation"] == "Bon achat !"


def test_non_clothing_photos_are_not_saved(db, evaluate):
    evaluate(_result(category="hors_perimetre", verdict="not_recommended", score=0))

    client.post("/api/v1/purchase/check", json={"image_url": "http://x/cat.jpg"})

    assert client.get("/api/v1/purchase/history").json() == []


def test_history_is_private_and_newest_first(db):
    other = db.users[1]
    db.add(PurchaseHistoryEntry(owner_id=other.id, image_url="http://x/theirs.jpg", category="bas",
                                verdict="recommended", score=80, result=_result("bas")))
    for minute, name in [(0, "first"), (1, "second")]:
        db.add(PurchaseHistoryEntry(owner_id=db.users[0].id, image_url=f"http://x/{name}.jpg", category="haut",
                                    verdict="recommended", score=72, result=_result(),
                                    created_at=datetime(2026, 10, 10, 12, minute, tzinfo=timezone.utc)))
    db.commit()

    urls = [h["image_url"] for h in client.get("/api/v1/purchase/history").json()]

    assert urls == ["http://x/second.jpg", "http://x/first.jpg"]


def test_saved_analyses_get_the_current_product_links(db, monkeypatch):
    monkeypatch.setattr("app.services.tunisian_brands._resolved_product_urls",
                        lambda: {"barsha_2017": "https://www.barsha.com.tn/fr/produit/2017-ballerine"})
    result = _result()
    result["catalog_alternatives"] = [{"item_key": "barsha_2017", "name": "BALLERINE", "brand": "Barsha",
                                       "product_url": None, "store_url": "https://www.barsha.com.tn"}]
    db.add(PurchaseHistoryEntry(owner_id=db.users[0].id, image_url="http://x/old.jpg", category="haut",
                                verdict="recommended", score=72, result=result))
    db.commit()

    alternative = client.get("/api/v1/purchase/history").json()[0]["result"]["catalog_alternatives"][0]

    assert alternative["product_url"] == "https://www.barsha.com.tn/fr/produit/2017-ballerine"


def test_entries_can_be_deleted_one_by_one_or_all_at_once(db, evaluate):
    evaluate(_result())
    for _ in range(3):
        client.post("/api/v1/purchase/check", json={"image_url": "http://x/a.jpg"})
    first = client.get("/api/v1/purchase/history").json()[0]["id"]

    assert client.delete(f"/api/v1/purchase/history/{first}").status_code == 204
    assert len(client.get("/api/v1/purchase/history").json()) == 2

    assert client.delete("/api/v1/purchase/history").status_code == 204
    assert client.get("/api/v1/purchase/history").json() == []


def test_clearing_my_history_keeps_other_users_entries(db, evaluate):
    other = db.users[1]
    db.add(PurchaseHistoryEntry(owner_id=other.id, image_url="http://x/theirs.jpg", category="bas",
                                verdict="recommended", score=80, result=_result("bas")))
    db.commit()

    client.delete("/api/v1/purchase/history")

    assert db.scalars(select(PurchaseHistoryEntry)).all()[0].owner_id == other.id

import uuid
from datetime import date

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.clothing_item import ClothingItem
from app.models.scheduled_outfit import ScheduledOutfit
from app.models.user import User
from app.models.wear_log import WearLog
from app.rag import context_retrieval
from app.rag.context_retrieval import retrieve_references
from app.services import catalog_index


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    user = User(id=uuid.uuid4(), email="u@x.tn", hashed_password="x")
    session.add(user)
    session.commit()
    session.user = user
    yield session
    session.close()


@pytest.fixture
def no_catalog(monkeypatch):
    """Keep the catalog out of every test unless a test opts into a fake one — the real
    catalog_embeddings.npz may or may not be committed, and the suite must be hermetic
    either way."""
    monkeypatch.setattr(catalog_index, "_load_index",
                        lambda: (pd.DataFrame(), np.empty((0, 512), dtype=np.float32)))


def _unit(idx):
    """A unit vector along one axis — gives deterministic, inspectable dot products."""
    v = np.zeros(512, dtype=np.float32)
    v[idx] = 1.0
    return v


def _seed_items(session, *ids):
    for item_id in ids:
        session.add(ClothingItem(id=item_id, owner_id=session.user.id, image_url=f"http://x/{item_id}"))
    session.commit()


def _mock_fetch(monkeypatch, vectors):
    """vectors: {item_id (uuid): np.ndarray(512)} — returns list[float] per id, like
    vector_store.fetch_embeddings."""
    by_id = {str(item_id): vec.tolist() for item_id, vec in vectors.items()}

    def fetch(item_ids):
        return {str(i): by_id[str(i)] for i in item_ids if str(i) in by_id}

    monkeypatch.setattr(context_retrieval.vector_store, "fetch_embeddings", fetch)


def test_historical_is_ordered_by_context_vector_and_carries_vec(db, no_catalog, monkeypatch):
    summer_a, summer_b = uuid.uuid4(), uuid.uuid4()
    winter_a, winter_b = uuid.uuid4(), uuid.uuid4()
    _seed_items(db, summer_a, summer_b, winter_a, winter_b)
    _mock_fetch(monkeypatch, {
        summer_a: _unit(10), summer_b: _unit(11),
        winter_a: _unit(20), winter_b: _unit(21),
    })
    db.add(ScheduledOutfit(owner_id=db.user.id, date=date(2026, 7, 15), item_ids=[summer_a, summer_b]))
    db.add(ScheduledOutfit(owner_id=db.user.id, date=date(2026, 1, 15), item_ids=[winter_a, winter_b]))
    db.commit()

    # ctx_vec points at the summer outfit's items; requested season is summer → the
    # summer outfit wins on both the dot product and the season bonus.
    result = retrieve_references(db, db.user.id, {"season": "ete"}, _unit(10), top_n_history=5)

    historical = result["historical"]
    assert len(historical) == 2
    assert historical[0]["date"] == date(2026, 7, 15)
    assert historical[0]["season"] == "ete"
    assert historical[1]["date"] == date(2026, 1, 15)
    assert historical[1]["season"] == "hiver"
    assert historical[0]["score"] > historical[1]["score"]
    # every entry carries the mean outfit vector (review-F4 — no re-fetch needed)
    assert isinstance(historical[0]["vec"], np.ndarray)
    assert historical[0]["vec"].shape == (512,)
    assert set(historical[0]["item_ids"]) == {summer_a, summer_b}


def test_wear_log_is_grouped_by_date_into_one_outfit(db, no_catalog, monkeypatch):
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    _seed_items(db, a, b, c)
    _mock_fetch(monkeypatch, {a: _unit(10), b: _unit(11), c: _unit(12)})
    # two items worn on the same day → one group; one item on another day → skipped (<2)
    db.add(WearLog(owner_id=db.user.id, item_id=a, date=date(2026, 8, 1)))
    db.add(WearLog(owner_id=db.user.id, item_id=b, date=date(2026, 8, 1)))
    db.add(WearLog(owner_id=db.user.id, item_id=c, date=date(2026, 8, 5)))
    db.commit()

    result = retrieve_references(db, db.user.id, {"season": "ete"}, _unit(10), top_n_history=5)

    historical = result["historical"]
    assert len(historical) == 1  # the 1-item day is dropped (MIN_EMBEDDINGS=2)
    assert historical[0]["date"] == date(2026, 8, 1)
    assert set(historical[0]["item_ids"]) == {a, b}


def test_pinecone_off_returns_empty_history_without_crashing(db, no_catalog, monkeypatch):
    a, b = uuid.uuid4(), uuid.uuid4()
    _seed_items(db, a, b)
    monkeypatch.setattr(context_retrieval.vector_store, "fetch_embeddings", lambda item_ids: {})
    db.add(ScheduledOutfit(owner_id=db.user.id, date=date(2026, 7, 15), item_ids=[a, b]))
    db.commit()

    result = retrieve_references(db, db.user.id, {"season": "ete"}, _unit(10))

    assert result["historical"] == []
    assert result["catalog"] == {}


def test_deleted_items_drop_a_group_below_the_threshold(db, no_catalog, monkeypatch):
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    _seed_items(db, a, b, c)
    # only `a` still has an embedding in Pinecone (b, c were deleted) → group skipped
    _mock_fetch(monkeypatch, {a: _unit(10)})
    db.add(ScheduledOutfit(owner_id=db.user.id, date=date(2026, 7, 15), item_ids=[a, b, c]))
    db.commit()

    result = retrieve_references(db, db.user.id, {"season": "ete"}, _unit(10))

    assert result["historical"] == []  # 1 embedding < MIN_EMBEDDINGS (2)


def test_deleted_items_are_ignored_but_the_group_survives_with_two_present(db, no_catalog, monkeypatch):
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    _seed_items(db, a, b, c)
    # `c` was deleted from Pinecone; `a` and `b` remain → the group survives on the two
    # present items, scored over just those (review-F10).
    _mock_fetch(monkeypatch, {a: _unit(10), b: _unit(11)})
    db.add(ScheduledOutfit(owner_id=db.user.id, date=date(2026, 7, 15), item_ids=[a, b, c]))
    db.commit()

    result = retrieve_references(db, db.user.id, {"season": "ete"}, _unit(10), top_n_history=5)

    historical = result["historical"]
    assert len(historical) == 1
    assert set(historical[0]["item_ids"]) == {a, b}  # deleted c dropped, a/b kept


def test_catalog_is_grouped_by_dressme_category(db, monkeypatch):
    # No historical data, so only the catalog path is exercised.
    products = pd.DataFrame([
        {"item_key": "kontakt_top-noir", "name": "Top noir", "dressme_category": "haut",
         "brand": "Kontakt", "price_tnd": 40.0, "image_location": "u1"},
        {"item_key": "lyoum_top-blanc", "name": "Top blanc", "dressme_category": "haut",
         "brand": "Lyoum", "price_tnd": 60.0, "image_location": "u2"},
        {"item_key": "ha_123", "name": "Jean", "dressme_category": "bas",
         "brand": "Hamadi Abid", "price_tnd": None, "image_location": "u3"},
    ]).astype(object)
    vectors = np.eye(3, 512, dtype=np.float32)
    monkeypatch.setattr(catalog_index, "_load_index", lambda: (products, vectors))

    result = retrieve_references(db, db.user.id, {"season": "ete"}, _unit(0), top_k_catalog=5)

    catalog = result["catalog"]
    assert set(catalog.keys()) == {"haut", "bas"}
    assert [m["name"] for m in catalog["haut"]] == ["Top noir", "Top blanc"]
    assert catalog["bas"][0]["name"] == "Jean"
    assert "similarity" in catalog["haut"][0]


def test_missing_catalog_returns_empty_without_crashing(db, monkeypatch):
    monkeypatch.setattr(catalog_index, "_load_index",
                        lambda: (pd.DataFrame(), np.empty((0, 512), dtype=np.float32)))
    a, b = uuid.uuid4(), uuid.uuid4()
    _seed_items(db, a, b)
    _mock_fetch(monkeypatch, {a: _unit(10), b: _unit(11)})
    db.add(ScheduledOutfit(owner_id=db.user.id, date=date(2026, 7, 15), item_ids=[a, b]))
    db.commit()

    result = retrieve_references(db, db.user.id, {"season": "ete"}, _unit(10))

    assert result["catalog"] == {}
    assert len(result["historical"]) == 1  # history still works without the catalog


def test_db_error_returns_empty_history_without_crashing(db, no_catalog, monkeypatch):
    def raising_query(*args, **kwargs):
        raise RuntimeError("DB down")

    monkeypatch.setattr(db, "query", raising_query)

    result = retrieve_references(db, db.user.id, {"season": "ete"}, _unit(10))

    assert result["historical"] == []  # DB failure → WARNING + empty, never raised
    assert result["catalog"] == {}

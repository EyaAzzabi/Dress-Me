"""Unit tests for app/ml/preference_dataset.py.

Uses entirely in-memory fakes — no real DB or Pinecone connection required.
"""

from __future__ import annotations

import uuid
from typing import Any

import numpy as np
import pytest

from app.ml.preference_dataset import build_preference_pairs, get_outfit_embeddings


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeOutfit:
    def __init__(self, n_items: int = 2):
        self.item_ids = [uuid.uuid4() for _ in range(n_items)]


class FakeVectorStore:
    """Returns a fixed 512-d vector for every requested item id."""

    def fetch_embeddings(self, ids: list[str]) -> dict[str, list[float]]:
        return {iid: [0.1] * 512 for iid in ids}


class EmptyVectorStore:
    """Always returns an empty dict — simulates no stored embeddings."""

    def fetch_embeddings(self, ids: list[str]) -> dict[str, list[float]]:
        return {}


class _FakeFeedbackRow:
    def __init__(self, outfit: FakeOutfit, rating: str):
        self.outfit = outfit
        self.rating = rating
        self.owner_id = uuid.uuid4()


class FakeDB:
    """Minimal SQLAlchemy Session mock that supports .query(...).filter(...).all()."""

    def __init__(self, rows: list[_FakeFeedbackRow]):
        self._rows = rows

    def query(self, *_args):
        return self

    def filter(self, *_args):
        return self

    def all(self) -> list[_FakeFeedbackRow]:
        return self._rows


class RaisingDB:
    """A DB that always raises on .query()."""

    def query(self, *_args):
        raise RuntimeError("DB connection failed")


# ---------------------------------------------------------------------------
# (a) get_outfit_embeddings returns one 512-d array per item found
# ---------------------------------------------------------------------------

def test_get_outfit_embeddings_returns_one_array_per_item():
    outfit = FakeOutfit(n_items=3)
    vs = FakeVectorStore()
    result = get_outfit_embeddings(outfit, vs)
    assert len(result) == 3
    for arr in result:
        assert isinstance(arr, np.ndarray)
        assert arr.shape == (512,)


# ---------------------------------------------------------------------------
# (b) get_outfit_embeddings returns [] when vector_store returns {}
# ---------------------------------------------------------------------------

def test_get_outfit_embeddings_returns_empty_when_no_embeddings():
    outfit = FakeOutfit(n_items=2)
    vs = EmptyVectorStore()
    result = get_outfit_embeddings(outfit, vs)
    assert result == []


# ---------------------------------------------------------------------------
# (c) build_preference_pairs with 1 liked + 1 disliked returns 1 pair
# ---------------------------------------------------------------------------

def test_build_preference_pairs_one_liked_one_disliked():
    liked_outfit = FakeOutfit(n_items=2)
    disliked_outfit = FakeOutfit(n_items=2)
    rows = [
        _FakeFeedbackRow(liked_outfit, "like"),
        _FakeFeedbackRow(disliked_outfit, "dislike"),
    ]
    db = FakeDB(rows)
    vs = FakeVectorStore()

    pairs = build_preference_pairs(db, str(uuid.uuid4()), vs)

    assert len(pairs) == 1
    preferred_embs, rejected_embs = pairs[0]
    assert len(preferred_embs) == 2
    assert len(rejected_embs) == 2


# ---------------------------------------------------------------------------
# (d) build_preference_pairs skips pair when embeddings are empty
# ---------------------------------------------------------------------------

def test_build_preference_pairs_skips_empty_embeddings():
    liked_outfit = FakeOutfit(n_items=2)
    disliked_outfit = FakeOutfit(n_items=2)
    rows = [
        _FakeFeedbackRow(liked_outfit, "like"),
        _FakeFeedbackRow(disliked_outfit, "dislike"),
    ]
    db = FakeDB(rows)
    vs = EmptyVectorStore()

    pairs = build_preference_pairs(db, str(uuid.uuid4()), vs)

    assert pairs == []


# ---------------------------------------------------------------------------
# (e) build_preference_pairs returns [] when db.query raises
# ---------------------------------------------------------------------------

def test_build_preference_pairs_returns_empty_on_db_error():
    db = RaisingDB()
    vs = FakeVectorStore()

    pairs = build_preference_pairs(db, str(uuid.uuid4()), vs)

    assert pairs == []

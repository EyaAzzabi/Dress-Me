"""Unit tests for app/ml/preference_dataset.py and app/ml/embedding_fetcher.py.

Uses entirely in-memory fakes — no real DB or Pinecone connection required.
"""

from __future__ import annotations

import uuid
from typing import Any

import numpy as np
import pytest

from app.ml.preference_dataset import build_preference_pairs
from app.ml.embedding_fetcher import get_outfit_embeddings, filter_pairs_by_embeddings


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeOutfit:
    def __init__(self, n_items: int = 2):
        self.id = uuid.uuid4()
        self.item_ids = [uuid.uuid4() for _ in range(n_items)]


# ---------------------------------------------------------------------------
# (a) get_outfit_embeddings: function signature matches new embedding_fetcher API
# ---------------------------------------------------------------------------

def test_get_outfit_embeddings_importable():
    """get_outfit_embeddings is importable from app.ml.embedding_fetcher."""
    from app.ml.embedding_fetcher import get_outfit_embeddings as goe
    assert callable(goe)


def test_filter_pairs_by_embeddings_importable():
    """filter_pairs_by_embeddings is importable from app.ml.embedding_fetcher."""
    from app.ml.embedding_fetcher import filter_pairs_by_embeddings as fpbe
    assert callable(fpbe)


# ---------------------------------------------------------------------------
# (b) filter_pairs_by_embeddings keeps valid pairs, drops missing
# ---------------------------------------------------------------------------

def test_filter_pairs_keeps_pairs_with_both_embeddings():
    """Pairs where both outfits have embeddings are retained."""
    oid_a = str(uuid.uuid4())
    oid_b = str(uuid.uuid4())
    oid_c = str(uuid.uuid4())

    embeddings = {
        oid_a: np.array([0.1] * 512, dtype=np.float32),
        oid_b: np.array([0.2] * 512, dtype=np.float32),
        # oid_c has no embedding
    }
    pairs = [
        (oid_a, oid_b, 0.75),   # both present → valid
        (oid_a, oid_c, 0.25),   # oid_c missing → dropped
    ]
    valid, dropped = filter_pairs_by_embeddings(pairs, embeddings)
    assert len(valid) == 1
    assert len(dropped) == 1
    # valid pair contains embeddings attached
    oa, emb_a, emb_b, weight = valid[0]
    assert oa == oid_a
    assert emb_a.shape == (512,)
    assert emb_b.shape == (512,)
    assert weight == 0.75


def test_filter_pairs_all_dropped_when_no_embeddings():
    """All pairs dropped when embeddings dict is empty."""
    oid_a = str(uuid.uuid4())
    oid_b = str(uuid.uuid4())
    pairs = [(oid_a, oid_b, 0.5)]
    valid, dropped = filter_pairs_by_embeddings(pairs, {})
    assert valid == []
    assert len(dropped) == 1


def test_filter_pairs_empty_input():
    """Empty input returns empty output."""
    valid, dropped = filter_pairs_by_embeddings([], {})
    assert valid == []
    assert dropped == []


# ---------------------------------------------------------------------------
# (c) build_preference_pairs error handling (DB errors)
# ---------------------------------------------------------------------------

class RaisingDB:
    """A DB that always raises on .query()."""

    def query(self, *_args):
        raise RuntimeError("DB connection failed")


def test_build_preference_pairs_returns_empty_on_db_error():
    """Returns ([], metadata) when db.query raises, never crashes."""
    db = RaisingDB()
    pairs, meta = build_preference_pairs(db, str(uuid.uuid4()))
    assert pairs == []
    assert isinstance(meta, dict)
    assert "pair_count" in meta
    assert meta["pair_count"] == 0
    assert meta["ready_for_training"] is False


def test_build_preference_pairs_invalid_user_id():
    """Returns ([], metadata) when user_id is not a valid UUID."""
    import unittest.mock as mock

    class FakeDB:
        def query(self, *a):
            return self
        def filter(self, *a):
            return self
        def order_by(self, *a):
            return self
        def all(self):
            return []

    pairs, meta = build_preference_pairs(FakeDB(), "not-a-uuid")
    assert pairs == []
    assert meta["pair_count"] == 0


# ---------------------------------------------------------------------------
# (d) build_preference_pairs returns (list, dict) with correct metadata keys
# ---------------------------------------------------------------------------

def test_build_preference_pairs_returns_tuple_with_metadata():
    """Return value is always (list, dict) with required metadata keys."""
    import unittest.mock as mock

    class FakeDB:
        def query(self, *a):
            return self
        def filter(self, *a):
            return self
        def order_by(self, *a):
            return self
        def all(self):
            return []

    result = build_preference_pairs(FakeDB(), str(uuid.uuid4()))
    assert isinstance(result, tuple)
    pairs, meta = result
    assert isinstance(pairs, list)
    assert isinstance(meta, dict)
    for key in ("pair_count", "feedback_count", "filtered_outfits", "ready_for_training"):
        assert key in meta, f"Missing metadata key: {key}"


# ---------------------------------------------------------------------------
# (e) Legacy call: build_preference_pairs(db, user_id, vector_store) still works
# ---------------------------------------------------------------------------

def test_build_preference_pairs_legacy_call_does_not_crash():
    """Old 3-arg call (db, user_id, vector_store) must not crash (backward compat)."""
    import unittest.mock as mock

    class FakeDB:
        def query(self, *a):
            return self
        def filter(self, *a):
            return self
        def order_by(self, *a):
            return self
        def all(self):
            return []

    fake_vs = object()  # any non-None sentinel
    result = build_preference_pairs(FakeDB(), str(uuid.uuid4()), fake_vs)
    assert isinstance(result, tuple)
    pairs, meta = result
    assert isinstance(pairs, list)

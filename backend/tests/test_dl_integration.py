"""Integration tests for FEAT-002: DL scoring in RecommendationAgent.

Verifies that:
- dl_score is present in every outfit dict from RecommendationAgent.run()
- alpha == 0.6 and beta == 0.4
- Graceful fallback when outfit_transformer_module is None
- preference_reward == 0.5 when no reward model is trained
- _maybe_train_reward_model returns None when db is None
- combined == alpha * transformer_compatibility + beta * preference_reward
"""

import uuid

import numpy as np
import pytest

from app.agents.recommendation_agent import (
    RecommendationAgent,
    RecommendationState,
    _maybe_train_reward_model,
)
from app.ml import ranking_model


class _FakeItem:
    def __init__(self, category: str, style: str | None = None, season: str | None = "toutes_saisons"):
        self.id = uuid.uuid4()
        self.owner_id = uuid.uuid4()
        self.category = category
        self.style = style
        self.season = season
        self.colors = ["blanc"]


@pytest.fixture(autouse=True)
def _clear_ranking_caches():
    ranking_model._load_model.cache_clear()
    ranking_model._load_vectors.cache_clear()
    yield
    ranking_model._load_model.cache_clear()
    ranking_model._load_vectors.cache_clear()


@pytest.fixture
def basic_items(monkeypatch):
    """Two wardrobe items with patched compatibility."""
    items = [_FakeItem("haut"), _FakeItem("bas")]
    monkeypatch.setattr(
        "app.agents.recommendation_agent.compatibility_model.pair_compatibility",
        lambda a, b, **k: 0.5,
    )
    return items


def test_dl_score_key_present_in_every_outfit(basic_items):
    """dl_score key must be present in every outfit dict returned by run()."""
    result = RecommendationAgent().run(wardrobe_items=basic_items, top_k=1)

    assert result["outfits"], "Expected at least one outfit"
    for outfit in result["outfits"]:
        assert "dl_score" in outfit, "dl_score key missing from outfit"
        dl = outfit["dl_score"]
        assert "transformer_compatibility" in dl
        assert "preference_reward" in dl
        assert "combined" in dl
        assert "alpha" in dl
        assert "beta" in dl


def test_dl_score_alpha_beta_values(basic_items):
    """alpha must be 0.6 and beta must be 0.4."""
    result = RecommendationAgent().run(wardrobe_items=basic_items, top_k=1)

    assert result["outfits"]
    dl = result["outfits"][0]["dl_score"]
    assert dl["alpha"] == 0.6
    assert dl["beta"] == 0.4


def test_dl_score_fallback_when_transformer_module_none(basic_items, monkeypatch):
    """When outfit_transformer_module is None, transformer_compatibility falls back to relevance_score."""
    monkeypatch.setattr(
        "app.agents.recommendation_agent.outfit_transformer_module", None
    )

    result = RecommendationAgent().run(wardrobe_items=basic_items, top_k=1)

    assert result["outfits"]
    outfit = result["outfits"][0]
    dl = outfit["dl_score"]
    assert dl["transformer_compatibility"] == pytest.approx(outfit["relevance_score"])


def test_dl_score_preference_reward_is_half_when_no_db(basic_items):
    """preference_reward == 0.5 when db=None (no reward model trained)."""
    result = RecommendationAgent().run(wardrobe_items=basic_items, top_k=1, db=None)

    assert result["outfits"]
    dl = result["outfits"][0]["dl_score"]
    assert dl["preference_reward"] == pytest.approx(0.5)


def test_maybe_train_reward_model_returns_none_when_db_none():
    """_maybe_train_reward_model returns None when state has db=None."""
    state: RecommendationState = {
        "db": None,
        "user_id": str(uuid.uuid4()),
    }
    result = _maybe_train_reward_model(state)
    assert result is None


def test_dl_score_combined_formula(basic_items):
    """combined == alpha * transformer_compatibility + beta * preference_reward."""
    result = RecommendationAgent().run(wardrobe_items=basic_items, top_k=1)

    assert result["outfits"]
    dl = result["outfits"][0]["dl_score"]
    expected = 0.6 * dl["transformer_compatibility"] + 0.4 * dl["preference_reward"]
    assert dl["combined"] == pytest.approx(expected)

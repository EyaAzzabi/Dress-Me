import uuid

import numpy as np
import pytest

from app.agents.recommendation_agent import RecommendationAgent


class _FakeItem:
    def __init__(self, category: str, style: str | None = None):
        self.id = uuid.uuid4()
        self.category = category
        self.style = style


def _unit(vector: np.ndarray) -> list[float]:
    return (vector / np.linalg.norm(vector)).tolist()


@pytest.fixture
def rng():
    return np.random.default_rng(0)


def test_builds_haut_bas_and_robe_bases(monkeypatch, rng):
    items = [_FakeItem("haut"), _FakeItem("bas"), _FakeItem("robe"), _FakeItem("chaussures")]
    embeddings = {str(item.id): _unit(rng.normal(size=512)) for item in items}
    monkeypatch.setattr(
        "app.agents.recommendation_agent.vector_store.fetch_embeddings", lambda ids: embeddings
    )

    result = RecommendationAgent().run(wardrobe_items=items, top_k=5)

    # haut+bas is one base, robe alone is another — both should produce a candidate
    assert len(result["outfits"]) == 2
    for outfit in result["outfits"]:
        assert -1 <= outfit["relevance_score"] <= 1  # cosine similarity range
        assert isinstance(outfit["explanation"], str) and outfit["explanation"]


def test_coherent_wardrobe_scores_higher_than_random(monkeypatch, rng):
    direction = rng.normal(size=512)
    coherent_items = [_FakeItem("haut"), _FakeItem("bas")]
    coherent_embeddings = {
        str(item.id): _unit(direction + rng.normal(size=512) * 0.05) for item in coherent_items
    }
    monkeypatch.setattr(
        "app.agents.recommendation_agent.vector_store.fetch_embeddings",
        lambda ids: coherent_embeddings,
    )
    coherent_result = RecommendationAgent().run(wardrobe_items=coherent_items, top_k=1)

    random_items = [_FakeItem("haut"), _FakeItem("bas")]
    random_embeddings = {str(item.id): _unit(rng.normal(size=512)) for item in random_items}
    monkeypatch.setattr(
        "app.agents.recommendation_agent.vector_store.fetch_embeddings", lambda ids: random_embeddings
    )
    random_result = RecommendationAgent().run(wardrobe_items=random_items, top_k=1)

    assert coherent_result["outfits"][0]["relevance_score"] > random_result["outfits"][0]["relevance_score"]


def test_no_embeddings_returns_empty(monkeypatch):
    items = [_FakeItem("haut"), _FakeItem("bas")]
    monkeypatch.setattr("app.agents.recommendation_agent.vector_store.fetch_embeddings", lambda ids: {})

    result = RecommendationAgent().run(wardrobe_items=items)

    assert result["outfits"] == []


def test_missing_bottom_category_skips_base(monkeypatch, rng):
    # Only a haut, no bas and no robe — no valid base exists.
    items = [_FakeItem("haut")]
    embeddings = {str(item.id): _unit(rng.normal(size=512)) for item in items}
    monkeypatch.setattr(
        "app.agents.recommendation_agent.vector_store.fetch_embeddings", lambda ids: embeddings
    )

    result = RecommendationAgent().run(wardrobe_items=items)

    assert result["outfits"] == []


def test_favorite_style_bonus_breaks_a_tie(monkeypatch, rng):
    # Two outfits with near-identical visual coherence; only one is entirely in the
    # user's favorite style. It should win, and say so in its explanation.
    direction = rng.normal(size=512)
    casual_haut, casual_bas = _FakeItem("haut", "Casual"), _FakeItem("bas", "Casual")
    formal_haut, formal_bas = _FakeItem("haut", "Formal"), _FakeItem("bas", "Formal")
    items = [casual_haut, casual_bas, formal_haut, formal_bas]
    embeddings = {str(item.id): _unit(direction + rng.normal(size=512) * 0.05) for item in items}
    monkeypatch.setattr(
        "app.agents.recommendation_agent.vector_store.fetch_embeddings", lambda ids: embeddings
    )

    result = RecommendationAgent().run(
        wardrobe_items=items, favorite_styles=["Casual"], top_k=4
    )

    best = result["outfits"][0]
    assert best["item_ids"] == [casual_haut.id, casual_bas.id]
    assert "Casual" in best["explanation"]


def test_no_favorite_styles_means_no_bonus(monkeypatch, rng):
    items = [_FakeItem("haut", "Casual"), _FakeItem("bas", "Casual")]
    embeddings = {str(item.id): _unit(rng.normal(size=512)) for item in items}
    monkeypatch.setattr(
        "app.agents.recommendation_agent.vector_store.fetch_embeddings", lambda ids: embeddings
    )

    result = RecommendationAgent().run(wardrobe_items=items, favorite_styles=[])

    assert "Casual" not in result["outfits"][0]["explanation"]

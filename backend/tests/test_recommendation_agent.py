import uuid

import numpy as np
import pytest

from app.agents.recommendation_agent import RecommendationAgent
from app.core.config import get_settings
from app.ml import ranking_model


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


class _ContextRanker:
    """Picklable stand-in for the trained LogisticRegression ranker whose class-1
    probability rises with ``context_fit`` (feature 1) only, so an in-context outfit
    outranks an out-of-context one at equal visual coherence. Defined at module level
    so joblib can pickle/unpickle it by qualified name within this test process."""

    def __init__(self, w_context: float = 4.0, bias: float = -2.0):
        self.w = float(w_context)
        self.b = float(bias)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        z = self.w * X[:, 1] + self.b
        p1 = 1.0 / (1.0 + np.exp(-z))
        return np.stack([1.0 - p1, p1], axis=1)


@pytest.fixture(autouse=True)
def _clear_ranking_caches():
    # ranking_model's @lru_cache loaders are module-level and persist across tests;
    # clear them around each test so a monkeypatched MODEL_PATH takes effect and no
    # fake model leaks into the next test.
    ranking_model._load_model.cache_clear()
    ranking_model._load_vectors.cache_clear()
    yield
    ranking_model._load_model.cache_clear()
    ranking_model._load_vectors.cache_clear()


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


# --- FEAT-005: ranking-enabled ordering, LLM off / LLM mocked explanations -----


def test_ranking_enabled_ranks_in_context_outfit_above_out_of_context(monkeypatch, tmp_path):
    # On the ranking-enabled path, context_fit (mean(outfit_vecs) . ctx_vec) breaks a
    # tie at equal visual coherence. Two single-robe outfits (visual=1.0 for both,
    # since a 1-item outfit short-circuits pairwise compatibility to 1.0): one aligned
    # with ctx_vec, one orthogonal -> the aligned one wins on context_fit.
    import joblib

    monkeypatch.setenv("RANKING_ENABLED", "true")
    get_settings.cache_clear()

    model_path = tmp_path / "ranking_model.joblib"
    joblib.dump(_ContextRanker(), model_path)
    monkeypatch.setattr(ranking_model, "MODEL_PATH", model_path)
    ranking_model._load_model.cache_clear()

    axis0 = np.zeros(ranking_model.CONTEXT_DIM, dtype=np.float32)
    axis0[0] = 1.0
    axis1 = np.zeros(ranking_model.CONTEXT_DIM, dtype=np.float32)
    axis1[1] = 1.0

    in_robe, out_robe = _FakeItem("robe"), _FakeItem("robe")
    items = [in_robe, out_robe]
    embeddings = {str(in_robe.id): axis0.tolist(), str(out_robe.id): axis1.tolist()}
    monkeypatch.setattr(
        "app.agents.recommendation_agent.vector_store.fetch_embeddings", lambda ids: embeddings
    )

    result = RecommendationAgent().run(wardrobe_items=items, top_k=4, ctx_vec=axis0)

    assert len(result["outfits"]) == 2
    assert result["outfits"][0]["item_ids"] == [in_robe.id]
    assert result["outfits"][0]["relevance_score"] > result["outfits"][1]["relevance_score"]


def test_llm_off_uses_the_template_explanation(monkeypatch, rng):
    # No llm_agent injected -> the deterministic template (contains "match").
    items = [_FakeItem("haut"), _FakeItem("bas")]
    embeddings = {str(item.id): _unit(rng.normal(size=512)) for item in items}
    monkeypatch.setattr(
        "app.agents.recommendation_agent.vector_store.fetch_embeddings", lambda ids: embeddings
    )

    result = RecommendationAgent().run(wardrobe_items=items)

    assert "match" in result["outfits"][0]["explanation"].lower()


def test_injected_llm_explanation_is_used(monkeypatch, rng):
    # An injected LLM whose explain_outfit returns a short string is used verbatim.
    items = [_FakeItem("haut"), _FakeItem("bas")]
    embeddings = {str(item.id): _unit(rng.normal(size=512)) for item in items}
    monkeypatch.setattr(
        "app.agents.recommendation_agent.vector_store.fetch_embeddings", lambda ids: embeddings
    )

    class _LLM:
        def explain_outfit(self, facts):
            return "LLM expliqué"

    result = RecommendationAgent().run(wardrobe_items=items, llm_agent=_LLM())

    assert result["outfits"][0]["explanation"] == "LLM expliqué"


def test_injected_llm_explanation_is_truncated_to_2048(monkeypatch, rng):
    # A long LLM explanation is truncated to Outfit.explanation's 2048 chars
    # (review-F7).
    items = [_FakeItem("haut"), _FakeItem("bas")]
    embeddings = {str(item.id): _unit(rng.normal(size=512)) for item in items}
    monkeypatch.setattr(
        "app.agents.recommendation_agent.vector_store.fetch_embeddings", lambda ids: embeddings
    )

    long_text = "x" * 3000

    class _LLM:
        def explain_outfit(self, facts):
            return long_text

    result = RecommendationAgent().run(wardrobe_items=items, llm_agent=_LLM())

    explanation = result["outfits"][0]["explanation"]
    assert explanation == long_text[:2048]
    assert len(explanation) == 2048

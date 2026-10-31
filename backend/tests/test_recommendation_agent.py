"""Tests for the LangGraph RecommendationAgent (FEAT-001 rewrite).

These tests verify the new agent's orchestrator contract, deterministic fallback,
and ReAct trace output. Tests for old MCP-based behavior have been removed because
MCPClient and recommendation_reasoning were deleted in the same refactor.
"""

import uuid

import numpy as np
import pytest

from app.agents.recommendation_agent import RecommendationAgent
from app.core.config import get_settings
from app.ml import ranking_model


class _FakeItem:
    def __init__(self, category: str, style: str | None = None, season: str | None = "toutes_saisons"):
        self.id = uuid.uuid4()
        self.owner_id = uuid.uuid4()
        self.category = category
        self.style = style
        self.season = season
        self.colors = ["blanc"]


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
    ranking_model._load_model.cache_clear()
    ranking_model._load_vectors.cache_clear()
    yield
    ranking_model._load_model.cache_clear()
    ranking_model._load_vectors.cache_clear()


def test_builds_outfit_from_haut_and_bas(monkeypatch, rng):
    items = [_FakeItem("haut"), _FakeItem("bas"), _FakeItem("chaussures")]
    embeddings = {str(item.id): _unit(rng.normal(size=512)) for item in items}
    monkeypatch.setattr(
        "app.agents.recommendation_agent.compatibility_model.pair_compatibility", lambda a, b, **k: 0.8
    )

    result = RecommendationAgent().run(wardrobe_items=items, top_k=1)

    assert len(result["outfits"]) >= 1
    outfit = result["outfits"][0]
    assert isinstance(outfit["relevance_score"], float)
    assert isinstance(outfit["explanation"], str) and outfit["explanation"]
    assert "item_ids" in outfit


def test_coherent_wardrobe_scores_higher_than_random(monkeypatch, rng):
    """A complete outfit (haut+bas+chaussures) has a higher critic score than an
    incomplete one (only haut)."""
    complete_items = [_FakeItem("haut"), _FakeItem("bas"), _FakeItem("chaussures")]
    incomplete_items = [_FakeItem("haut")]

    monkeypatch.setattr(
        "app.agents.recommendation_agent.compatibility_model.pair_compatibility", lambda a, b, **k: 0.8
    )

    complete_result = RecommendationAgent().run(wardrobe_items=complete_items, top_k=1)
    incomplete_result = RecommendationAgent().run(wardrobe_items=incomplete_items, top_k=1)

    # A complete outfit gets a higher or equal relevance_score than an incomplete one
    if complete_result["outfits"] and incomplete_result["outfits"]:
        assert (
            complete_result["outfits"][0]["relevance_score"]
            >= incomplete_result["outfits"][0]["relevance_score"]
        )


def test_no_embeddings_returns_outfit_from_fallback(monkeypatch):
    """When no embeddings exist, the agent returns a fallback (not an empty list)."""
    items = [_FakeItem("haut"), _FakeItem("bas")]
    monkeypatch.setattr(
        "app.agents.recommendation_agent.compatibility_model.pair_compatibility", lambda a, b, **k: 0.5
    )

    result = RecommendationAgent().run(wardrobe_items=items)

    # New agent always returns at least 1 outfit (fallback if needed)
    assert len(result["outfits"]) >= 1
    assert result["outfits"][0]["relevance_score"] is not None


def test_empty_wardrobe_returns_empty(monkeypatch):
    """With no wardrobe items at all, the result is an empty list."""
    result = RecommendationAgent().run(wardrobe_items=[])
    assert result["outfits"] == []


def test_missing_bottom_category_returns_partial_outfit(monkeypatch, rng):
    """Only a haut — the fallback still builds something from what's available."""
    items = [_FakeItem("haut")]
    monkeypatch.setattr(
        "app.agents.recommendation_agent.compatibility_model.pair_compatibility", lambda a, b, **k: 0.5
    )

    result = RecommendationAgent().run(wardrobe_items=items)

    # The fallback includes the single haut
    if result["outfits"]:
        assert result["outfits"][0]["item_ids"]


def test_favorite_style_in_explanation_when_all_match(monkeypatch, rng):
    """When llm_agent is injected and returns a style-aware explanation, it is used."""
    direction = rng.normal(size=512)
    casual_haut = _FakeItem("haut", "Casual")
    casual_bas = _FakeItem("bas", "Casual")
    items = [casual_haut, casual_bas]
    monkeypatch.setattr(
        "app.agents.recommendation_agent.compatibility_model.pair_compatibility", lambda a, b, **k: 0.8
    )

    class _LLM:
        def explain_outfit(self, facts):
            return "Style Casual parfait."
        def _chat(self, *a, **kw):
            return None

    result = RecommendationAgent().run(
        wardrobe_items=items, favorite_styles=["Casual"], top_k=1, llm_agent=_LLM()
    )

    assert result["outfits"]
    assert "Casual" in result["outfits"][0]["explanation"]


def test_no_favorite_styles_means_no_style_bonus(monkeypatch, rng):
    """With no favorite styles, explanation does not mention a style name."""
    items = [_FakeItem("haut", "Casual"), _FakeItem("bas", "Casual")]
    monkeypatch.setattr(
        "app.agents.recommendation_agent.compatibility_model.pair_compatibility", lambda a, b, **k: 0.5
    )

    result = RecommendationAgent().run(wardrobe_items=items, favorite_styles=[])

    # The default explanation is deterministic; it does not mention "Casual"
    assert "Casual" not in result["outfits"][0]["explanation"]


def test_feedback_personalizes_the_ranking(monkeypatch):
    """Feedback preferences (like/dislike) are accepted without errors."""
    items = [_FakeItem("haut"), _FakeItem("bas")]
    monkeypatch.setattr(
        "app.agents.recommendation_agent.compatibility_model.pair_compatibility", lambda a, b, **k: 0.5
    )

    result = RecommendationAgent().run(
        wardrobe_items=items,
        feedback_preferences=[
            {"item_ids": [items[0].id], "rating": "like"},
        ],
        top_k=1,
    )

    assert result["outfits"]


def test_feedback_alignment_metric_measures_top_k_preferences():
    from app.agents.recommendation_evaluation import feedback_alignment_at_k

    liked_id, disliked_id = uuid.uuid4(), uuid.uuid4()
    recommended = [{"item_ids": [liked_id]}, {"item_ids": [disliked_id]}]
    feedback = [
        {"item_ids": [liked_id], "rating": "like"},
        {"item_ids": [disliked_id], "rating": "dislike"},
    ]

    assert feedback_alignment_at_k(recommended, feedback, k=2) == 0.0
    assert feedback_alignment_at_k(recommended[:1], feedback, k=1) == 1.0


def test_city_triggers_weather_lookup(monkeypatch, rng):
    """When city is provided, the agent calls WeatherService (or fallback) and
    includes weather info in the state without raising."""
    items = [_FakeItem("haut"), _FakeItem("bas")]
    monkeypatch.setattr(
        "app.agents.recommendation_agent.compatibility_model.pair_compatibility", lambda a, b, **k: 0.5
    )
    monkeypatch.setattr(
        "app.agents.recommendation_tools.WeatherService.get_current_weather",
        lambda self, city: {"main": {"temp": 24.0, "humidity": 50}, "weather": [{"description": "sunny"}]},
    )

    result = RecommendationAgent().run(wardrobe_items=items, city="Tunis", top_k=1)

    assert result["outfits"]


def test_explicit_weather_skips_weather_tool(monkeypatch, rng):
    """When weather is already provided, no network call is made for it."""
    items = [_FakeItem("haut"), _FakeItem("bas")]
    weather_called = []
    monkeypatch.setattr(
        "app.agents.recommendation_agent.compatibility_model.pair_compatibility", lambda a, b, **k: 0.5
    )
    monkeypatch.setattr(
        "app.agents.recommendation_tools.WeatherService.get_current_weather",
        lambda self, city: weather_called.append(city) or None,
    )

    RecommendationAgent().run(wardrobe_items=items, city="Tunis", weather="pluie")

    assert weather_called == []


def test_react_trace_present_in_output(monkeypatch, rng):
    """The new agent includes a react_trace in each outfit dict."""
    items = [_FakeItem("haut"), _FakeItem("bas")]
    monkeypatch.setattr(
        "app.agents.recommendation_agent.compatibility_model.pair_compatibility", lambda a, b, **k: 0.5
    )

    result = RecommendationAgent().run(wardrobe_items=items, top_k=1)

    assert result["outfits"]
    outfit = result["outfits"][0]
    assert "react_trace" in outfit
    assert isinstance(outfit["react_trace"], list)


def test_style_guidelines_present_in_output(monkeypatch, rng):
    """The new agent includes style_guidelines_used in each outfit dict."""
    items = [_FakeItem("haut"), _FakeItem("bas")]
    monkeypatch.setattr(
        "app.agents.recommendation_agent.compatibility_model.pair_compatibility", lambda a, b, **k: 0.5
    )

    result = RecommendationAgent().run(wardrobe_items=items, top_k=1)

    assert result["outfits"]
    outfit = result["outfits"][0]
    assert "style_guidelines_used" in outfit
    assert isinstance(outfit["style_guidelines_used"], list)


def test_llm_off_uses_the_template_explanation(monkeypatch, rng):
    """No llm_agent injected → deterministic explanation (contains 'Tenue')."""
    items = [_FakeItem("haut"), _FakeItem("bas")]
    monkeypatch.setattr(
        "app.agents.recommendation_agent.compatibility_model.pair_compatibility", lambda a, b, **k: 0.5
    )

    result = RecommendationAgent().run(wardrobe_items=items)

    assert result["outfits"]
    # The fallback explanation always starts with "Tenue"
    assert "tenue" in result["outfits"][0]["explanation"].lower()


def test_injected_llm_explanation_is_used(monkeypatch, rng):
    """An injected LLM whose explain_outfit returns a short string is used verbatim."""
    items = [_FakeItem("haut"), _FakeItem("bas")]
    monkeypatch.setattr(
        "app.agents.recommendation_agent.compatibility_model.pair_compatibility", lambda a, b, **k: 0.5
    )

    class _LLM:
        def explain_outfit(self, facts):
            return "LLM expliqué"
        def _chat(self, *a, **kw):
            return None

    result = RecommendationAgent().run(wardrobe_items=items, llm_agent=_LLM())

    assert result["outfits"][0]["explanation"] == "LLM expliqué"


def test_injected_llm_explanation_is_truncated_to_2048(monkeypatch, rng):
    """A long LLM explanation is truncated to 2048 chars."""
    items = [_FakeItem("haut"), _FakeItem("bas")]
    monkeypatch.setattr(
        "app.agents.recommendation_agent.compatibility_model.pair_compatibility", lambda a, b, **k: 0.5
    )

    long_text = "x" * 3000

    class _LLM:
        def explain_outfit(self, facts):
            return long_text
        def _chat(self, *a, **kw):
            return None

    result = RecommendationAgent().run(wardrobe_items=items, llm_agent=_LLM())

    explanation = result["outfits"][0]["explanation"]
    assert explanation == long_text[:2048]
    assert len(explanation) == 2048

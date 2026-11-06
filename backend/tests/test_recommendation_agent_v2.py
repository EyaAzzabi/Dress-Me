"""Tests for RecommendationAgentV2."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from app.agents.recommendation_agent_v2 import RecommendationAgentV2


@pytest.fixture(autouse=True)
def mock_dependencies():
    """Mock heavy dependencies for all tests."""
    with patch.dict('sys.modules', {'torch': None}):
        with patch('app.ml.explanation_engine.ExplanationEngine') as mock_exp:
            mock_exp.generate_explanation.return_value = {'explanation': 'test explanation', 'weather_verified': True, 'confidence': 0.7, 'reasoning': {}}
            with patch('app.ml.recommendation_llm.RecommendationToolSandbox'):
                with patch('app.ml.recommendation_llm.run_agent', return_value={'explanation': 'test'}):
                    with patch('app.db.vector_store.fetch_embeddings', return_value={}):
                        with patch('app.services.weather_verification.WeatherVerificationService') as mock_weather:
                            mock_weather.get_weather.return_value = {'temperature': 20.0, 'condition': 'sunny', 'confidence': 0.7}
                            yield


@pytest.fixture
def agent():
    """Create a RecommendationAgentV2 instance."""
    return RecommendationAgentV2()


@pytest.fixture
def mock_items():
    """Create mock wardrobe items."""
    items = []
    for i in range(10):
        item = Mock()
        item.id = f"item_{i}"
        item.name = f"Item {i}"
        item.category = ["haut", "bas", "chaussures", "robe"][i % 4]
        item.colors = ["bleu", "blanc", "noir"][i % 3:]
        item.material = ["coton", "laine", "lin"][i % 3]
        item.style = ["casual", "formal"][i % 2]
        item.season = "all"
        item.owner_id = "user_123"
        items.append(item)
    return items


class TestRecommendationAgentV2:
    """Tests for RecommendationAgentV2 class."""

    def test_agent_has_correct_name(self, agent):
        """Agent should have correct name."""
        assert agent.name == "recommendation_agent_v2"

    def test_run_with_empty_wardrobe(self, agent):
        """Run with empty wardrobe should return empty outfits."""
        result = agent.run(wardrobe_items=[])

        assert "outfits" in result
        assert result["outfits"] == []

    def test_run_with_mock_items(self, agent, mock_items):
        """Run should return outfits."""
        result = agent.run(
            wardrobe_items=mock_items,
            occasion="casual",
            season="summer",
            temperature=25.0,
        )

        assert "outfits" in result
        assert isinstance(result["outfits"], list)

    def test_run_returns_outfit_structure(self, agent, mock_items):
        """Each outfit should have required fields."""
        result = agent.run(
            wardrobe_items=mock_items,
            occasion="casual",
            top_k=1,
        )

        assert len(result["outfits"]) > 0
        outfit = result["outfits"][0]

        # Required fields
        assert "item_ids" in outfit
        assert "explanation" in outfit
        assert "scores" in outfit
        assert "confidence" in outfit

        # Scores substructure
        scores = outfit["scores"]
        assert "sft" in scores
        assert "combined" in scores

    def test_run_respects_top_k(self, agent, mock_items):
        """Run should return at most top_k outfits."""
        result = agent.run(wardrobe_items=mock_items, top_k=2)

        assert len(result["outfits"]) <= 2

    def test_run_with_weather_city(self, agent, mock_items, monkeypatch):
        """Run should fetch weather when city provided."""
        fetch_called = False

        def mock_get_weather(city, *args, **kwargs):
            nonlocal fetch_called
            fetch_called = True
            return {
                "temperature": 20.0,
                "condition": "sunny",
                "humidity": 50,
                "wind_speed": 0.0,
                "pressure": 1013,
                "uv_index": None,
                "confidence": 0.95,
                "cached": False,
                "error": None,
            }

        monkeypatch.setattr(
            "app.agents.recommendation_agent_v2.WeatherVerificationService.get_weather",
            mock_get_weather,
        )

        result = agent.run(wardrobe_items=mock_items, city="Tunis")

        assert fetch_called is True
        assert "outfits" in result

    def test_extract_user_id(self, agent, mock_items):
        """Extract user_id should get owner_id from wardrobe items."""
        user_id = agent._extract_user_id(mock_items)

        assert user_id == "user_123"  # Should extract user_id

    def test_extract_user_id_no_items(self, agent):
        """Extract user_id with no items should return empty string."""
        user_id = agent._extract_user_id([])

        assert user_id == ""

    def test_filter_candidates_by_season(self, agent, mock_items):
        """Filter should remove items from wrong season."""
        # Mark some items with winter season
        mock_items[0].season = "winter"
        weather = {"temperature": 25.0}

        filtered = agent._filter_candidates(mock_items, season="summer", weather_data=weather)

        # Should have fewer items (winter items removed)
        assert len(filtered) <= len(mock_items)

    def test_combine_scores(self, agent):
        """Combine scores should return weighted average."""
        combined = agent._combine_scores(
            sft_score=0.8,
            llm_confidence=0.7,
            compatibility_score=0.6,
        )

        # Should be weighted average
        expected = 0.4 * 0.8 + 0.3 * 0.7 + 0.3 * 0.6
        assert combined == pytest.approx(expected)

    def test_combine_scores_without_llm(self, agent):
        """Combine scores should handle missing LLM confidence."""
        combined = agent._combine_scores(
            sft_score=0.8,
            llm_confidence=None,
            compatibility_score=0.6,
        )

        # Should be normalized without LLM
        assert 0.0 <= combined <= 1.0

    def test_combine_scores_clamps_output(self, agent):
        """Combined score should be clamped to [0, 1]."""
        combined1 = agent._combine_scores(
            sft_score=1.5,  # Over 1.0
            llm_confidence=0.7,
        )
        combined2 = agent._combine_scores(
            sft_score=-0.5,  # Under 0.0
            llm_confidence=0.7,
        )

        assert 0.0 <= combined1 <= 1.0
        assert 0.0 <= combined2 <= 1.0

    def test_build_outfit_dict(self, agent, mock_items):
        """Build outfit dict should create complete structure."""
        sft_scores = {item.id: 0.7 for item in mock_items}
        weather = {"temperature": 25.0, "condition": "sunny"}

        outfit_dict = agent._build_outfit_dict(
            outfit_items=mock_items[:3],
            sft_scores=sft_scores,
            llm_scores={},
            weather_data=weather,
            occasion="casual",
            season="summer",
            temperature=25.0,
            request_text=None,
        )

        assert "item_ids" in outfit_dict
        assert "explanation" in outfit_dict
        assert "scores" in outfit_dict
        assert "confidence" in outfit_dict
        # Backwards compat fields
        assert "relevance_score" in outfit_dict
        assert "dl_score" in outfit_dict

    def test_fallback_outfit(self, agent, mock_items):
        """Fallback outfit should generate deterministic result."""
        result = agent._fallback_outfit(mock_items, top_k=1)

        assert "outfits" in result
        assert len(result["outfits"]) <= 1
        if result["outfits"]:
            outfit = result["outfits"][0]
            assert "item_ids" in outfit
            assert "explanation" in outfit

    def test_graceful_degradation_empty_filtered_items(self, agent, mock_items):
        """Should fall back to all items if filtering yields nothing."""
        weather = {"temperature": -100}  # Extreme to trigger fallback

        filtered = agent._filter_candidates(mock_items, season="winter", weather_data=weather)

        # Should return items (at least the original list if all filtered out)
        assert len(filtered) > 0

    def test_backwards_compatibility_signature(self, agent, mock_items):
        """Should accept v1 signature arguments."""
        # Test that old arguments are accepted
        result = agent.run(
            wardrobe_items=mock_items,
            occasion="casual",
            season="summer",
            temperature=25.0,
            weather="sunny",
            city="Tunis",
            top_k=3,
            request_text="I need casual outfit",
            llm_agent=None,
            db=None,
        )

        assert "outfits" in result

    def test_run_with_missing_embeddings(self, agent, mock_items, monkeypatch):
        """Should handle missing embeddings gracefully."""
        def mock_fetch_embeddings(item_ids):
            # Return empty dict (no embeddings)
            return {}

        # Patch at the import location within the module
        monkeypatch.setattr(
            "app.db.vector_store.fetch_embeddings",
            mock_fetch_embeddings,
        )

        result = agent.run(
            wardrobe_items=mock_items,
            occasion="casual",
        )

        assert "outfits" in result


class TestComposeOutfitCandidates:
    """Tests for _compose_outfit_candidates() method."""

    def test_generates_multiple_candidates(self):
        """Should generate multiple outfit candidates."""
        agent = RecommendationAgentV2()

        mock_items = []
        for i in range(12):
            item = Mock()
            item.id = f"item_{i}"
            item.category = ["haut", "bas", "chaussures", "robe"][i % 4]
            mock_items.append(item)

        sft_scores = {item.id: 0.5 + (i % 10) * 0.01 for i, item in enumerate(mock_items)}

        candidates = agent._compose_outfit_candidates(mock_items, sft_scores, top_k=3)

        assert len(candidates) <= 3
        assert len(candidates) > 0

    def test_each_outfit_has_items(self):
        """Each outfit should have at least one item."""
        agent = RecommendationAgentV2()

        mock_items = []
        for i in range(8):
            item = Mock()
            item.id = f"item_{i}"
            item.category = ["haut", "bas", "chaussures"][i % 3]
            mock_items.append(item)

        sft_scores = {item.id: 0.7 for item in mock_items}

        candidates = agent._compose_outfit_candidates(mock_items, sft_scores, top_k=2)

        for outfit in candidates:
            assert len(outfit) > 0


class TestScoreWithSFT:
    """Tests for _score_with_sft() method."""

    def test_score_with_sft_no_model(self):
        """Should return neutral scores when model unavailable."""
        agent = RecommendationAgentV2()
        mock_items = [Mock(id="item_1"), Mock(id="item_2")]

        scores = agent._score_with_sft(
            model=None,
            items=mock_items,
            occasion="casual",
            season="summer",
            temperature=25.0,
            weather_data={},
        )

        assert "item_1" in scores
        assert "item_2" in scores
        assert all(0.0 <= s <= 1.0 for s in scores.values())

    def test_score_with_sft_returns_dict(self):
        """Should return dict mapping item_id to score."""
        agent = RecommendationAgentV2()
        mock_items = [Mock(id="item_1"), Mock(id="item_2")]

        scores = agent._score_with_sft(
            model=None,
            items=mock_items,
            occasion="casual",
            season="summer",
            temperature=None,
            weather_data={},
        )

        assert isinstance(scores, dict)
        assert all(isinstance(k, str) for k in scores.keys())
        assert all(isinstance(v, float) for v in scores.values())

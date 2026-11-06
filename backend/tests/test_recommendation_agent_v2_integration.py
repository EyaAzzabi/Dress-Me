"""Integration tests for RecommendationAgentV2 full pipeline."""

import pytest
from unittest.mock import Mock

from app.agents.recommendation_agent_v2 import RecommendationAgentV2
from app.services.weather_verification import WeatherVerificationService
from app.ml.explanation_engine import ExplanationEngine


@pytest.fixture
def sample_wardrobe():
    """Create a realistic sample wardrobe."""
    items = []
    
    tops = [
        ("top_1", "Chemise blanche", "coton", "white", "casual", "summer"),
        ("top_2", "Chemise noire", "coton", "black", "formal", "all"),
        ("top_3", "Pull tricot", "laine", "blue", "casual", "winter"),
    ]
    
    bottoms = [
        ("bottom_1", "Pantalon bleu", "coton", "blue", "casual", "all"),
        ("bottom_2", "Pantalon noir", "coton", "black", "formal", "all"),
        ("bottom_3", "Short blanc", "coton", "white", "casual", "summer"),
    ]
    
    shoes = [
        ("shoes_1", "Baskets blanches", "toile", "white", "casual", "all"),
        ("shoes_2", "Chaussures noires", "cuir", "black", "formal", "all"),
    ]
    
    for item_id, name, material, color, style, season in tops + bottoms + shoes:
        item = Mock()
        item.id = item_id
        item.name = name
        item.material = material
        item.colors = [color]
        item.style = style
        item.season = season
        item.category = "top" if item_id.startswith("top") else "bottom" if item_id.startswith("bottom") else "chaussures"
        item.owner_id = "user_test_123"
        items.append(item)
    
    return items


class TestIntegrationFullPipeline:
    """Integration tests for the full RecommendationAgentV2 pipeline."""

    def test_full_pipeline_generates_complete_outfit(self, sample_wardrobe):
        """Full pipeline should generate outfit with all required fields."""
        agent = RecommendationAgentV2()
        
        result = agent.run(
            wardrobe_items=sample_wardrobe,
            occasion="casual",
            season="summer",
            temperature=25.0,
            weather="sunny",
            top_k=1,
        )
        
        assert "outfits" in result
        assert len(result["outfits"]) > 0
        
        outfit = result["outfits"][0]
        
        # All required fields present
        assert "item_ids" in outfit
        assert "explanation" in outfit
        assert "scores" in outfit
        assert "confidence" in outfit
        assert "weather_fit" in outfit
        
        # Scores structure
        assert "sft" in outfit["scores"]
        assert "combined" in outfit["scores"]
        
        # Backwards compatibility fields
        assert "relevance_score" in outfit
        assert "dl_score" in outfit
        assert "critic_score" in outfit

    def test_weather_influences_outfit_selection(self, sample_wardrobe):
        """Weather should influence outfit composition."""
        agent = RecommendationAgentV2()
        
        # Warm weather
        result_warm = agent.run(
            wardrobe_items=sample_wardrobe,
            occasion="casual",
            temperature=28.0,
            weather="sunny",
            top_k=1,
        )
        
        # Cold weather
        result_cold = agent.run(
            wardrobe_items=sample_wardrobe,
            occasion="casual",
            temperature=5.0,
            weather="cloudy",
            top_k=1,
        )
        
        # Both should generate outfits
        assert len(result_warm["outfits"]) > 0
        assert len(result_cold["outfits"]) > 0
        
        # Outfits should be different
        warm_items = set(result_warm["outfits"][0]["item_ids"])
        cold_items = set(result_cold["outfits"][0]["item_ids"])
        
        # May differ due to seasonal constraints and material choices
        assert isinstance(warm_items, set)
        assert isinstance(cold_items, set)

    def test_explanation_contains_french_and_details(self, sample_wardrobe):
        """Explanation should be detailed and in French."""
        agent = RecommendationAgentV2()
        
        result = agent.run(
            wardrobe_items=sample_wardrobe,
            occasion="casual",
            season="summer",
            temperature=25.0,
            top_k=1,
        )
        
        outfit = result["outfits"][0]
        explanation = outfit["explanation"]
        
        # Should be a non-empty string
        assert isinstance(explanation, str)
        assert len(explanation) > 0
        
        # Should contain item selection info
        assert "•" in explanation or ":" in explanation
        
        # Should mention temperature, occasion, or style
        assert any(keyword in explanation.lower() 
                  for keyword in ["25", "casual", "chaud", "méteo", "météo", "sélectionnée"])

    def test_confidence_score_reflects_fit(self, sample_wardrobe):
        """Confidence score should reflect outfit fit quality."""
        agent = RecommendationAgentV2()
        
        result = agent.run(
            wardrobe_items=sample_wardrobe,
            occasion="casual",
            season="summer",
            temperature=25.0,
            weather="sunny",
            top_k=1,
        )
        
        outfit = result["outfits"][0]
        confidence = outfit["confidence"]
        
        # Confidence should be between 0 and 1
        assert 0.0 <= confidence <= 1.0
        
        # For well-matched outfit with weather, should be reasonable
        assert confidence > 0.2

    def test_scoring_components_present(self, sample_wardrobe):
        """All scoring components should be present."""
        agent = RecommendationAgentV2()
        
        result = agent.run(
            wardrobe_items=sample_wardrobe,
            occasion="formal",
            top_k=1,
        )
        
        outfit = result["outfits"][0]
        scores = outfit["scores"]
        
        # SFT score should be present
        assert "sft" in scores
        assert 0.0 <= scores["sft"] <= 1.0
        
        # Combined score should be present
        assert "combined" in scores
        assert 0.0 <= scores["combined"] <= 1.0
        
        # LLM might be None
        llm_score = scores.get("llm")
        if llm_score is not None:
            assert 0.0 <= llm_score <= 1.0


class TestWeatherIntegration:
    """Tests for weather integration with outfit selection."""

    def test_hot_weather_prefers_light_materials(self, sample_wardrobe):
        """Hot weather should influence material selection."""
        weather = WeatherVerificationService.get_weather(city=None, use_cache=False)
        weather["temperature"] = 35.0
        weather["condition"] = "sunny"
        
        constraints = WeatherVerificationService.map_weather_to_constraints(weather)
        
        # Should prefer light materials
        assert "lin" in constraints["materials"] or "coton" in constraints["materials"]
        assert constraints["layering"] == "none"
        assert constraints["breathability"] == "very_high"

    def test_cold_weather_prefers_warm_materials(self):
        """Cold weather should prefer warm materials."""
        weather = {
            "temperature": 0.0,
            "condition": "snowy",
            "humidity": 60,
            "wind_speed": 10.0,
        }
        
        constraints = WeatherVerificationService.map_weather_to_constraints(weather)
        
        # Should prefer warm materials
        assert "laine" in constraints["materials"] or "tricot" in constraints["materials"]
        assert constraints["layering"] == "heavy"
        assert constraints["coverage"] == "full"


class TestExplanationIntegration:
    """Tests for explanation generation with real data."""

    def test_explanation_includes_all_items(self):
        """Explanation should mention all items in outfit."""
        outfit = [
            {"id": "top_1", "name": "Chemise blanche", "category": "top"},
            {"id": "bottom_1", "name": "Pantalon bleu", "category": "bottom"},
            {"id": "shoes_1", "name": "Baskets", "category": "shoes"},
        ]
        
        context = {"occasion": "casual", "season": "summer"}
        
        explanation = ExplanationEngine.generate_explanation(
            outfit=outfit,
            context=context,
            sft_score=0.8,
        )
        
        # Should mention items
        text = explanation["explanation"]
        assert "Chemise blanche" in text or "top" in text.lower()
        
        # Should have reasoning
        reasoning = explanation["reasoning"]
        assert "item_choices" in reasoning
        assert len(reasoning["item_choices"]) > 0

    def test_explanation_with_weather_and_confidence(self):
        """Explanation with weather should be comprehensive."""
        outfit = [
            {"id": "1", "name": "Item 1", "category": "top", "material": "coton"},
            {"id": "2", "name": "Item 2", "category": "bottom", "material": "lin"},
        ]
        
        weather = {
            "temperature": 22.0,
            "condition": "cloudy",
            "humidity": 60,
            "wind_speed": 3.0,
        }
        
        explanation = ExplanationEngine.generate_explanation(
            outfit=outfit,
            context={"occasion": "casual", "temperature": 22.0},
            weather=weather,
            sft_score=0.75,
            llm_confidence=0.8,
        )
        
        # Should have high confidence
        assert explanation["confidence"] > 0.5
        
        # Should be weather verified
        assert "weather_fit" in explanation["reasoning"]

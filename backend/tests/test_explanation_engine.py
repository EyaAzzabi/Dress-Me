"""Tests for ExplanationEngine."""

import pytest

from app.ml.explanation_engine import ExplanationEngine


class TestGenerateExplanation:
    """Tests for generate_explanation() method."""

    def test_empty_outfit_returns_minimal_explanation(self):
        """Empty outfit should return minimal dict."""
        result = ExplanationEngine.generate_explanation(
            outfit=[],
            context={"occasion": "casual"},
        )

        assert isinstance(result, dict)
        assert "explanation" in result
        assert "reasoning" in result
        assert "confidence" in result
        assert result["confidence"] == 0.0

    def test_explanation_contains_french_text(self):
        """Explanation should contain French text."""
        outfit = [
            {
                "id": "item1",
                "name": "Chemise blanche",
                "category": "top",
                "colors": ["blanc"],
                "material": "coton",
                "style": "casual",
            },
            {
                "id": "item2",
                "name": "Pantalon bleu",
                "category": "bottom",
                "colors": ["bleu"],
                "material": "coton",
                "style": "casual",
            },
        ]
        context = {
            "occasion": "casual",
            "season": "summer",
            "temperature": 25.0,
        }

        result = ExplanationEngine.generate_explanation(
            outfit=outfit,
            context=context,
            sft_score=0.8,
        )

        # Should contain item names
        assert "Chemise blanche" in result["explanation"]
        assert "Pantalon bleu" in result["explanation"]

        # Should contain French keywords
        assert ("Sélectionnée pour" in result["explanation"]
                or "matière" in result["explanation"]
                or "casual" in result["explanation"].lower())

    def test_explanation_with_weather(self):
        """Explanation should include weather verification."""
        outfit = [
            {
                "id": "item1",
                "name": "Chemise",
                "category": "top",
                "colors": ["blanc"],
                "material": "coton",
            },
            {
                "id": "item2",
                "name": "Pantalon",
                "category": "bottom",
                "colors": ["bleu"],
                "material": "coton",
            },
        ]
        weather = {
            "temperature": 25.0,
            "condition": "sunny",
            "humidity": 45,
            "wind_speed": 1.0,
        }
        context = {"occasion": "casual", "temperature": 25.0}

        result = ExplanationEngine.generate_explanation(
            outfit=outfit,
            context=context,
            weather=weather,
            sft_score=0.8,
        )

        # Should mention weather
        assert "Météo" in result["explanation"] or "25" in result["explanation"]
        assert result["weather_verified"] is not None

    def test_reasoning_structure(self):
        """Reasoning dict should have expected structure."""
        outfit = [
            {
                "id": "item1",
                "name": "Chemise",
                "category": "top",
                "colors": ["blanc"],
            },
        ]
        context = {"occasion": "casual"}

        result = ExplanationEngine.generate_explanation(outfit, context)

        reasoning = result.get("reasoning", {})
        assert "item_choices" in reasoning
        assert isinstance(reasoning["item_choices"], list)
        assert "weather_fit" in reasoning
        assert "occasion_fit" in reasoning

    def test_confidence_score_bounds(self):
        """Confidence should be between 0 and 1."""
        outfit = [
            {
                "id": "item1",
                "name": "Chemise",
                "category": "top",
                "colors": ["blanc"],
            },
            {
                "id": "item2",
                "name": "Pantalon",
                "category": "bottom",
                "colors": ["bleu"],
            },
        ]
        context = {"occasion": "casual"}

        result = ExplanationEngine.generate_explanation(outfit, context, sft_score=0.9)

        confidence = result.get("confidence", 0.0)
        assert 0.0 <= confidence <= 1.0

    def test_with_high_sft_score(self):
        """High SFT score should increase confidence."""
        outfit = [
            {"id": "item1", "name": "Item1", "category": "top"},
            {"id": "item2", "name": "Item2", "category": "bottom"},
        ]
        context = {}

        result_low = ExplanationEngine.generate_explanation(outfit, context, sft_score=0.3)
        result_high = ExplanationEngine.generate_explanation(outfit, context, sft_score=0.9)

        assert result_high.get("confidence", 0.0) > result_low.get("confidence", 0.0)


class TestExplainItemChoice:
    """Tests for _explain_item_choice() method."""

    def test_returns_french_string(self):
        """Should return French explanation string."""
        item = {
            "name": "Chemise coton",
            "category": "top",
            "colors": ["blanc"],
            "material": "coton",
            "style": "casual",
        }
        context = {"occasion": "casual", "season": "summer"}

        result = ExplanationEngine._explain_item_choice(item, context)

        assert isinstance(result, str)
        assert len(result) > 0
        # Should contain French or English keywords
        assert any(keyword in result.lower() for keyword in ["sélectionnée", "coton", "casual", "choice"])

    def test_includes_material_and_style(self):
        """Should mention material and style when available."""
        item = {
            "name": "Chemise",
            "category": "top",
            "material": "soie",
            "style": "formal",
        }
        context = {"occasion": "business"}

        result = ExplanationEngine._explain_item_choice(item, context)

        assert "soie" in result or "formal" in result or "business" in result


class TestVerifyWeatherFit:
    """Tests for _verify_weather_fit() method."""

    def test_weather_fit_includes_temperature(self):
        """Weather fit text should include temperature info."""
        outfit = [{"id": "item1", "category": "top"}]
        weather = {"temperature": 25.0, "condition": "sunny"}
        fit_result = {"fit_score": 0.8, "warnings": []}

        result = ExplanationEngine._verify_weather_fit(outfit, weather, fit_result)

        assert "25" in result or "sunny" in result.lower()

    def test_weather_fit_with_warnings(self):
        """Should include warnings in output."""
        outfit = [{"id": "item1", "category": "top"}]
        weather = {"temperature": 5.0, "condition": "cloudy"}
        fit_result = {
            "fit_score": 0.3,
            "warnings": ["Pas assez chaud"],
        }

        result = ExplanationEngine._verify_weather_fit(outfit, weather, fit_result)

        assert "Pas assez chaud" in result


class TestComputeConfidence:
    """Tests for _compute_confidence() method."""

    def test_with_no_scores(self):
        """Should return default confidence without scores."""
        result = ExplanationEngine._compute_confidence(
            sft_score=None,
            llm_confidence=None,
            weather_verified=False,
            outfit=[],
        )

        assert 0.0 <= result <= 1.0

    def test_sft_score_contribution(self):
        """SFT score should influence confidence."""
        result_low = ExplanationEngine._compute_confidence(
            sft_score=0.3,
            llm_confidence=None,
            weather_verified=False,
            outfit=[{"id": "1"}],
        )
        result_high = ExplanationEngine._compute_confidence(
            sft_score=0.9,
            llm_confidence=None,
            weather_verified=False,
            outfit=[{"id": "1"}],
        )

        assert result_high > result_low

    def test_weather_verified_boost(self):
        """Weather verification should boost confidence."""
        result_no_weather = ExplanationEngine._compute_confidence(
            sft_score=0.7,
            llm_confidence=None,
            weather_verified=False,
            outfit=[{"id": "1"}],
        )
        result_weather = ExplanationEngine._compute_confidence(
            sft_score=0.7,
            llm_confidence=None,
            weather_verified=True,
            outfit=[{"id": "1"}],
        )

        assert result_weather > result_no_weather

    def test_incomplete_outfit_penalty(self):
        """Incomplete outfit should reduce confidence."""
        result_complete = ExplanationEngine._compute_confidence(
            sft_score=0.8,
            llm_confidence=None,
            weather_verified=False,
            outfit=[{"id": "1"}, {"id": "2"}],
        )
        result_incomplete = ExplanationEngine._compute_confidence(
            sft_score=0.8,
            llm_confidence=None,
            weather_verified=False,
            outfit=[{"id": "1"}],
        )

        assert result_complete > result_incomplete

"""Tests for constraint_parser module.

Tests constraint extraction from French-language user requests using LLM
with fallback to regex when LLM is unavailable.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from app.ml.constraint_parser import ConstraintParser


class TestConstraintParserLLMPath:
    """Tests for LLM-based constraint parsing."""

    def test_color_extraction_via_llm(self, monkeypatch):
        """Test that 'touche de bleu' is parsed to colors=['bleu'] via LLM."""
        mock_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "colors": ["bleu"],
                        "styles": [],
                        "occasions": [],
                        "formality": None,
                        "season": None,
                        "notes": None,
                    })
                }
            }]
        }

        def mock_post(*args, **kwargs):
            resp = MagicMock()
            resp.json.return_value = mock_response
            resp.raise_for_status.return_value = None
            return resp

        monkeypatch.setattr("httpx.post", mock_post)

        parser = ConstraintParser()
        constraints = parser.parse("touche de bleu")

        assert "bleu" in constraints.get("colors", [])
        assert constraints.get("formality") is None

    def test_style_extraction_via_llm(self, monkeypatch):
        """Test that 'style casual' is parsed to styles=['casual'] via LLM."""
        mock_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "colors": [],
                        "styles": ["casual"],
                        "occasions": [],
                        "formality": None,
                        "season": None,
                        "notes": None,
                    })
                }
            }]
        }

        def mock_post(*args, **kwargs):
            resp = MagicMock()
            resp.json.return_value = mock_response
            resp.raise_for_status.return_value = None
            return resp

        monkeypatch.setattr("httpx.post", mock_post)

        parser = ConstraintParser()
        constraints = parser.parse("style casual")

        assert "casual" in constraints.get("styles", [])

    def test_occasion_extraction_via_llm(self, monkeypatch):
        """Test that 'occasion soirée' is parsed to occasions=['soirée'] via LLM."""
        mock_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "colors": [],
                        "styles": [],
                        "occasions": ["soirée"],
                        "formality": None,
                        "season": None,
                        "notes": None,
                    })
                }
            }]
        }

        def mock_post(*args, **kwargs):
            resp = MagicMock()
            resp.json.return_value = mock_response
            resp.raise_for_status.return_value = None
            return resp

        monkeypatch.setattr("httpx.post", mock_post)

        parser = ConstraintParser()
        constraints = parser.parse("occasion soirée")

        assert "soirée" in constraints.get("occasions", [])

    def test_combined_constraints_via_llm(self, monkeypatch):
        """Test that combined constraints are extracted correctly."""
        mock_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "colors": ["bleu"],
                        "styles": ["élégant"],
                        "occasions": ["soirée"],
                        "formality": "formal",
                        "season": None,
                        "notes": None,
                    })
                }
            }]
        }

        def mock_post(*args, **kwargs):
            resp = MagicMock()
            resp.json.return_value = mock_response
            resp.raise_for_status.return_value = None
            return resp

        monkeypatch.setattr("httpx.post", mock_post)

        parser = ConstraintParser()
        constraints = parser.parse("soirée élégante en bleu")

        assert "bleu" in constraints.get("colors", [])
        assert "élégant" in constraints.get("styles", [])
        assert "soirée" in constraints.get("occasions", [])
        assert constraints.get("formality") == "formal"


class TestConstraintParserRegexFallback:
    """Tests for regex-based fallback parsing."""

    def test_color_extraction_regex_fallback(self, monkeypatch):
        """Test that regex fallback extracts colors when LLM fails."""
        def mock_post(*args, **kwargs):
            raise ConnectionError("LLM unavailable")

        monkeypatch.setattr("httpx.post", mock_post)

        parser = ConstraintParser()
        constraints = parser.parse("touche de bleu")

        # Regex fallback should still work
        assert "bleu" in constraints.get("colors", [])

    def test_style_extraction_regex_fallback(self, monkeypatch):
        """Test that regex fallback extracts styles."""
        def mock_post(*args, **kwargs):
            raise TimeoutError("LLM timeout")

        monkeypatch.setattr("httpx.post", mock_post)

        parser = ConstraintParser()
        constraints = parser.parse("style casual")

        assert "casual" in constraints.get("styles", [])

    def test_occasion_extraction_regex_fallback(self, monkeypatch):
        """Test that regex fallback extracts occasions."""
        def mock_post(*args, **kwargs):
            raise RuntimeError("LLM error")

        monkeypatch.setattr("httpx.post", mock_post)

        parser = ConstraintParser()
        constraints = parser.parse("soirée élégante")

        assert "soirée" in constraints.get("occasions", [])

    def test_formality_extraction_regex_fallback(self, monkeypatch):
        """Test that formality is extracted by regex fallback."""
        def mock_post(*args, **kwargs):
            raise ConnectionError("LLM unavailable")

        monkeypatch.setattr("httpx.post", mock_post)

        parser = ConstraintParser()
        constraints = parser.parse("très formel")

        assert constraints.get("formality") == "formal"

    def test_season_extraction_regex_fallback(self, monkeypatch):
        """Test that season is extracted by regex fallback."""
        def mock_post(*args, **kwargs):
            raise ConnectionError("LLM unavailable")

        monkeypatch.setattr("httpx.post", mock_post)

        parser = ConstraintParser()
        constraints = parser.parse("tenue d'été")

        assert constraints.get("season") == "été"


class TestConstraintParserEdgeCases:
    """Tests for edge cases and error handling."""

    def test_none_input_returns_empty(self):
        """Test that None input returns empty constraints."""
        parser = ConstraintParser()
        constraints = parser.parse(None)

        assert constraints["colors"] == []
        assert constraints["styles"] == []
        assert constraints["occasions"] == []
        assert constraints["formality"] is None
        assert constraints["season"] is None

    def test_empty_string_input_returns_empty(self):
        """Test that empty string returns empty constraints."""
        parser = ConstraintParser()
        constraints = parser.parse("")

        assert constraints["colors"] == []
        assert constraints["styles"] == []
        assert constraints["occasions"] == []

    def test_whitespace_only_returns_empty(self):
        """Test that whitespace-only string returns empty constraints."""
        parser = ConstraintParser()
        constraints = parser.parse("   \n\t  ")

        assert constraints["colors"] == []
        assert constraints["styles"] == []
        assert constraints["occasions"] == []

    def test_llm_returns_invalid_json_falls_back_to_regex(self, monkeypatch):
        """Test that invalid JSON from LLM triggers regex fallback."""
        def mock_post(*args, **kwargs):
            resp = MagicMock()
            resp.json.return_value = {"choices": [{"message": {"content": "not json"}}]}
            resp.raise_for_status.return_value = None
            return resp

        monkeypatch.setattr("httpx.post", mock_post)

        parser = ConstraintParser()
        constraints = parser.parse("touche de bleu")

        # Should fall back to regex and still extract bleu
        assert "bleu" in constraints.get("colors", [])

    def test_schema_validation_normalizes_output(self, monkeypatch):
        """Test that output is normalized and schema-compliant."""
        mock_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "colors": ["BLEU", "ROUGE"],
                        "styles": ["  Casual  "],
                        "occasions": None,
                        "formality": "FORMAL",
                        "season": "ETE",
                        "notes": "  ",
                        "extra_field": "should_be_dropped",
                    })
                }
            }]
        }

        def mock_post(*args, **kwargs):
            resp = MagicMock()
            resp.json.return_value = mock_response
            resp.raise_for_status.return_value = None
            return resp

        monkeypatch.setattr("httpx.post", mock_post)

        parser = ConstraintParser()
        constraints = parser.parse("any text")

        # Check normalization: lowercase and stripped
        assert "bleu" in constraints["colors"]
        assert "rouge" in constraints["colors"]
        assert "casual" in constraints["styles"]
        assert constraints["formality"] == "formal"
        assert constraints["season"] == "ete"
        assert constraints["notes"] is None  # whitespace-only becomes None
        assert "extra_field" not in constraints  # unknown fields dropped

    def test_multiple_colors_deduplicated(self, monkeypatch):
        """Test that duplicate colors are deduplicated."""
        def mock_post(*args, **kwargs):
            raise ConnectionError()

        monkeypatch.setattr("httpx.post", mock_post)

        parser = ConstraintParser()
        # "bleu" appears in "bleu" and might match in "bleue"
        constraints = parser.parse("bleu et bleu clair")

        # Should have unique colors
        assert constraints["colors"].count("bleu") <= 1


class TestConstraintParserIntegration:
    """Integration tests combining both paths."""

    def test_graceful_degradation_llm_to_regex(self, monkeypatch):
        """Test that parser gracefully degrades from LLM to regex."""
        call_count = 0

        def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # First call succeeds (LLM path)
            if call_count == 1:
                resp = MagicMock()
                resp.json.return_value = {
                    "choices": [{
                        "message": {
                            "content": json.dumps({
                                "colors": ["bleu"],
                                "styles": [],
                                "occasions": [],
                                "formality": None,
                                "season": None,
                                "notes": None,
                            })
                        }
                    }]
                }
                resp.raise_for_status.return_value = None
                return resp
            # Second call fails (triggers fallback)
            raise ConnectionError("LLM unavailable")

        monkeypatch.setattr("httpx.post", mock_post)

        parser = ConstraintParser()
        
        # First parse: LLM succeeds
        c1 = parser.parse("touche de bleu")
        assert "bleu" in c1["colors"]
        
        # Second parse: LLM fails, regex fallback kicks in
        c2 = parser.parse("style casual et rouge")
        assert "casual" in c2["styles"]
        assert "rouge" in c2["colors"]

    def test_typical_french_user_request(self, monkeypatch):
        """Test a typical French user request with multiple constraints."""
        mock_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "colors": ["noir", "blanc"],
                        "styles": ["classique"],
                        "occasions": ["travail"],
                        "formality": "formal",
                        "season": "automne",
                        "notes": "Pour un entretien d'embauche",
                    })
                }
            }]
        }

        def mock_post(*args, **kwargs):
            resp = MagicMock()
            resp.json.return_value = mock_response
            resp.raise_for_status.return_value = None
            return resp

        monkeypatch.setattr("httpx.post", mock_post)

        parser = ConstraintParser()
        constraints = parser.parse(
            "Je cherche une tenue noire et blanche, classique et formelle pour un travail en automne"
        )

        assert "noir" in constraints["colors"]
        assert "blanc" in constraints["colors"]
        assert "classique" in constraints["styles"]
        assert "travail" in constraints["occasions"]
        assert constraints["formality"] == "formal"
        assert constraints["season"] == "automne"
        assert constraints["notes"] is not None

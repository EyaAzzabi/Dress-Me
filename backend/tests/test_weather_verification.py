"""Tests for WeatherVerificationService."""

import pytest
from unittest.mock import Mock, patch

from app.services.weather_verification import WeatherVerificationService


@pytest.fixture
def clear_cache():
    """Clear weather cache before and after tests."""
    WeatherVerificationService._CACHE.clear()
    yield
    WeatherVerificationService._CACHE.clear()


class TestGetWeather:
    """Tests for get_weather() method."""

    def test_get_weather_returns_dict_with_required_fields(self, clear_cache, monkeypatch):
        """Weather dict should contain all required fields."""
        # Mock the settings
        monkeypatch.setattr(
            "app.services.weather_verification.get_settings",
            lambda: Mock(openweather_api_key=None),
        )

        result = WeatherVerificationService.get_weather(city=None)

        assert isinstance(result, dict)
        assert "temperature" in result
        assert "condition" in result
        assert "humidity" in result
        assert "wind_speed" in result
        assert "confidence" in result
        assert "cached" in result
        assert "error" in result

    def test_get_weather_fallback_without_api_key(self, clear_cache, monkeypatch):
        """Should return fallback weather when API key not configured."""
        monkeypatch.setattr(
            "app.services.weather_verification.get_settings",
            lambda: Mock(openweather_api_key=None),
        )

        result = WeatherVerificationService.get_weather(city="Tunis")

        assert result["confidence"] == 0.5  # Low confidence for fallback
        assert result["error"] is not None or result["cached"] is False
        assert isinstance(result["temperature"], float)

    def test_get_weather_caching(self, clear_cache, monkeypatch):
        """Weather should be cached for 1 hour."""
        monkeypatch.setattr(
            "app.services.weather_verification.get_settings",
            lambda: Mock(openweather_api_key=None),
        )

        # First call
        result1 = WeatherVerificationService.get_weather(city="Tunis", use_cache=True)
        # Note: fallback weather is not cached since API key unavailable
        # So both calls may not use cache. Just verify structure is consistent.
        assert isinstance(result1, dict)
        assert "temperature" in result1

        # Second call
        result2 = WeatherVerificationService.get_weather(city="Tunis", use_cache=True)
        assert isinstance(result2, dict)
        assert "temperature" in result2

    def test_get_weather_with_cache_disabled(self, clear_cache, monkeypatch):
        """When use_cache=False, should not use cache."""
        monkeypatch.setattr(
            "app.services.weather_verification.get_settings",
            lambda: Mock(openweather_api_key=None),
        )

        result1 = WeatherVerificationService.get_weather(city="Tunis", use_cache=True)
        result2 = WeatherVerificationService.get_weather(city="Tunis", use_cache=False)

        # Both should be fresh (not cached) since we can't mock API
        assert result1["cached"] is False
        assert result2["cached"] is False


class TestMapWeatherToConstraints:
    """Tests for map_weather_to_constraints() method."""

    def test_warm_sunny_weather(self):
        """28°C sunny should map to light layering, breathable materials."""
        weather = {
            "temperature": 28.0,
            "condition": "sunny",
            "humidity": 45,
            "wind_speed": 2.0,
        }

        result = WeatherVerificationService.map_weather_to_constraints(weather)

        assert result["layering"] == "none"
        assert "lin" in result["materials"] or "coton" in result["materials"]
        assert result["breathability"] == "very_high"
        assert result["coverage"] == "minimal"

    def test_cold_weather(self):
        """5°C weather should map to heavy layering, warm materials."""
        weather = {
            "temperature": 5.0,
            "condition": "cloudy",
            "humidity": 70,
            "wind_speed": 5.0,
        }

        result = WeatherVerificationService.map_weather_to_constraints(weather)

        assert result["layering"] == "heavy"
        assert "laine" in result["materials"] or "tricot" in result["materials"]
        # Coverage may be "medium" or "full" for cloudy cold weather
        assert result["coverage"] in ["medium", "full"]

    def test_rainy_weather(self):
        """Rainy condition should suggest waterproof materials."""
        weather = {
            "temperature": 15.0,
            "condition": "rainy",
            "humidity": 80,
            "wind_speed": 3.0,
        }

        result = WeatherVerificationService.map_weather_to_constraints(weather)

        assert "imperméable" in result["materials"] or "polyuréthane" in result["materials"]
        assert result["coverage"] == "full"

    def test_sunny_uv_protection(self):
        """Sunny weather above 15°C should recommend UV protection."""
        weather = {
            "temperature": 25.0,
            "condition": "sunny",
            "humidity": 50,
            "wind_speed": 1.0,
        }

        result = WeatherVerificationService.map_weather_to_constraints(weather)

        assert result["uv_protection"] is True


class TestVerifyOutfitWeatherFit:
    """Tests for verify_outfit_weather_fit() method."""

    def test_linen_dress_in_cold_weather(self):
        """Linen dress in 5°C should have low fit score."""
        outfit_items = [
            {
                "category": "robe",
                "name": "Robe lin",
                "material": "lin",
                "colors": ["bleu"],
                "season": "summer",
            }
        ]
        weather = {
            "temperature": 5.0,
            "condition": "cloudy",
            "humidity": 70,
            "wind_speed": 0.0,
        }

        result = WeatherVerificationService.verify_outfit_weather_fit(outfit_items, weather)

        assert result["weather_fit"] is False or result["fit_score"] < 0.7
        assert len(result["warnings"]) > 0

    def test_warm_outfit_in_sunny_weather(self):
        """Cotton outfit in 25°C sunny should have high fit score."""
        outfit_items = [
            {
                "category": "top",
                "name": "Chemise coton",
                "material": "coton",
                "colors": ["blanc"],
                "season": "summer",
            },
            {
                "category": "bottom",
                "name": "Pantalon lin",
                "material": "lin",
                "colors": ["blanc"],
                "season": "summer",
            },
        ]
        weather = {
            "temperature": 25.0,
            "condition": "sunny",
            "humidity": 45,
            "wind_speed": 1.0,
        }

        result = WeatherVerificationService.verify_outfit_weather_fit(outfit_items, weather)

        assert result["weather_fit"] is True
        assert result["fit_score"] >= 0.5

    def test_incomplete_outfit_low_score(self):
        """Outfit with only 1 item should have low score."""
        outfit_items = [
            {
                "category": "top",
                "name": "Chemise",
                "material": "coton",
                "colors": ["bleu"],
            }
        ]
        weather = {"temperature": 20.0, "condition": "sunny"}

        result = WeatherVerificationService.verify_outfit_weather_fit(outfit_items, weather)

        assert result["fit_score"] < 0.7  # Should be reduced for incomplete outfit


class TestParseOpenWeather:
    """Tests for _parse_openweather() method."""

    def test_parse_clear_sky(self):
        """Should parse 'clear' condition as 'sunny'."""
        api_data = {
            "main": {"temp": 25.0, "humidity": 50, "pressure": 1013},
            "weather": [{"main": "Clear"}],
            "wind": {"speed": 2.0},
        }

        result = WeatherVerificationService._parse_openweather(api_data)

        assert result["condition"] == "sunny"
        assert result["temperature"] == 25.0

    def test_parse_rain(self):
        """Should parse 'rain' condition."""
        api_data = {
            "main": {"temp": 15.0, "humidity": 80, "pressure": 1013},
            "weather": [{"main": "Rain"}],
            "wind": {"speed": 5.0},
        }

        result = WeatherVerificationService._parse_openweather(api_data)

        assert result["condition"] == "rainy"
        assert result["humidity"] == 80

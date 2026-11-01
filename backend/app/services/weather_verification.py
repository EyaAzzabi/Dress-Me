"""Weather Verification Service — Real weather API + constraint mapping.

Fetches real weather from OpenWeather API with smart caching (1-hour TTL).
Maps weather conditions to outfit constraints (materials, layering, colors).
Verifies outfit fit against weather conditions.

All text user-facing and deterministic fallback in French.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class WeatherVerificationService:
    """Weather API client with caching and smart constraint mapping."""

    # In-memory cache: {city: {"data": {...}, "timestamp": datetime, "cached": bool}}
    _CACHE: dict[str, dict[str, Any]] = {}
    _CACHE_TTL = 3600  # 1 hour in seconds

    BASE_URL = "https://api.openweathermap.org/data/2.5/weather"

    # City coordinates for common Tunisian cities
    CITY_COORDS = {
        "Tunis": {"lat": 36.8190, "lon": 10.1658},
        "Sousse": {"lat": 35.8333, "lon": 10.6333},
        "Sfax": {"lat": 34.7406, "lon": 10.7603},
        "Djerba": {"lat": 33.8075, "lon": 10.8451},
    }

    @staticmethod
    def get_weather(
        city: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Fetch real weather from OpenWeather API or cache.

        Args:
            city: City name (will be looked up in CITY_COORDS if available)
            latitude: Latitude (overrides city lookup)
            longitude: Longitude (overrides city lookup)
            use_cache: Whether to use cache (default True)

        Returns:
            {
                "temperature": float (celsius),
                "condition": str (e.g., "sunny", "rainy", "cloudy"),
                "humidity": int (0-100, %),
                "wind_speed": float (m/s),
                "uv_index": float | None,
                "pressure": int (hPa),
                "confidence": float (0-1),
                "cached": bool,
                "error": str | None,
            }
        """
        settings = get_settings()

        # Check cache first if enabled
        if use_cache and city in WeatherVerificationService._CACHE:
            cached_entry = WeatherVerificationService._CACHE[city]
            age = (datetime.now() - cached_entry["timestamp"]).total_seconds()
            if age < WeatherVerificationService._CACHE_TTL:
                return {**cached_entry["data"], "cached": True}

        # Prepare API request
        if not settings.openweather_api_key:
            result = WeatherVerificationService._get_fallback_weather(city, latitude, longitude)
            return result

        try:
            # Use latitude/longitude if provided, otherwise lookup city
            if latitude is not None and longitude is not None:
                params = {
                    "lat": latitude,
                    "lon": longitude,
                    "appid": settings.openweather_api_key,
                    "units": "metric",
                }
            elif city and city in WeatherVerificationService.CITY_COORDS:
                coords = WeatherVerificationService.CITY_COORDS[city]
                params = {
                    "lat": coords["lat"],
                    "lon": coords["lon"],
                    "appid": settings.openweather_api_key,
                    "units": "metric",
                }
            elif city:
                # Fall back to city name if not in coords dict
                params = {
                    "q": city,
                    "appid": settings.openweather_api_key,
                    "units": "metric",
                }
            else:
                return WeatherVerificationService._get_fallback_weather(city, latitude, longitude)

            response = httpx.get(
                WeatherVerificationService.BASE_URL,
                params=params,
                timeout=5.0,
            )
            response.raise_for_status()
            api_data = response.json()

            # Parse API response
            result = WeatherVerificationService._parse_openweather(api_data)
            result["error"] = None

            # Cache the result
            if city:
                WeatherVerificationService._CACHE[city] = {
                    "data": {k: v for k, v in result.items() if k != "cached"},
                    "timestamp": datetime.now(),
                }

            return result

        except (httpx.HTTPError, httpx.HTTPStatusError, httpx.TimeoutException) as e:
            logger.warning(f"OpenWeather API error for {city}: {e}. Using fallback.")
            return WeatherVerificationService._get_fallback_weather(city, latitude, longitude)

    @staticmethod
    def _parse_openweather(api_data: dict[str, Any]) -> dict[str, Any]:
        """Parse OpenWeather API response.

        Args:
            api_data: Response from OpenWeather /weather endpoint

        Returns:
            Normalized weather dict
        """
        try:
            main = api_data.get("main", {})
            weather = api_data.get("weather", [{}])[0]
            wind = api_data.get("wind", {})

            condition_map = {
                "clear": "sunny",
                "sunny": "sunny",
                "rain": "rainy",
                "drizzle": "rainy",
                "clouds": "cloudy",
                "cloudy": "cloudy",
                "snow": "snowy",
                "thunderstorm": "stormy",
                "mist": "foggy",
                "smoke": "foggy",
                "haze": "foggy",
                "dust": "dusty",
                "sand": "dusty",
                "ash": "dusty",
                "squall": "windy",
                "tornado": "stormy",
            }
            condition = weather.get("main", "").lower()
            condition = condition_map.get(condition, condition)

            return {
                "temperature": float(main.get("temp", 20.0)),
                "condition": condition,
                "humidity": int(main.get("humidity", 50)),
                "wind_speed": float(wind.get("speed", 0.0)),
                "pressure": int(main.get("pressure", 1013)),
                "uv_index": None,  # OpenWeather free tier doesn't include UV
                "confidence": 0.95,  # High confidence from API
                "cached": False,
            }
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error parsing OpenWeather data: {e}")
            return WeatherVerificationService._get_fallback_weather(None, None, None)

    @staticmethod
    def _get_fallback_weather(
        city: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> dict[str, Any]:
        """Provide estimated weather when API is unavailable.

        Uses seasonal defaults based on current month.
        Assumes Mediterranean climate (Tunis region).

        Returns:
            Weather dict with low confidence
        """
        month = datetime.now().month

        # Seasonal temperature/conditions for Mediterranean climate
        if month in [12, 1, 2]:  # Winter
            temp = 12.0
            condition = "cloudy"
            humidity = 70
        elif month in [3, 4, 5]:  # Spring
            temp = 18.0
            condition = "sunny"
            humidity = 60
        elif month in [6, 7, 8]:  # Summer
            temp = 30.0
            condition = "sunny"
            humidity = 45
        else:  # Fall (9, 10, 11)
            temp = 22.0
            condition = "sunny"
            humidity = 55

        return {
            "temperature": temp,
            "condition": condition,
            "humidity": humidity,
            "wind_speed": 5.0,
            "pressure": 1013,
            "uv_index": None,
            "confidence": 0.5,  # Low confidence from fallback
            "cached": False,
            "error": "API unavailable, using seasonal defaults",
        }

    @staticmethod
    def map_weather_to_constraints(weather: dict[str, Any]) -> dict[str, Any]:
        """Map weather conditions to outfit constraints.

        Deterministic mapping: temperature + condition → materials, layering, colors.

        Args:
            weather: Weather dict from get_weather()

        Returns:
            {
                "layering": str (e.g., "none", "light", "medium", "heavy"),
                "materials": list[str] (e.g., ["coton", "lin", "soie"]),
                "colors": list[str] (e.g., ["clair", "pastel"]),
                "coverage": str (e.g., "light", "medium", "full"),
                "breathability": str (e.g., "high", "medium", "low"),
                "uv_protection": bool,
            }
        """
        temp = weather.get("temperature", 20.0)
        condition = weather.get("condition", "sunny").lower()
        humidity = weather.get("humidity", 50)

        # Temperature-based constraints
        if temp < 0:
            layering = "heavy"
            materials = ["laine", "tricot épais", "coton épais"]
            colors = ["foncé", "chaud"]
            coverage = "full"
            breathability = "low"
        elif temp < 10:
            layering = "heavy"
            materials = ["laine", "tricot", "coton épais", "velours"]
            colors = ["foncé", "chaud"]
            coverage = "full"
            breathability = "medium"
        elif temp < 15:
            layering = "medium"
            materials = ["coton", "tricot", "lin épais", "denim"]
            colors = ["neutre", "pastel"]
            coverage = "medium"
            breathability = "medium"
        elif temp < 20:
            layering = "light"
            materials = ["coton", "lin", "soie", "rayon"]
            colors = ["clair", "pastel", "neutre"]
            coverage = "light"
            breathability = "high"
        elif temp < 25:
            layering = "none"
            materials = ["lin", "coton léger", "soie", "rayon", "chanvre"]
            colors = ["clair", "blanc", "pastel"]
            coverage = "light"
            breathability = "high"
        else:  # >= 25
            layering = "none"
            materials = ["lin", "coton très léger", "chanvre", "viscose"]
            colors = ["blanc", "clair", "pastel", "couleur vive"]
            coverage = "minimal"
            breathability = "very_high"

        # Condition-based adjustments
        if "rain" in condition:
            if "breathability" not in locals():
                breathability = "medium"
            materials.extend(["imperméable", "polyuréthane"])
            coverage = "full"
        elif "cloud" in condition:
            coverage = "medium"
        elif "snow" in condition:
            coverage = "full"
            breathability = "low"
        elif "wind" in condition:
            layering = "heavy" if layering == "none" else layering
            materials.extend(["denim", "velours côtelé"])

        # UV protection recommendation for sunny conditions
        uv_protection = temp > 15 and ("sun" in condition or "clear" in condition)

        return {
            "layering": layering,
            "materials": materials,
            "colors": colors,
            "coverage": coverage,
            "breathability": breathability,
            "uv_protection": uv_protection,
        }

    @staticmethod
    def verify_outfit_weather_fit(
        outfit_items: list[dict[str, Any]],
        weather: dict[str, Any],
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Verify if outfit items fit weather conditions.

        Args:
            outfit_items: List of item dicts with keys:
                - category (str): e.g., "top", "bottom", "shoes", "accessories"
                - colors (list[str]): item colors
                - season (str | None): e.g., "spring", "summer", "fall", "winter"
                - material (str | None): e.g., "coton", "laine", "lin"
                - style (str | None): e.g., "casual", "formal", "sporty"
            weather: Weather dict from get_weather()
            temperature: Override weather temperature for verification

        Returns:
            {
                "weather_fit": bool,
                "fit_score": float (0-1),
                "warnings": list[str] (French),
                "recommendations": list[str] (French),
            }
        """
        temp = temperature or weather.get("temperature", 20.0)
        condition = weather.get("condition", "sunny").lower()
        constraints = WeatherVerificationService.map_weather_to_constraints(weather)

        warnings = []
        recommendations = []
        fit_score = 1.0

        # Check each item in outfit
        for item in outfit_items:
            category = item.get("category", "").lower()
            material = (item.get("material") or "").lower()
            season = (item.get("season") or "").lower()

            # Season mismatch
            if season and temp < 15 and "summer" in season:
                warnings.append(
                    f"{item.get('name', category)}: trop léger pour {temp}°C (saison été)"
                )
                fit_score -= 0.15
            elif season and temp > 25 and "winter" in season:
                warnings.append(
                    f"{item.get('name', category)}: trop chaud pour {temp}°C (saison hiver)"
                )
                fit_score -= 0.15

            # Material mismatch
            if material:
                if temp < 10 and material in ["lin", "soie", "viscose"]:
                    warnings.append(
                        f"{item.get('name', category)}: matière {material} pas assez chaude"
                    )
                    fit_score -= 0.2
                elif temp > 25 and material in ["laine", "velours", "denim épais"]:
                    warnings.append(
                        f"{item.get('name', category)}: matière {material} trop chaude"
                    )
                    fit_score -= 0.15

            # Weather condition check
            if "rain" in condition and category in ["shoes", "chaussures"]:
                if material not in ["imperméable", "caoutchouc", "polyuréthane"]:
                    recommendations.append(f"Chaussures imperméables recommandées (pluie)")

        # Overall fit assessment
        if len(outfit_items) < 2:
            warnings.append("Tenue incomplète (moins de 2 pièces)")
            fit_score = 0.3

        fit_score = max(0.0, min(1.0, fit_score))
        weather_fit = fit_score >= 0.5

        return {
            "weather_fit": weather_fit,
            "fit_score": fit_score,
            "warnings": warnings,
            "recommendations": recommendations,
        }

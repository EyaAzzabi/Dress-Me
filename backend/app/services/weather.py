import httpx

from app.core.config import get_settings


CITY_COORDS = {
    "Tunis":  {"lat": 36.8190, "lon": 10.1658},
    "Sousse": {"lat": 35.8333, "lon": 10.6333},
    "Sfax":   {"lat": 34.7406, "lon": 10.7603},
    "Djerba": {"lat": 33.8075, "lon": 10.8451},
}


class WeatherService:
    """Thin client for OpenWeather, used by the Context Agent."""

    BASE_URL = "https://api.openweathermap.org/data/2.5/weather"

    def __init__(self) -> None:
        self.settings = get_settings()

    def get_current_weather(self, city: str) -> dict | None:
        if not self.settings.openweather_api_key:
            return None
        try:
            coords = CITY_COORDS.get(city)
            if coords:
                params = {**coords, "appid": self.settings.openweather_api_key, "units": "metric"}
            else:
                params = {"q": city, "appid": self.settings.openweather_api_key, "units": "metric"}
            response = httpx.get(self.BASE_URL, params=params, timeout=5.0)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, httpx.HTTPStatusError):
            return self._get_fallback_weather(city)

    def _get_fallback_weather(self, city: str) -> dict:
        """Provide estimated weather when API is unavailable or key not activated yet"""
        from datetime import datetime
        
        # Estimate temperature based on month and typical climate
        month = datetime.now().month
        
        # Typical temperatures for Mediterranean climate (Tunis, etc.)
        if month in [12, 1, 2]:  # Winter
            temp = 12.0
            description = "partly cloudy"
        elif month in [3, 4, 5]:  # Spring
            temp = 18.0
            description = "clear sky"
        elif month in [6, 7, 8]:  # Summer
            temp = 30.0
            description = "sunny"
        else:  # Fall (9, 10, 11)
            temp = 22.0
            description = "partly cloudy"
        
        return {
            "weather": [{"description": description}],
            "main": {"temp": temp, "humidity": 65},
            "wind": {"speed": 3.5}
        }

import httpx

from app.core.config import get_settings


class WeatherService:
    """Thin client for OpenWeather, used by the Context Agent."""

    BASE_URL = "https://api.openweathermap.org/data/2.5/weather"

    def __init__(self) -> None:
        self.settings = get_settings()

    def get_current_weather(self, city: str) -> dict | None:
        if not self.settings.openweather_api_key:
            return None
        response = httpx.get(
            self.BASE_URL,
            params={"q": city, "appid": self.settings.openweather_api_key, "units": "metric"},
            timeout=5.0,
        )
        response.raise_for_status()
        return response.json()

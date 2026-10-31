"""Public weather endpoint — no auth required (just city name)."""
from fastapi import APIRouter
from pydantic import BaseModel

from app.services.weather import WeatherService

router = APIRouter(prefix="/weather", tags=["weather"])
_service = WeatherService()


class WeatherResponse(BaseModel):
    city: str
    temp: float
    description: str
    icon: str


def _icon(description: str, temp: float) -> str:
    desc = description.lower()
    if "rain" in desc or "drizzle" in desc or "shower" in desc:
        return "🌧️"
    if "thunder" in desc or "storm" in desc:
        return "⛈️"
    if "snow" in desc:
        return "❄️"
    if "fog" in desc or "mist" in desc or "haze" in desc:
        return "🌫️"
    if "overcast" in desc:
        return "☁️"
    if "cloud" in desc or "partly" in desc or "scattered" in desc or "broken" in desc or "few" in desc:
        return "⛅"
    if temp >= 28:
        return "☀️"
    return "🌤️"


@router.get("/{city}", response_model=WeatherResponse)
def get_weather(city: str) -> WeatherResponse:
    data = _service.get_current_weather(city)
    if data is None:
        # Fallback: return generic
        return WeatherResponse(city=city, temp=22.0, description="ciel dégagé", icon="🌤️")
    temp = round(data["main"]["temp"])
    description = data["weather"][0]["description"]
    return WeatherResponse(city=city, temp=temp, description=description, icon=_icon(description, temp))

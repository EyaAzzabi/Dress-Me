from dotenv import load_dotenv; load_dotenv()
import os, httpx

key = os.getenv("OPENWEATHER_API_KEY")
cities = {
    "Tunis":  (36.8190, 10.1658),
    "Sousse": (35.8333, 10.6333),
    "Sfax":   (34.7406, 10.7603),
    "Djerba": (33.8075, 10.8451),
}
for city, (lat, lon) in cities.items():
    r = httpx.get(
        "https://api.openweathermap.org/data/2.5/weather",
        params={"lat": lat, "lon": lon, "appid": key, "units": "metric"}
    )
    d = r.json()
    print(f"{city}: {d['main']['temp']}°C — {d['weather'][0]['description']}")

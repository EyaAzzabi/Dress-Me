from app.agents.context_agent import ContextAgent


def test_explicit_weather_is_never_overridden(monkeypatch):
    called = False

    def fail_if_called(self, city):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "app.agents.context_agent.WeatherService.get_current_weather", fail_if_called
    )

    result = ContextAgent().run(occasion="wedding", weather="sunny", city="Tunis")

    assert result["weather"] == "sunny"
    assert not called


def test_no_city_leaves_weather_none():
    result = ContextAgent().run(occasion="wedding")

    assert result == {"occasion": "wedding", "weather": None, "season": None}


def test_city_without_api_key_leaves_weather_none(monkeypatch):
    # WeatherService itself returns None with no OPENWEATHER_API_KEY configured —
    # ContextAgent must not crash on that, just pass it through.
    monkeypatch.setattr(
        "app.agents.context_agent.WeatherService.get_current_weather", lambda self, city: None
    )

    result = ContextAgent().run(city="Tunis")

    assert result["weather"] is None


def test_city_with_weather_data_fills_in_a_readable_string(monkeypatch):
    fake_data = {"weather": [{"description": "clear sky"}], "main": {"temp": 21.4}}
    monkeypatch.setattr(
        "app.agents.context_agent.WeatherService.get_current_weather",
        lambda self, city: fake_data,
    )

    result = ContextAgent().run(city="Tunis")

    assert result["weather"] == "clear sky, 21°C"

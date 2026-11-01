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

    # Legacy keys preserved (review-F6) — relaxed from exact-equality to subset
    # assertions because the enriched run now adds occasion_category/formality/
    # dress_code/temperature/weather_band on top.
    assert result["occasion"] == "wedding"
    assert result["weather"] is None
    assert result["season"] is None
    # New keys from the axe-3 enrichment: "wedding" parses to mariage via the rules
    # (LLM off by the conftest), temperature/season unknown so weather_band is None.
    assert result["occasion_category"] == "mariage"
    assert result["formality"] == 5
    assert result["dress_code"] == "tenue de cérémonie"
    assert result["temperature"] is None
    assert result["weather_band"] is None


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


# --- axe-3 enrichment: occasion parsing + temperature/weather_band -------------


def test_free_text_occasion_is_parsed_to_a_category_via_rules(monkeypatch):
    # LLM off by the conftest -> parse_occasion returns None -> ContextAgent falls
    # back to the deterministic occasions.parse_occasion_rules.
    result = ContextAgent().run(occasion="je vais a un mariage ce soir")

    assert result["occasion_category"] == "mariage"
    assert result["formality"] == 5
    assert result["dress_code"] == "tenue de cérémonie"
    # The raw occasion text is preserved as-is on the legacy key.
    assert result["occasion"] == "je vais a un mariage ce soir"


def test_free_text_dinner_request_is_parsed_as_evening():
    result = ContextAgent().run(occasion="Je vais dîner au restaurant ce soir")

    assert result["occasion_category"] == "soiree"
    assert result["formality"] == 3


def test_temperature_and_weather_band_are_present_when_lookup_succeeds(monkeypatch):
    fake_data = {"weather": [{"description": "clear sky"}], "main": {"temp": 28.0}}
    monkeypatch.setattr(
        "app.agents.context_agent.WeatherService.get_current_weather",
        lambda self, city: fake_data,
    )

    result = ContextAgent().run(city="Tunis", occasion="plage")

    assert result["temperature"] == 28.0
    # 28°C >= 24 -> "chaud" (coherent with seasons.HOT_FROM_C).
    assert result["weather_band"] == "chaud"
    # No explicit season -> inferred from the looked-up temperature (>=24 -> ete).
    assert result["season"] == "ete"


def test_parse_occasion_uses_the_injected_llm_agent_when_it_returns_a_parse(monkeypatch):
    # An injected LLMAgent whose parse_occasion returns a parse is preferred over the
    # deterministic rules — this is the path FEAT-005 will exercise via a real provider.
    class _LLM:
        def parse_occasion(self, raw_occasion, context_hints):
            return {
                "occasion_category": "ceremonie",
                "formality": 5,
                "dress_code": "tenue de cérémonie",
            }

    result = ContextAgent(llm_agent=_LLM()).run(occasion="communion")

    assert result["occasion_category"] == "ceremonie"
    assert result["formality"] == 5

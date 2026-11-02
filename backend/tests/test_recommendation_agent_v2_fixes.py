from datetime import date
from types import SimpleNamespace

from app.agents.recommendation_agent_v2 import RecommendationAgentV2
from app.ml.constraint_parser import ConstraintParser
from app.ml import compatibility_model


def clothing_item(item_id, category, *, color="noir", style="casual", season="all", material="coton"):
    return SimpleNamespace(
        id=item_id,
        category=category,
        colors=[color],
        style=style,
        season=season,
        material=material,
        name=item_id,
    )


def test_composer_accepts_english_and_french_category_aliases():
    agent = RecommendationAgentV2()
    items = [
        clothing_item("top", "top"),
        clothing_item("bottom", "bas"),
        clothing_item("shoes", "chaussures"),
    ]

    outfits = agent._compose_outfit_candidates(items, {}, top_k=1)

    assert len(outfits) == 1
    assert {item.id for item in outfits[0]} == {"top", "bottom", "shoes"}


def test_composer_requires_a_dress_or_a_top_and_bottom():
    agent = RecommendationAgentV2()
    incomplete = [
        clothing_item("top", "haut"),
        clothing_item("shoes", "shoes"),
    ]
    dress = [clothing_item("dress", "robe")]

    assert agent._compose_outfit_candidates(incomplete, {}, top_k=3) == []
    assert agent._compose_outfit_candidates(dress, {}, top_k=1)[0][0].id == "dress"


def test_composer_returns_distinct_ranked_combinations():
    agent = RecommendationAgentV2()
    items = [
        clothing_item("top-1", "top"),
        clothing_item("top-2", "top"),
        clothing_item("bottom-1", "bottom"),
        clothing_item("bottom-2", "bottom"),
    ]

    outfits = agent._compose_outfit_candidates(items, {}, top_k=3)

    assert len(outfits) == 3
    assert len({frozenset(item.id for item in outfit) for outfit in outfits}) == 3
    assert all(
        {agent._canonical_category(item.category) for item in outfit} >= {"top", "bottom"}
        for outfit in outfits
    )


def test_compatibility_uses_trained_pair_model_when_embeddings_exist(monkeypatch):
    agent = RecommendationAgentV2()
    outfit = [
        clothing_item("top", "top"),
        clothing_item("bottom", "bottom"),
    ]
    monkeypatch.setattr(compatibility_model, "pair_compatibility", lambda *args, **kwargs: 0.91)

    score = agent._score_outfit_compatibility(
        outfit,
        compatibility_embeddings={"top": [1.0, 0.0], "bottom": [0.0, 1.0]},
    )

    assert score == 0.91


def test_temperature_zero_is_preserved_and_extreme_mismatch_is_not_restored():
    agent = RecommendationAgentV2()
    linen = clothing_item("linen", "top", material="lin")

    filtered = agent._filter_candidates([linen], season=None, weather_data={"temperature": 0})

    assert filtered == []
    assert agent._fetch_weather(city=None, temperature=0, weather=None)["temperature"] == 0


def test_personalization_uses_favorite_styles_recent_wear_and_feedback():
    agent = RecommendationAgentV2()
    items = [
        clothing_item("fav", "top", style="formal"),
        clothing_item("recent", "bottom"),
        clothing_item("liked", "shoes"),
    ]

    adjusted = agent._apply_personalization(
        {item.id: 0.5 for item in items},
        items,
        {
            "favorite_styles": ["formal"],
            "usage": {"recent": {"last_worn": date.today()}},
            "feedback_preferences": [{"item_ids": ["liked"], "rating": "like"}],
        },
    )

    assert adjusted["fav"] > adjusted["recent"]
    assert adjusted["liked"] > 0.5


def test_free_text_color_constraint_boosts_matching_items(monkeypatch):
    agent = RecommendationAgentV2()
    items = [
        clothing_item("blue-top", "top", color="blue"),
        clothing_item("red-top", "top", color="red"),
        clothing_item("bottom", "bottom", color="black"),
    ]
    monkeypatch.setattr(agent, "_fetch_weather", lambda *args: {"temperature": 20})
    monkeypatch.setattr(agent, "_load_models", lambda user_id: {})
    monkeypatch.setattr(
        agent,
        "_score_items",
        lambda models, candidates, *args, **kwargs: {
            item.id: 0.5 for item in candidates
        },
    )

    result = agent.run(wardrobe_items=items, request_text="touche de bleu", top_k=1)

    assert result["outfits"][0]["item_ids"] == ["blue-top", "bottom"]


def test_agent_constraint_parsing_does_not_make_an_llm_request(monkeypatch):
    parser = ConstraintParser()

    def unexpected_llm_call(_):
        raise AssertionError("The deterministic recommendation parser must not call an LLM")

    monkeypatch.setattr(parser, "_parse_with_llm", unexpected_llm_call)

    constraints = parser.parse("touche de bleu", use_llm=False)

    assert constraints["colors"] == ["bleu"]


def test_fallback_does_not_repeat_the_same_outfit():
    agent = RecommendationAgentV2()
    items = [
        clothing_item("top-1", "top"),
        clothing_item("top-2", "top"),
        clothing_item("bottom-1", "bottom"),
        clothing_item("bottom-2", "bottom"),
    ]

    result = agent._fallback_outfit(items, top_k=3)

    outfit_sets = [frozenset(outfit["item_ids"]) for outfit in result["outfits"]]
    assert len(outfit_sets) == len(set(outfit_sets))
    assert all(len(outfit) == 2 for outfit in outfit_sets)

"""Tests for the deterministic occasion vocabulary + weather bands (FEAT-001 socle).

Covers: the injective keyword -> category mapping (FR/EN table from the design), the
``casual_quotidien`` fallback for ``None`` and no-match text, the absence of the
"mer"-in-"commercial" false positive (review-F3), and the ``weather_band`` boundaries
(14/24) coherent with the season helpers.
"""

import pytest

from app.services.occasions import (
    OCCASION_CATEGORIES,
    WEATHER_BANDS,
    parse_occasion_rules,
    weather_band,
)


# --- vocabulary shape ---------------------------------------------------------


def test_occasion_categories_is_the_eight_category_vocabulary():
    assert OCCASION_CATEGORIES == [
        "mariage",
        "soiree",
        "travail",
        "casual_quotidien",
        "sport",
        "plage",
        "voyage",
        "ceremonie",
    ]


def test_weather_bands_has_three_bands():
    assert set(WEATHER_BANDS) == {"froid", "modere", "chaud"}


# --- parse_occasion_rules: FR/EN keyword -> category ---------------------------


@pytest.mark.parametrize(
    "text, expected_category, expected_formality, expected_dress_code",
    [
        # mariage
        ("je vais a un mariage", "mariage", 5, "tenue de cérémonie"),
        ("a summer wedding", "mariage", 5, "tenue de cérémonie"),
        # ceremonie
        ("funeral this afternoon", "ceremonie", 5, "tenue de cérémonie"),
        ("baptême de mon neveu", "ceremonie", 5, "tenue de cérémonie"),
        ("communion de la petite", "ceremonie", 5, "tenue de cérémonie"),
        ("church on sunday", "ceremonie", 5, "tenue de cérémonie"),
        # soiree
        ("soirée entre amis", "soiree", 3, "chic"),
        ("birthday party tonight", "soiree", 3, "chic"),
        ("on sort en boîte", "soiree", 3, "chic"),
        ("on va en club", "soiree", 3, "chic"),
        # travail
        ("j'ai un entretien demain", "travail", 4, "business casual"),
        ("meeting at the bureau", "travail", 4, "business casual"),
        ("job interview", "travail", 4, "business casual"),
        # sport
        ("session de sport", "sport", 1, "sportwear"),
        ("going to the gym", "sport", 1, "sportwear"),
        ("running in the park", "sport", 1, "sportwear"),
        # plage
        ("je vais a la mer", "plage", 1, "décontracté"),
        ("day at the beach", "plage", 1, "décontracté"),
        ("baignade cet après-midi", "plage", 1, "décontracté"),
        # voyage
        ("vacances a l'aéroport", "voyage", 2, "confortable"),
        ("business trip", "voyage", 2, "confortable"),
        ("avion pour paris", "voyage", 2, "confortable"),
    ],
)
def test_parse_occasion_rules_maps_keywords_to_categories(
    text, expected_category, expected_formality, expected_dress_code
):
    result = parse_occasion_rules(text)
    assert result == {
        "occasion_category": expected_category,
        "formality": expected_formality,
        "dress_code": expected_dress_code,
    }
    assert result["occasion_category"] in OCCASION_CATEGORIES


def test_parse_occasion_rules_always_returns_a_vocabulary_category():
    # Whatever the input, the category is always one of the eight (never None and
    # never out-of-vocabulary) and formality stays within 1..5.
    for text in [None, "", "random words with no keyword"]:
        result = parse_occasion_rules(text)
        assert result["occasion_category"] in OCCASION_CATEGORIES
        assert isinstance(result["formality"], int)
        assert 1 <= result["formality"] <= 5


# --- fallback ------------------------------------------------------------------


def test_parse_occasion_rules_falls_back_to_casual_quotidien_for_none():
    assert parse_occasion_rules(None) == {
        "occasion_category": "casual_quotidien",
        "formality": 2,
        "dress_code": None,
    }


def test_parse_occasion_rules_falls_back_to_casual_quotidien_for_no_match():
    result = parse_occasion_rules("just a quiet day at home")
    assert result == {
        "occasion_category": "casual_quotidien",
        "formality": 2,
        "dress_code": None,
    }


# --- review-F3: no "mer"-in-"commercial" false positive ------------------------


def test_commercial_is_not_false_matched_to_plage():
    # review-F3: token (whole-word) matching must not let "mer" match inside
    # "commercial" — shopping at a mall is casual, not the beach.
    result = parse_occasion_rules("je vais au centre commercial")
    assert result["occasion_category"] == "casual_quotidien"
    assert result["occasion_category"] != "plage"

    assert parse_occasion_rules("centre commercial")["occasion_category"] == "casual_quotidien"
    # ... while a real beach mention still matches plage.
    assert parse_occasion_rules("je vais a la mer")["occasion_category"] == "plage"


# --- weather_band boundaries (coherent with seasons 14/24) ---------------------


@pytest.mark.parametrize(
    "temperature, expected",
    [
        (-5.0, "froid"),
        (13.0, "froid"),
        (14.0, "modere"),
        (23.9, "modere"),
        (24.0, "chaud"),
        (30.0, "chaud"),
    ],
)
def test_weather_band_boundaries(temperature, expected):
    assert weather_band(temperature) == expected


def test_weather_band_none_returns_none():
    assert weather_band(None) is None

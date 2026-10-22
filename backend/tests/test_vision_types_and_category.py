"""Offline tests for the Vision Agent's two-stage category and its type-based season/style.

No FashionCLIP and no real classifier: the pieces are stubbed so these run in milliseconds.
The real end-to-end quality is measured by ml/notebooks/13_vision_agent_evaluation.py.
"""

import json

import numpy as np
import pytest

from app.ml import garment_types, vision_model
from app.schemas.clothing_item import Season

EMBEDDING = np.ones(512) / np.sqrt(512)


# ---------------------------------------------------------------- the shipped priors artifact
def test_priors_artifact_is_well_formed():
    priors = json.loads(garment_types.PRIORS_PATH.read_text(encoding="utf-8"))

    assert len(priors["types"]) >= 30
    for row in priors["types"]:
        assert row["prompt"]
        assert sum(row["season"]) == pytest.approx(1.0, abs=2e-3)
        assert sum(row["usage"]) == pytest.approx(1.0, abs=2e-3)
        assert len(row["season"]) == len(priors["seasons"])
        assert len(row["usage"]) == len(priors["usages"])


def test_prior_seasons_are_valid_wardrobe_seasons():
    priors = json.loads(garment_types.PRIORS_PATH.read_text(encoding="utf-8"))
    allowed = set(Season.__args__)

    assert set(priors["seasons"]) <= allowed


def test_a_sweater_leans_away_from_summer_and_shorts_do_not(monkeypatch):
    priors = garment_types._priors()
    names = [t["article_type"] for t in priors["types"]]

    def one_hot(name):
        return lambda embedding: np.eye(len(names))[names.index(name)]

    monkeypatch.setattr(garment_types, "type_posterior", one_hot("Sweaters"))
    sweater = garment_types.season_posterior(EMBEDDING)
    monkeypatch.setattr(garment_types, "type_posterior", one_hot("Shorts"))
    shorts = garment_types.season_posterior(EMBEDDING)

    assert sweater["ete"] < 0.15 < shorts["ete"]
    assert sum(sweater.values()) == pytest.approx(1.0, abs=2e-3)


# ---------------------------------------------------------------- season / style thresholds
def test_season_is_only_suggested_when_confident(monkeypatch):
    monkeypatch.setattr(garment_types, "available", lambda: True)
    monkeypatch.setattr(garment_types, "season_posterior", lambda e: {"ete": 0.2, "hiver": 0.1, "mi_saison": 0.7})
    assert vision_model.predict_season(EMBEDDING)[0] == "mi_saison"

    monkeypatch.setattr(garment_types, "season_posterior", lambda e: {"ete": 0.45, "hiver": 0.1, "mi_saison": 0.45})
    label, confidence = vision_model.predict_season(EMBEDDING)
    assert label is None and confidence == pytest.approx(0.45)


def test_style_comes_from_the_four_learnable_styles(monkeypatch):
    monkeypatch.setattr(garment_types, "available", lambda: True)
    monkeypatch.setattr(garment_types, "usage_posterior", lambda e: {"Casual": 0.1, "Sports": 0.8, "Ethnic": 0.05, "Formal": 0.05})
    assert vision_model.predict_style(EMBEDDING)[0] == "Sports"

    monkeypatch.setattr(garment_types, "usage_posterior", lambda e: {"Casual": 0.4, "Sports": 0.3, "Ethnic": 0.2, "Formal": 0.1})
    assert vision_model.predict_style(EMBEDDING)[0] is None


def test_without_the_priors_artifact_season_and_style_fall_back_to_zero_shot(monkeypatch):
    monkeypatch.setattr(garment_types, "available", lambda: False)
    monkeypatch.setattr(
        garment_types, "season_posterior", lambda e: pytest.fail("priors must not be used when unavailable")
    )
    calls = []

    def fake_zero_shot(embedding, prompts, template):
        calls.append(tuple(prompts))
        return {name: (0.9 if i == 0 else 0.1 / (len(prompts) - 1)) for i, name in enumerate(prompts)}

    monkeypatch.setattr(vision_model, "_zero_shot_probs", fake_zero_shot)

    assert vision_model.predict_season(EMBEDDING)[0] == "ete"
    assert vision_model.predict_style(EMBEDDING)[0] == "Casual"
    assert len(calls) == 2


# ---------------------------------------------------------------- two-stage category
class _Probe:
    """Stands in for the 8-class probe (the 'is it clothing' gate)."""

    def __init__(self, label, confidence=0.9):
        self.label, self.confidence = label, confidence
        self.classes_ = np.array(["haut", "hors_perimetre"])

    def predict(self, x):
        return np.array([self.label])

    def predict_proba(self, x):
        return np.array([[self.confidence, 1 - self.confidence]])


class _Head:
    classes_ = np.array(["bas", "haut", "robe"])

    def __init__(self):
        self.asked = 0

    def predict_proba(self, x):
        self.asked += 1
        return np.array([[0.1, 0.2, 0.7]])


def test_non_clothing_never_reaches_the_garment_head(monkeypatch):
    head = _Head()
    monkeypatch.setattr(vision_model, "_load_category_classifier", lambda: _Probe("hors_perimetre", 0.8))
    monkeypatch.setattr(vision_model, "_load_garment_classifier", lambda: head)

    assert vision_model.predict_category(EMBEDDING) == ("hors_perimetre", 0.8)
    assert head.asked == 0


def test_garment_category_and_confidence_come_from_the_head(monkeypatch):
    monkeypatch.setattr(vision_model, "_load_category_classifier", lambda: _Probe("haut", 0.95))
    monkeypatch.setattr(vision_model, "_load_garment_classifier", lambda: _Head())

    label, confidence = vision_model.predict_category(EMBEDDING)

    assert label == "robe" and confidence == pytest.approx(0.7)


def test_category_falls_back_to_the_probe_without_the_head_artifact(monkeypatch):
    monkeypatch.setattr(vision_model, "_load_category_classifier", lambda: _Probe("haut", 0.66))
    monkeypatch.setattr(vision_model, "_load_garment_classifier", lambda: None)

    label, confidence = vision_model.predict_category(EMBEDDING)

    assert label == "haut" and confidence == pytest.approx(0.66)


def test_low_head_confidence_marks_the_category_uncertain(monkeypatch):
    monkeypatch.setattr(vision_model, "embed_image_bytes", lambda b: EMBEDDING)
    monkeypatch.setattr(vision_model, "predict_category", lambda e: ("robe", 0.55))
    monkeypatch.setattr(vision_model, "predict_colors", lambda e: (["noir"], 0.9))
    monkeypatch.setattr(vision_model, "predict_pattern", lambda e: ("uni", 0.8))
    monkeypatch.setattr(vision_model, "predict_style", lambda e: (None, 0.4))
    monkeypatch.setattr(vision_model, "predict_season", lambda e: (None, 0.4))

    result = vision_model.analyze_image(b"ignored")

    assert result["category_uncertain"] is True  # 0.55 < CATEGORY_MIN_CONFIDENCE (0.60)
    assert result["style"] is None and result["season"] is None

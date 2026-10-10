import numpy as np
import pytest

from app.ml import vision_model


class _FakeClassifier:
    def predict(self, X):
        return np.array(["haut"] * len(X))


@pytest.fixture(autouse=True)
def fake_classifier(monkeypatch):
    monkeypatch.setattr(vision_model, "_load_category_classifier", lambda: _FakeClassifier())


def test_non_clothing_photo_is_out_of_scope_even_if_the_classifier_says_otherwise(monkeypatch):
    monkeypatch.setattr(vision_model, "clothing_probability", lambda e: np.array([0.05]))

    assert vision_model.predict_category(np.zeros(512)) == "hors_perimetre"


def test_clothing_photo_goes_through_to_the_classifier(monkeypatch):
    monkeypatch.setattr(vision_model, "clothing_probability", lambda e: np.array([0.9]))

    assert vision_model.predict_category(np.zeros(512)) == "haut"


def test_gate_threshold_is_inclusive_of_borderline_clothing(monkeypatch):
    monkeypatch.setattr(vision_model, "clothing_probability",
                        lambda e: np.array([vision_model.CLOTHING_GATE_THRESHOLD]))

    assert vision_model.predict_category(np.zeros(512)) == "haut"

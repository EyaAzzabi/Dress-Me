import numpy as np

from app.ml import clothing_gate


def test_non_clothing_photo_is_rejected(monkeypatch):
    monkeypatch.setattr(clothing_gate, "clothing_probability", lambda e: np.array([0.05]))

    assert clothing_gate.is_clothing(np.zeros(512)) is False


def test_clothing_photo_goes_through(monkeypatch):
    monkeypatch.setattr(clothing_gate, "clothing_probability", lambda e: np.array([0.9]))

    assert clothing_gate.is_clothing(np.zeros(512)) is True


def test_gate_threshold_is_inclusive_of_borderline_clothing(monkeypatch):
    monkeypatch.setattr(clothing_gate, "clothing_probability",
                        lambda e: np.array([clothing_gate.CLOTHING_GATE_THRESHOLD]))

    assert clothing_gate.is_clothing(np.zeros(512)) is True

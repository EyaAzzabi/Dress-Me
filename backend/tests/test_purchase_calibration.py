import pytest

from app.ml import purchase_calibration


@pytest.fixture
def fake_calibration(monkeypatch):
    levels = list(range(0, 101, 25))
    monkeypatch.setattr(purchase_calibration, "_load", lambda: {
        "quantile_levels": levels,
        "base_compatibility": [0.40, 0.50, 0.54, 0.58, 0.70],
    })


def test_median_raw_score_maps_to_half(fake_calibration):
    assert purchase_calibration.percentile("base_compatibility", 0.54) == pytest.approx(0.5)


def test_scores_between_quantiles_are_interpolated(fake_calibration):
    assert purchase_calibration.percentile("base_compatibility", 0.56) == pytest.approx(0.625)


def test_scores_outside_the_reference_range_are_clipped(fake_calibration):
    assert purchase_calibration.percentile("base_compatibility", 0.1) == 0.0
    assert purchase_calibration.percentile("base_compatibility", 0.99) == 1.0


def test_missing_artifact_falls_back_to_a_linear_ramp(monkeypatch):
    monkeypatch.setattr(purchase_calibration, "_load", lambda: None)

    low, high = purchase_calibration._FALLBACK_RANGES["style_fit"]
    assert purchase_calibration.percentile("style_fit", (low + high) / 2) == pytest.approx(0.5)


def test_bundled_artifact_is_monotonic():
    calibration = purchase_calibration._load()
    if calibration is None:
        pytest.skip("purchase_calibration.json not built")
    for kind in ("base_compatibility", "optional_compatibility", "style_fit"):
        quantiles = calibration[kind]
        assert quantiles == sorted(quantiles)

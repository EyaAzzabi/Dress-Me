import numpy as np
import pytest

from app.ml import compatibility_model


def _unit(vector: np.ndarray) -> np.ndarray:
    return vector / np.linalg.norm(vector)


@pytest.fixture(autouse=True)
def clear_cache():
    compatibility_model._load_model.cache_clear()
    yield
    compatibility_model._load_model.cache_clear()


def test_falls_back_to_cosine_similarity_when_artifact_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(compatibility_model, "MODEL_PATH", tmp_path / "missing.joblib")
    rng = np.random.default_rng(0)
    a, b = _unit(rng.normal(size=512)), _unit(rng.normal(size=512))

    score = compatibility_model.pair_compatibility(a, b)

    assert score == pytest.approx(float(a @ b))


def test_real_artifact_returns_a_probability():
    assert compatibility_model.MODEL_PATH.exists(), (
        "artifacts/compatibility_model.joblib missing — copy it from "
        "ml/data/processed/compatibility_model.joblib (see ml/notebooks/09_compatibility_model.py)"
    )
    rng = np.random.default_rng(0)
    a, b = _unit(rng.normal(size=512)), _unit(rng.normal(size=512))

    score = compatibility_model.pair_compatibility(a, b)

    assert 0.0 <= score <= 1.0


def test_identical_vectors_score_higher_than_unrelated_ones():
    rng = np.random.default_rng(1)
    a = _unit(rng.normal(size=512))
    b = _unit(rng.normal(size=512))

    same = compatibility_model.pair_compatibility(a, a)
    different = compatibility_model.pair_compatibility(a, b)

    assert same > different

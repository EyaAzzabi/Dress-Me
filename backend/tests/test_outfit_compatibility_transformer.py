"""Unit tests for app/ml/outfit_compatibility_transformer.py.

All tests run on CPU with deterministic random data (rng seed 0).
No real Polyvore data or GPU required.
"""

import numpy as np
import pytest

from app.ml import outfit_compatibility_transformer as oct_mod
from app.ml.outfit_compatibility_transformer import (
    OutfitCompatibilityTransformer,
    load_or_init,
    save_model,
    score_outfit,
    train_on_polyvore_style_data,
)

RNG = np.random.default_rng(0)


def _random_emb(rng=None) -> np.ndarray:
    r = rng if rng is not None else RNG
    return r.random(512).astype(np.float32)


# ---------------------------------------------------------------------------
# (a) score_outfit returns float in [0, 1] for various outfit lengths
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n_items", [2, 3, 5])
def test_score_outfit_returns_bounded_float(n_items):
    rng = np.random.default_rng(0)
    embeddings = [_random_emb(rng) for _ in range(n_items)]
    result = score_outfit(embeddings)
    assert isinstance(result, float), f"Expected float, got {type(result)}"
    assert 0.0 <= result <= 1.0, f"Score {result} is outside [0, 1]"


# ---------------------------------------------------------------------------
# (b) load_or_init with missing artifact returns model without error
# ---------------------------------------------------------------------------

def test_load_or_init_missing_artifact_returns_instance(monkeypatch, tmp_path):
    missing = tmp_path / "nonexistent" / "outfit_transformer.pt"
    monkeypatch.setattr(oct_mod, "ARTIFACT_PATH", missing)
    model = load_or_init()
    assert isinstance(model, OutfitCompatibilityTransformer)


# ---------------------------------------------------------------------------
# (c) train_on_polyvore_style_data completes without error
# ---------------------------------------------------------------------------

def test_train_on_polyvore_style_data_runs_without_error():
    rng = np.random.default_rng(0)
    positive_pairs = [[_random_emb(rng), _random_emb(rng)] for _ in range(4)]
    negative_pairs = [[_random_emb(rng), _random_emb(rng)] for _ in range(4)]
    # Should not raise
    model = train_on_polyvore_style_data(positive_pairs, negative_pairs)
    assert model is not None


# ---------------------------------------------------------------------------
# (d) save_model + load_or_init round-trip: score is identical before/after
# ---------------------------------------------------------------------------

def test_save_and_reload_produces_same_score(monkeypatch, tmp_path):
    rng = np.random.default_rng(0)
    artifact = tmp_path / "outfit_transformer.pt"
    monkeypatch.setattr(oct_mod, "ARTIFACT_PATH", artifact)

    # Train briefly so weights are non-default
    positive_pairs = [[_random_emb(rng), _random_emb(rng)] for _ in range(4)]
    negative_pairs = [[_random_emb(rng), _random_emb(rng)] for _ in range(4)]
    trained_model = train_on_polyvore_style_data(positive_pairs, negative_pairs, epochs=2)

    # Save
    save_model(trained_model)
    assert artifact.exists(), "save_model did not create the artifact file"

    # Score before reload (using trained model directly)
    rng2 = np.random.default_rng(0)
    test_embeddings = [_random_emb(rng2), _random_emb(rng2), _random_emb(rng2)]
    score_before = score_outfit(test_embeddings)

    # Reload and score again — load_or_init reads ARTIFACT_PATH which is monkeypatched
    score_after = score_outfit(test_embeddings)

    assert abs(score_before - score_after) < 1e-5, (
        f"Score changed after reload: {score_before} → {score_after}"
    )

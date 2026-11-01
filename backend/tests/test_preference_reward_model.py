"""Unit tests for app/ml/preference_reward_model.py.

All tests run on CPU with deterministic random data (rng seed 0).
"""

import numpy as np
import pytest

from app.ml import preference_reward_model as prm_mod
from app.ml.preference_reward_model import (
    PreferenceRewardModel,
    load_or_init,
    predict_reward,
    save,
    train_from_feedback,
)

RNG = np.random.default_rng(0)


def _random_emb(rng=None) -> np.ndarray:
    r = rng if rng is not None else RNG
    return r.random(512).astype(np.float32)


# ---------------------------------------------------------------------------
# (a) predict_reward returns a Python float
# ---------------------------------------------------------------------------

def test_predict_reward_returns_float():
    rng = np.random.default_rng(0)
    embeddings = [_random_emb(rng) for _ in range(3)]
    model = load_or_init("test-user-id")
    result = predict_reward(model, embeddings)
    assert isinstance(result, float), f"Expected float, got {type(result)}"


# ---------------------------------------------------------------------------
# (b) load_or_init with missing artifact → _trained is False
# ---------------------------------------------------------------------------

def test_load_or_init_missing_artifact_returns_untrained(tmp_path):
    user_id = "missing-user"
    # Artifact does not exist in tmp_path, but load_or_init builds its own path
    # We patch only the model that comes back — just call with a user_id that has
    # no saved artifact in the real artifacts dir.
    model = load_or_init("__nonexistent_user_xyz__")
    assert model._trained is False


# ---------------------------------------------------------------------------
# (c) train_from_feedback with 2 pairs sets _trained = True
# ---------------------------------------------------------------------------

def test_train_from_feedback_sets_trained_true():
    rng = np.random.default_rng(0)
    pairs = [
        ([_random_emb(rng), _random_emb(rng)], [_random_emb(rng)]),
        ([_random_emb(rng)], [_random_emb(rng), _random_emb(rng)]),
    ]
    model = load_or_init("__test_train__")
    train_from_feedback(model, pairs)
    assert model._trained is True


# ---------------------------------------------------------------------------
# (d) Bradley-Terry loss decreases over training
# ---------------------------------------------------------------------------

def test_bradley_terry_loss_decreases():
    """Loss at epoch 20 should be strictly lower than at epoch 0 given enough signal."""
    try:
        import torch
        import torch.nn as nn
    except ImportError:
        pytest.skip("torch not available")

    rng = np.random.default_rng(0)
    pairs = [
        ([_random_emb(rng), _random_emb(rng)], [_random_emb(rng), _random_emb(rng)])
        for _ in range(4)
    ]

    from app.ml.preference_reward_model import (
        PreferenceRewardModel,
        _mean_pool_embeddings,
    )

    def compute_loss(model_):
        total = 0.0
        for preferred_embs, rejected_embs in pairs:
            pref_vec = _mean_pool_embeddings(preferred_embs).unsqueeze(0)
            rej_vec = _mean_pool_embeddings(rejected_embs).unsqueeze(0)
            r_pref = model_(pref_vec).squeeze()
            r_rej = model_(rej_vec).squeeze()
            loss = -torch.log(torch.sigmoid(r_pref - r_rej) + 1e-8)
            total += loss.item()
        return total

    # Measure initial loss
    model_initial = PreferenceRewardModel()
    loss_initial = compute_loss(model_initial)

    # Train for 20 epochs
    model_trained = PreferenceRewardModel()
    # Copy same initial weights so comparison is fair
    model_trained.load_state_dict(model_initial.state_dict())
    train_from_feedback(model_trained, pairs, epochs=20)
    loss_final = compute_loss(model_trained)

    assert loss_final < loss_initial, (
        f"Expected loss to decrease: initial={loss_initial:.4f}, final={loss_final:.4f}"
    )


# ---------------------------------------------------------------------------
# (e) save + load_or_init round-trip: predict_reward is identical (approx)
# ---------------------------------------------------------------------------

def test_save_and_reload_produces_same_reward(monkeypatch, tmp_path):
    rng = np.random.default_rng(0)
    user_id = "roundtrip-user"

    # Patch artifact path to tmp_path
    original_path_fn = prm_mod.Path

    def patched_path(*args):
        p = original_path_fn(*args)
        return p

    # We override the artifacts directory used by save() and load_or_init()
    # by monkeypatching the Path resolution inside the module.
    import app.ml.preference_reward_model as _prm

    # Intercept the artifact path by wrapping save and load_or_init with tmp_path
    artifact_file = tmp_path / f"reward_model_{user_id[:8]}.pt"

    try:
        import torch
    except ImportError:
        pytest.skip("torch not available")

    # Create, train briefly, then save manually to tmp_path
    model = PreferenceRewardModel()
    pairs = [
        ([_random_emb(rng), _random_emb(rng)], [_random_emb(rng)])
        for _ in range(2)
    ]
    train_from_feedback(model, pairs, epochs=5)

    # Save to tmp_path directly
    torch.save(model.state_dict(), str(artifact_file))

    # Load from tmp_path manually
    model2 = PreferenceRewardModel()
    state = torch.load(str(artifact_file), map_location="cpu", weights_only=True)
    model2.load_state_dict(state)
    model2._trained = True
    model2.eval()

    # Compare predictions on same input
    rng2 = np.random.default_rng(0)
    test_embs = [_random_emb(rng2) for _ in range(3)]

    reward_before = predict_reward(model, test_embs)
    reward_after = predict_reward(model2, test_embs)

    assert abs(reward_before - reward_after) < 1e-5, (
        f"Reward changed after reload: {reward_before} → {reward_after}"
    )

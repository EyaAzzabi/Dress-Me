"""Tests for the contextual outfit ranker (FEAT-002 — axe 1, fine-tuning du classement).

Covers:
- ``context_vector`` indexing (specific ``occasion|season|band`` key) and the three
  fallback branches (band-agnostic ``occasion|season|_any``; ``season=None`` -> zeros;
  absent ``.npz`` -> zeros), review-F9/F10.
- ``score_outfit`` with no artifact (monkeypatched ``MODEL_PATH`` to a missing file +
  ``_load_model.cache_clear``) reproduces the **exact** existing heuristic
  (``min(1, visual + style_bonus)`` then ``max(0, . - penalty*recent)``), review-F12.
- ``score_outfit`` with a fake persisted classifier reproduces the artifact-present
  formula (``learned + additive layer - freshness penalty``, clamped to ``[0, 1]``).
- ``ranking_enabled=False`` yields the same score as an absent artifact (invariant
  ``score in [0, 1]``).
- absent ``context_vectors.npz`` -> ``context_vector`` returns zeros -> ``context_fit``
  degrades to 0 without crashing.
- monotonicity: higher ``visual_coherence`` -> higher score at constant context.

All tests pass ``ranking_enabled=True`` directly to ``score_outfit`` (no env override
needed for unit tests — FEAT-002). Caches are cleared around each test so monkeypatched
paths take effect.
"""

import numpy as np
import pytest

from app.ml import ranking_model


# --- helpers -------------------------------------------------------------------

def _unit(v: np.ndarray) -> np.ndarray:
    return v / np.linalg.norm(v)


def _write_vectors_npz(path, mapping: dict[str, np.ndarray]) -> None:
    """Write a ``{keys, vectors}`` .npz the same way the training notebook does."""
    keys = list(mapping.keys())
    vectors = np.stack([mapping[k] for k in keys]).astype(np.float32)
    np.savez_compressed(path, keys=np.array(keys), vectors=vectors)


class _FakeRanker:
    """Minimal picklable stand-in for the trained LogisticRegression ranker.

    ``predict_proba`` returns a fixed class-1 probability for every input row — only
    ``predict_proba`` is exercised by ``score_outfit``'s artifact path. Defined at
    module level so joblib can pickle/unpickle it by qualified name within this test
    module's process.
    """

    def __init__(self, p1: float = 0.5):
        self.p1 = float(p1)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        n = X.shape[0]
        col0 = np.full(n, 1.0 - self.p1, dtype=np.float64)
        col1 = np.full(n, self.p1, dtype=np.float64)
        return np.stack([col0, col1], axis=1)


class _MonotonicRanker:
    """Fake ranker whose class-1 probability is a logistic function of the two
    features, so a higher ``visual_coherence`` (feature 0) yields a higher probability
    at constant ``context_fit`` (feature 1) — for the monotonicity test."""

    def __init__(self, w_visual=3.0, w_context=1.0, bias=-1.5):
        self.w = np.array([w_visual, w_context], dtype=np.float64)
        self.b = float(bias)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        z = X @ self.w + self.b
        p1 = 1.0 / (1.0 + np.exp(-z))
        return np.stack([1.0 - p1, p1], axis=1)


class _BrokenRanker:
    """Ranker whose predict_proba always raises — exercises score_outfit's non-fatal
    fallback (WARNING + heuristic) when the loaded model fails mid-prediction."""

    def predict_proba(self, X: np.ndarray) -> np.ndarray:  # noqa: ARG002
        raise RuntimeError("boom")


@pytest.fixture(autouse=True)
def _clear_ranking_caches():
    """The @lru_cache on _load_model/_load_vectors is module-level and persists across
    tests; clear it before and after each test so monkeypatched paths take effect."""
    ranking_model._load_model.cache_clear()
    ranking_model._load_vectors.cache_clear()
    yield
    ranking_model._load_model.cache_clear()
    ranking_model._load_vectors.cache_clear()


# --- exact heuristic fallback (no artifact) -----------------------------------


def test_score_outfit_no_artifact_uses_exact_heuristic(monkeypatch, tmp_path):
    # Even with ranking_enabled=True, a missing artifact falls back to the exact
    # existing heuristic — context features are NOT computed/applied.
    monkeypatch.setattr(ranking_model, "MODEL_PATH", tmp_path / "missing.joblib")
    ranking_model._load_model.cache_clear()

    visual = 0.7
    score = ranking_model.score_outfit(
        visual=visual, style_match=True, recent=2,
        # these contextual inputs must be IGNORED on the fallback path:
        context_fit=0.9, season_compat=0.9, history_fit=0.9,
        ranking_enabled=True,
    )
    expected = max(
        0.0,
        min(1.0, visual + ranking_model.STYLE_MATCH_BONUS)
        - ranking_model.RECENT_WEAR_PENALTY * 2,
    )
    assert score == pytest.approx(expected)


def test_score_outfit_no_artifact_ignores_context_features(monkeypatch, tmp_path):
    monkeypatch.setattr(ranking_model, "MODEL_PATH", tmp_path / "missing.joblib")
    ranking_model._load_model.cache_clear()

    base = ranking_model.score_outfit(visual=0.5, ranking_enabled=True)
    # passing contextual features must not change the fallback score
    with_ctx = ranking_model.score_outfit(
        visual=0.5, context_fit=0.8, season_compat=1.0,
        history_fit=1.0, style_match=True, recent=3, ranking_enabled=True,
    )
    expected_with_ctx = max(
        0.0,
        min(1.0, 0.5 + ranking_model.STYLE_MATCH_BONUS)
        - ranking_model.RECENT_WEAR_PENALTY * 3,
    )
    assert with_ctx == pytest.approx(expected_with_ctx)
    # without the style/recent deltas, context alone changes nothing:
    assert ranking_model.score_outfit(visual=0.5, context_fit=0.8, ranking_enabled=True) == pytest.approx(base)


# --- ranking_enabled=False equals an absent artifact ---------------------------


def test_ranking_disabled_equals_absent_artifact(monkeypatch, tmp_path):
    # Acceptance: score_outfit(ranking_enabled=False) == score_outfit when MODEL_PATH
    # absent, across style/freshness combinations, score stays in [0, 1].
    monkeypatch.setattr(ranking_model, "MODEL_PATH", tmp_path / "missing.joblib")
    ranking_model._load_model.cache_clear()

    for visual in (0.3, 0.6, 0.95):
        for style_match in (True, False):
            for recent in (0, 1, 3):
                disabled = ranking_model.score_outfit(
                    visual=visual, style_match=style_match, recent=recent,
                    context_fit=0.7, season_compat=0.7, history_fit=0.7,
                    ranking_enabled=False,
                )
                absent = ranking_model.score_outfit(
                    visual=visual, style_match=style_match, recent=recent,
                    context_fit=0.7, season_compat=0.7, history_fit=0.7,
                    ranking_enabled=True,
                )
                assert disabled == pytest.approx(absent)
                assert 0.0 <= disabled <= 1.0


# --- artifact-present formula with a fake persisted classifier ------------------


def test_score_outfit_artifact_formula(monkeypatch, tmp_path):
    p1 = 0.6
    model_path = tmp_path / "ranking_model.joblib"
    import joblib

    joblib.dump(_FakeRanker(p1=p1), model_path)
    monkeypatch.setattr(ranking_model, "MODEL_PATH", model_path)
    ranking_model._load_model.cache_clear()

    season_compat, history_fit, recent = 0.5, 0.4, 2
    score = ranking_model.score_outfit(
        visual=0.3, context_fit=0.2, history_fit=history_fit,
        season_compat=season_compat, style_match=True, recent=recent,
        ranking_enabled=True,
    )
    learned = p1
    base = (
        learned
        + ranking_model.SEASON_COMPAT_BONUS * season_compat
        + ranking_model.STYLE_MATCH_BONUS  # style_match=True
        + ranking_model.HISTORY_FIT_WEIGHT * history_fit
    )
    expected = max(0.0, min(1.0, base - ranking_model.RECENT_WEAR_PENALTY * recent))
    assert score == pytest.approx(expected)


def test_score_outfit_artifact_clamps_to_unit_interval(monkeypatch, tmp_path):
    # Large additive layer + high learned prob -> clamped to 1.0; heavy freshness ->
    # clamped to 0.0. Invariant score in [0, 1] is held by score_outfit.
    import joblib

    model_path = tmp_path / "ranking_model.joblib"
    joblib.dump(_FakeRanker(p1=0.9), model_path)
    monkeypatch.setattr(ranking_model, "MODEL_PATH", model_path)
    ranking_model._load_model.cache_clear()

    high = ranking_model.score_outfit(
        visual=0.9, context_fit=0.9, season_compat=1.0,
        history_fit=1.0, style_match=True, ranking_enabled=True,
    )
    assert high == pytest.approx(1.0)

    low = ranking_model.score_outfit(
        visual=0.1, context_fit=0.0, recent=50,  # huge freshness penalty
        ranking_enabled=True,
    )
    assert low == pytest.approx(0.0)


def test_score_outfit_predict_failure_falls_back_to_heuristic(monkeypatch, tmp_path):
    # A model whose predict_proba raises -> non-fatal WARNING + heuristic for this
    # outfit (the other candidates would still be ranked normally).
    import joblib

    model_path = tmp_path / "ranking_model.joblib"
    joblib.dump(_BrokenRanker(), model_path)
    monkeypatch.setattr(ranking_model, "MODEL_PATH", model_path)
    ranking_model._load_model.cache_clear()

    visual = 0.6
    score = ranking_model.score_outfit(visual=visual, style_match=True, recent=1, ranking_enabled=True)
    expected = max(
        0.0,
        min(1.0, visual + ranking_model.STYLE_MATCH_BONUS) - ranking_model.RECENT_WEAR_PENALTY * 1,
    )
    assert score == pytest.approx(expected)


# --- context_vector indexing + three fallback branches (review-F9/F10) ----------


def test_context_vector_indexes_specific_key(monkeypatch, tmp_path):
    specific = _unit(np.full(ranking_model.CONTEXT_DIM, 0.1, dtype=np.float32))
    any_band = _unit(np.full(ranking_model.CONTEXT_DIM, 0.2, dtype=np.float32))
    path = tmp_path / "context_vectors.npz"
    _write_vectors_npz(path, {
        "mariage|ete|chaud": specific,
        "mariage|ete|_any": any_band,
    })
    monkeypatch.setattr(ranking_model, "VECTORS_PATH", path)
    ranking_model._load_vectors.cache_clear()

    vec = ranking_model.context_vector("mariage", "ete", "chaud")
    assert np.allclose(vec, specific)
    assert np.isclose(np.linalg.norm(vec), 1.0, atol=1e-5)


def test_context_vector_band_agnostic_branch(monkeypatch, tmp_path):
    # season given, weather_band None -> band-agnostic key "occasion|season|_any".
    any_band = _unit(np.full(ranking_model.CONTEXT_DIM, 0.4, dtype=np.float32))
    path = tmp_path / "context_vectors.npz"
    _write_vectors_npz(path, {"travail|hiver|_any": any_band})
    monkeypatch.setattr(ranking_model, "VECTORS_PATH", path)
    ranking_model._load_vectors.cache_clear()

    vec = ranking_model.context_vector("travail", "hiver", None)
    assert np.allclose(vec, any_band)


def test_context_vector_season_none_returns_zeros(monkeypatch, tmp_path):
    # season is None -> zeros(512) computed on the fly, regardless of weather_band or
    # whether vectors are present (review-F10: the real trigger of the zero vector).
    path = tmp_path / "context_vectors.npz"
    _write_vectors_npz(path, {"travail|ete|chaud": _unit(np.ones(ranking_model.CONTEXT_DIM, dtype=np.float32))})
    monkeypatch.setattr(ranking_model, "VECTORS_PATH", path)
    ranking_model._load_vectors.cache_clear()

    for weather_band in ("chaud", None):
        vec = ranking_model.context_vector("travail", None, weather_band)
        assert vec.shape == (ranking_model.CONTEXT_DIM,)
        assert np.allclose(vec, 0.0)


def test_context_vector_out_of_vocab_occasion_falls_back_to_casual(monkeypatch, tmp_path):
    # An out-of-vocabulary occasion_category is normalized to casual_quotidien.
    casual_any = _unit(np.full(ranking_model.CONTEXT_DIM, 0.7, dtype=np.float32))
    path = tmp_path / "context_vectors.npz"
    _write_vectors_npz(path, {"casual_quotidien|mi_saison|_any": casual_any})
    monkeypatch.setattr(ranking_model, "VECTORS_PATH", path)
    ranking_model._load_vectors.cache_clear()

    vec = ranking_model.context_vector("not_a_real_category", "mi_saison", None)
    assert np.allclose(vec, casual_any)


# --- absent context_vectors.npz -> zeros, no crash -----------------------------


def test_context_vector_absent_npz_returns_zeros(monkeypatch, tmp_path):
    monkeypatch.setattr(ranking_model, "VECTORS_PATH", tmp_path / "missing.npz")
    ranking_model._load_vectors.cache_clear()

    vec = ranking_model.context_vector("travail", "ete", "chaud")
    assert vec.shape == (ranking_model.CONTEXT_DIM,)
    assert np.allclose(vec, 0.0)


def test_score_outfit_absent_vectors_no_crash(monkeypatch, tmp_path):
    # Model present but context_vectors absent -> ctx_vec=zeros -> context_fit=0 path;
    # score_outfit must not crash and stays in [0, 1].
    import joblib

    model_path = tmp_path / "ranking_model.joblib"
    joblib.dump(_FakeRanker(p1=0.5), model_path)
    monkeypatch.setattr(ranking_model, "MODEL_PATH", model_path)
    monkeypatch.setattr(ranking_model, "VECTORS_PATH", tmp_path / "missing.npz")
    ranking_model._load_model.cache_clear()
    ranking_model._load_vectors.cache_clear()

    score = ranking_model.score_outfit(visual=0.5, context_fit=0.0, ranking_enabled=True)
    assert 0.0 <= score <= 1.0


# --- monotonicity: higher visual_coherence -> higher score --------------------


def test_score_outfit_monotonic_in_visual(monkeypatch, tmp_path):
    import joblib

    model_path = tmp_path / "ranking_model.joblib"
    joblib.dump(_MonotonicRanker(), model_path)
    monkeypatch.setattr(ranking_model, "MODEL_PATH", model_path)
    ranking_model._load_model.cache_clear()

    context_fit = 0.1
    s_low = ranking_model.score_outfit(visual=0.2, context_fit=context_fit, ranking_enabled=True)
    s_mid = ranking_model.score_outfit(visual=0.5, context_fit=context_fit, ranking_enabled=True)
    s_high = ranking_model.score_outfit(visual=0.8, context_fit=context_fit, ranking_enabled=True)
    assert s_low < s_mid < s_high
    assert all(0.0 <= s <= 1.0 for s in (s_low, s_mid, s_high))


# --- compute_learned_features shape (2 features only, review-F5) ---------------


def test_compute_learned_features_is_two_features():
    feats = ranking_model.compute_learned_features(visual=0.3, context_fit=0.4)
    assert feats.shape == (1, 2)
    assert np.allclose(feats, np.array([[0.3, 0.4]], dtype=np.float32))

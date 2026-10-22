"""Contextual outfit ranker for the RecommendationAgent (axe 1 — fine-tuning du
classement).

A learned ``LogisticRegression`` ranks candidate outfits on two features that *are*
computable on the Polyvore training data — ``visual_coherence`` (mean pairwise
compatibility, reusing ``compatibility_model``) and ``context_fit`` (mean outfit image
embedding · a FashionCLIP *text* context vector, a zero-shot image-text match for "does
this outfit suit this occasion/season/weather"). The four other contextual signals
(``season_compat``, ``style_match``, ``freshness``, ``history_fit``) are **not**
learnable on Polyvore (items there have ``season=pd.NA``/``style=pd.NA`` and there is no
per-user usage history), so they are applied as a **deterministic additive layer** with
fixed, calibrated weights on top of the learned probability (review-F1, voie A).

The runtime loads only lightweight libraries — ``joblib`` + ``numpy`` + ``sklearn``.
The heavy image/text model runs solely offline in ``ml/notebooks/10_ranking_model.py``
to precompute the context vectors, which are then read here as a small ``.npz``.
See the design (§ Axe 1) and the review findings F1/F5/F9/F10/F12.

Two artifacts, both optional (produced by the notebook only if the ship-gate passes):
- ``artifacts/ranking_model.joblib`` — the trained ``LogisticRegression``.
- ``artifacts/context_vectors.npz`` — 96 precomputed L2-normalized FashionCLIP text
  vectors (72 specific ``occasion|season|band`` + 24 band-agnostic ``occasion|season|_any``;
  review-F9), stored as ``{keys: str[], vectors: (96, 512)}``.

When either artifact is absent — a fresh checkout, a failed ship-gate, or
``RANKING_ENABLED=False`` — ``score_outfit`` returns the **exact existing heuristic**
of ``recommendation_agent`` (review-F12), without ever touching the artifacts.
"""

from functools import lru_cache
from pathlib import Path
import logging

import numpy as np

from app.services.occasions import OCCASION_CATEGORIES

logger = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).resolve().parent / "artifacts" / "ranking_model.joblib"
VECTORS_PATH = Path(__file__).resolve().parent / "artifacts" / "context_vectors.npz"

# FashionCLIP projection dimension (patrickjohncyh/fashion-clip) — the same 512-dim
# space the item image embeddings (Pinecone) and the context text vectors live in, so
# ``mean(outfit_vecs) . ctx_vec`` is a legitimate zero-shot image-text match.
CONTEXT_DIM = 512

# Deterministic additive-layer weights. STYLE_MATCH_BONUS / RECENT_WEAR_PENALTY mirror
# recommendation_agent.py's existing constants (0.1 / 0.05) so the fallback path
# reproduces the existing heuristic byte-for-byte; they are redefined here rather than
# imported to avoid a circular import once recommendation_agent wires this module in
# (FEAT-005). Keep them in sync with recommendation_agent.py.
STYLE_MATCH_BONUS = 0.1
RECENT_WEAR_PENALTY = 0.05
# New deterministic weights for the contextual additive layer (axe 1, voie A — review-F1).
# Calibrated by hand to the same order of magnitude as STYLE_MATCH_BONUS; NOT learned
# (they cannot be — Polyvore has no season/style/usage labels) and NOT optimized on
# relevance labels (the app data has none). Tunable; finer calibration is backlog.
SEASON_COMPAT_BONUS = 0.1
HISTORY_FIT_WEIGHT = 0.1

# Fallback category used when occasion_category is missing or out-of-vocabulary.
_FALLBACK_CATEGORY = "casual_quotidien"

# One-shot guards so the "artifact absent" INFO log fires once per process rather than
# on every call.
_model_absence_logged = False
_vectors_absence_logged = False


@lru_cache
def _load_model():
    import joblib

    return joblib.load(MODEL_PATH)


@lru_cache
def _load_vectors() -> dict[str, np.ndarray]:
    """Load the precomputed context vectors as a ``key -> 512-dim vector`` dict.

    Returns ``{}`` when the ``.npz`` artifact is absent (fresh checkout / failed
    ship-gate) so ``context_vector`` degrades to a zero vector; logged INFO once.
    """
    global _vectors_absence_logged
    if not VECTORS_PATH.exists():
        if not _vectors_absence_logged:
            logger.info(
                "context_vectors.npz absent — context_vector will return zeros "
                "(context_fit degrades to 0); this is the fallback path."
            )
            _vectors_absence_logged = True
        return {}
    data = np.load(VECTORS_PATH, allow_pickle=False)
    keys = data["keys"].tolist()
    vectors = np.asarray(data["vectors"], dtype=np.float32)
    return {key: vec for key, vec in zip(keys, vectors)}


def context_vector(
    occasion_category: str | None, season: str | None, weather_band: str | None
) -> np.ndarray:
    """Look up the precomputed FashionCLIP *text* context vector for a situation.

    Three-branch fallback chain (review-F9/F10): ``parse_occasion_rules`` always yields a
    valid category, so the real trigger of the zero vector is a missing *season*.

    1. ``season`` and ``weather_band`` both given -> ``f"{occasion}|{season}|{band}"`
       (specific vector; 8×3×3 = 72 stored).
    2. ``season`` given but ``weather_band`` None -> ``f"{occasion}|{season}|_any"`
       (band-agnostic vector; 8×3 = 24 stored).
    3. ``season`` None -> ``zeros(512)`` computed on the fly (not stored).

    An out-of-vocabulary ``occasion_category`` falls back to ``casual_quotidien``. When
    the ``.npz`` artifact is absent (or the key is simply missing) the result is also
    ``zeros(512)`` — graceful degradation, no crash.
    """
    category = occasion_category if occasion_category in OCCASION_CATEGORIES else _FALLBACK_CATEGORY
    if season is None:
        return np.zeros(CONTEXT_DIM, dtype=np.float32)
    vectors = _load_vectors()
    if weather_band is None:
        key = f"{category}|{season}|_any"
    else:
        key = f"{category}|{season}|{weather_band}"
    return vectors.get(key, np.zeros(CONTEXT_DIM, dtype=np.float32))


def compute_learned_features(visual: float, context_fit: float) -> np.ndarray:
    """Two learned features fed to the LogisticRegression ranker (review-F5).

    Only ``visual_coherence`` and ``context_fit`` are learnable on Polyvore and feed
    ``predict_proba``. The other four signals (``season_compat``, ``style_match``,
    ``freshness``/``recent``, ``history_fit``) are the deterministic additive layer,
    computed and applied in :func:`score_outfit`, not learned.
    """
    return np.array([[visual, context_fit]], dtype=np.float32)


def _heuristic_score(visual: float, style_match: bool, recent: int) -> float:
    """Exact replication of recommendation_agent's existing scoring (review-F12):

    ``score = min(1.0, visual + (STYLE_MATCH_BONUS if style_match else 0.0))`` then
    ``max(0.0, score - RECENT_WEAR_PENALTY * recent)`` where ``recent`` is the integer
    count of recently-worn pieces and ``style_match`` is a boolean. No contextual
    feature is computed or applied — byte-for-byte identical to the current checkout.
    """
    score = min(1.0, visual + (STYLE_MATCH_BONUS if style_match else 0.0))
    return max(0.0, score - RECENT_WEAR_PENALTY * recent)


def score_outfit(
    *,
    visual: float,
    context_fit: float = 0.0,
    history_fit: float = 0.0,
    season_compat: float = 0.0,
    style_match: bool = False,
    recent: int = 0,
    ranking_enabled: bool = True,
) -> float:
    """Rank an outfit candidate, clamped to ``[0, 1]``.

    Fallback path (``ranking_enabled`` False **or** artifact absent): the exact existing
    heuristic (review-F12), **without loading the artifact** — so a fresh checkout and a
    disabled kill-switch behave identically.

    Artifact-present path: ``learned = predict_proba([[visual, context_fit]])[0, 1]``
    then the deterministic additive layer
    ``base = learned + SEASON_COMPAT_BONUS*season_compat + (STYLE_MATCH_BONUS if
    style_match else 0) + HISTORY_FIT_WEIGHT*history_fit`` and
    ``score = max(0, min(1, base - RECENT_WEAR_PENALTY*recent))``. Any failure during
    ``predict_proba`` falls back to the heuristic for this outfit and logs WARNING
    (non-fatal; the other candidates are still ranked normally).
    """
    # Deliberate kill-switch: silent heuristic, no artifact touch.
    if not ranking_enabled:
        return _heuristic_score(visual, style_match, recent)
    # Artifact absent: heuristic, logged INFO once.
    if not MODEL_PATH.exists():
        global _model_absence_logged
        if not _model_absence_logged:
            logger.info(
                "ranking_model.joblib absent — using exact heuristic fallback "
                "(ship-gate not passed or fresh checkout)."
            )
            _model_absence_logged = True
        return _heuristic_score(visual, style_match, recent)
    try:
        model = _load_model()
        learned = float(model.predict_proba(compute_learned_features(visual, context_fit))[0, 1])
        base = (
            learned
            + SEASON_COMPAT_BONUS * season_compat
            + (STYLE_MATCH_BONUS if style_match else 0.0)
            + HISTORY_FIT_WEIGHT * history_fit
        )
        return max(0.0, min(1.0, base - RECENT_WEAR_PENALTY * recent))
    except Exception:  # noqa: BLE001 — non-fatal: rank this outfit with the heuristic
        logger.warning(
            "ranking model prediction failed; falling back to heuristic for this outfit",
            exc_info=True,
        )
        return _heuristic_score(visual, style_match, recent)

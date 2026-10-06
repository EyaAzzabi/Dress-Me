"""Pairwise outfit-compatibility scorer, trained on real Polyvore outfit co-occurrence
(68,306 real outfits — see ml/notebooks/09_compatibility_model.py for how it was
trained and validated). Replaces the raw-cosine-similarity heuristic
RecommendationAgent used to score outfit coherence.

Honest result on held-out, never-seen-during-training outfits: AUC 0.674 vs. 0.609
and accuracy 62.3% vs. 58.3% for plain cosine similarity — a real but modest
improvement, not a dramatic one. A linear probe on frozen embeddings captures somewhat
more than raw similarity, not a lot more.
"""

from functools import lru_cache
from pathlib import Path

import numpy as np

MODEL_PATH = Path(__file__).resolve().parent / "artifacts" / "compatibility_model.joblib"


@lru_cache
def _load_model():
    import joblib

    return joblib.load(MODEL_PATH)


def pair_compatibility(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """Probability these two L2-normalized embeddings were styled together in a real
    outfit, per the trained model. Falls back to raw cosine similarity if the
    artifact is missing (e.g. a fresh checkout before copying it from ml/)."""
    if not MODEL_PATH.exists():
        return float(vec_a @ vec_b)
    model = _load_model()
    feature = (vec_a * vec_b).reshape(1, -1)
    return float(model.predict_proba(feature)[0, 1])

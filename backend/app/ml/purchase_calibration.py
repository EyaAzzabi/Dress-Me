"""Turns PurchaseAgent's raw scores into percentiles of a real reference distribution.

The quantiles in artifacts/purchase_calibration.json come from random pairings of
real Tunisian catalog garments (scripts/calibrate_purchase_agent.py). A percentile
of 0.85 reads as "better than 85 % of random combinations" — meaningful to a user
and comparable across score types, unlike a raw compatibility probability that only
ever moves between ~0.45 and ~0.65.
"""

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

CALIBRATION_PATH = Path(__file__).resolve().parent / "artifacts" / "purchase_calibration.json"
QUANTILE_LEVELS = list(range(0, 101, 5))

# Used only when the artifact is missing: a linear ramp over each score's observed
# min-max on the catalog (3,000 random samples).
_FALLBACK_RANGES = {
    "base_compatibility": (0.34, 0.69),
    "optional_compatibility": (0.30, 0.70),
    "style_fit": (0.32, 0.80),
}


@lru_cache
def _load() -> dict | None:
    if not CALIBRATION_PATH.exists():
        return None
    return json.loads(CALIBRATION_PATH.read_text())


def percentile(kind: str, value: float) -> float:
    """Share (0-1) of the reference distribution `kind` that `value` beats."""
    calibration = _load()
    if calibration is None:
        low, high = _FALLBACK_RANGES[kind]
        return float(np.clip((value - low) / (high - low), 0.0, 1.0))
    quantiles = calibration[kind]
    levels = np.array(calibration["quantile_levels"]) / 100
    return float(np.interp(value, quantiles, levels))

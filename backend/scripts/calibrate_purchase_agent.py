"""Calibrates PurchaseAgent on real data instead of guessing thresholds.

Uses the FashionCLIP embeddings of the Tunisian catalog
(app/data/catalog_embeddings.npz) as a stand-in population of real garments, and
writes app/ml/artifacts/purchase_calibration.json: the quantiles of each raw score
over random pairings, so the agent can turn a raw score into "better than X % of
random combinations" (app/ml/purchase_calibration.py).

- base_compatibility / optional_compatibility: the Polyvore compatibility model's
  probability over random haut x bas and haut x (veste|chaussures|sac|accessoire)
  pairs. Its raw output is squeezed around 0.54 (p10 0.48, p90 0.60), so a fixed
  probability threshold is meaningless — a percentile isn't.
- style_fit: cosine similarity between a random item and the centroid of a random
  15-item "wardrobe".
- Also printed, for the fixed similarity thresholds: nearest same-category neighbour
  and random same-category pair similarities.

Usage (from backend/):  python -m scripts.calibrate_purchase_agent
"""

import json
import sys
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.ml import compatibility_model  # noqa: E402
from app.ml.purchase_calibration import CALIBRATION_PATH, QUANTILE_LEVELS  # noqa: E402
from app.services.catalog_index import _load_index  # noqa: E402

RNG = np.random.default_rng(42)
PERCENTILES = [10, 25, 50, 75, 90, 95, 99]
SAMPLES = 3000


def show(name: str, values) -> None:
    stats = "  ".join(f"p{p}={v:.3f}" for p, v in zip(PERCENTILES, np.percentile(values, PERCENTILES)))
    print(f"{name:<38} n={len(values):<5} mean={np.mean(values):.3f}  {stats}")


def main() -> None:
    products, vectors = _load_index()
    if len(products) == 0:
        sys.exit("No catalog index — run `python -m scripts.build_catalog_index` first.")
    categories = products["dressme_category"].to_numpy()
    by_category = {c: np.flatnonzero(categories == c) for c in np.unique(categories)}
    print(f"{len(products)} catalog embeddings: " + ", ".join(f"{c}={len(i)}" for c, i in by_category.items()))

    def compat_sample(left, right) -> list[float]:
        pairs = [(RNG.choice(left), RNG.choice(right)) for _ in range(SAMPLES)]
        return [compatibility_model.pair_compatibility(vectors[a], vectors[b]) for a, b in pairs]

    hauts, bas = by_category["haut"], by_category["bas"]
    base_compat = compat_sample(hauts, bas)
    show("compatibility, random haut x bas", base_compat)

    optional = np.concatenate([by_category[c] for c in ("chaussures", "sac", "accessoire", "veste") if c in by_category])
    wearable = np.concatenate([hauts, bas, by_category["robe"]])
    optional_compat = compat_sample(wearable, optional)
    show("compatibility, random wearable x optional", optional_compat)

    style_fit = []
    for _ in range(SAMPLES):
        wardrobe = RNG.choice(len(vectors), size=15, replace=False)
        centroid = vectors[wardrobe].mean(axis=0)
        centroid /= np.linalg.norm(centroid)
        candidate = RNG.integers(len(vectors))
        style_fit.append(float(vectors[candidate] @ centroid))
    show("style fit, item vs 15-item centroid", style_fit)

    nearest = []
    for c, idx in by_category.items():
        sample = RNG.choice(idx, size=min(300, len(idx)), replace=False)
        sims = vectors[sample] @ vectors[idx].T
        sims[np.arange(len(sample)), np.searchsorted(idx, sample)] = -1  # exclude self
        nearest.extend(sims.max(axis=1))
    show("nearest same-category neighbour", nearest)

    random_same = []
    for c, idx in by_category.items():
        a, b = RNG.choice(idx, size=500), RNG.choice(idx, size=500)
        random_same.extend(np.sum(vectors[a] * vectors[b], axis=1))
    show("random same-category pair", random_same)

    calibration = {
        "quantile_levels": QUANTILE_LEVELS,
        "base_compatibility": np.percentile(base_compat, QUANTILE_LEVELS).round(5).tolist(),
        "optional_compatibility": np.percentile(optional_compat, QUANTILE_LEVELS).round(5).tolist(),
        "style_fit": np.percentile(style_fit, QUANTILE_LEVELS).round(5).tolist(),
        "source": f"{len(products)} Tunisian catalog FashionCLIP embeddings, {SAMPLES} random samples each",
    }
    CALIBRATION_PATH.write_text(json.dumps(calibration, indent=2))
    print(f"Saved {CALIBRATION_PATH}")


if __name__ == "__main__":
    main()

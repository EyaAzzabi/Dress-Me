"""Evaluates how well the Vision Agent tells clothing from non-clothing photos.

- Clothing set: the in-scope Tunisian catalog embeddings (app/data/catalog_embeddings.npz).
- Non-clothing set: ~250 random real-world photos from picsum.photos (landscapes,
  animals, food, objects, cities...) — the kind of photo the category classifier never
  saw: its hors_perimetre class was only trained on non-clothing catalog products.

Reports, for the current classifier alone and combined with the zero-shot gate in
app/ml/vision_model.py at several thresholds, the share of clothing wrongly rejected
and of non-clothing wrongly accepted.

Usage (from backend/):  python -m scripts.evaluate_clothing_gate
"""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.ml import vision_model  # noqa: E402
from app.services.catalog_index import _load_index  # noqa: E402

OOD_CACHE = Path(__file__).resolve().parent / ".ood_picsum.npy"
PICSUM_IDS = range(0, 260)


def _download(picsum_id: int) -> bytes | None:
    try:
        response = httpx.get(f"https://picsum.photos/id/{picsum_id}/400/400", follow_redirects=True, timeout=30)
        response.raise_for_status()
    except Exception:  # noqa: BLE001 — some ids don't exist
        return None
    return response.content


def non_clothing_embeddings() -> np.ndarray:
    if OOD_CACHE.exists():
        return np.load(OOD_CACHE)
    with ThreadPoolExecutor(max_workers=12) as pool:
        images = [content for content in pool.map(_download, PICSUM_IDS) if content]
    vectors = np.array([vision_model.embed_image_bytes(content) for content in images])
    np.save(OOD_CACHE, vectors)
    return vectors


def main() -> None:
    _, clothing = _load_index()
    if len(clothing) == 0:
        sys.exit("No catalog index — run `python -m scripts.build_catalog_index` first.")
    non_clothing = non_clothing_embeddings()
    print(f"{len(clothing)} clothing photos, {len(non_clothing)} non-clothing photos\n")

    classifier = vision_model._load_category_classifier()

    def classifier_rejects(vectors):
        return classifier.predict(vectors) == "hors_perimetre"

    p_clothing = vision_model.clothing_probability(clothing)
    p_non_clothing = vision_model.clothing_probability(non_clothing)

    print(f"{'rule':<40}{'clothing rejected':>20}{'non-clothing accepted':>24}")

    def report(name, rejected_clothing, rejected_non_clothing):
        print(f"{name:<40}{rejected_clothing.mean() * 100:>19.1f}%{(~rejected_non_clothing).mean() * 100:>23.1f}%")

    report("classifier only", classifier_rejects(clothing), classifier_rejects(non_clothing))
    for threshold in (0.2, 0.3, 0.4, 0.5):
        marker = "  <- shipped" if threshold == vision_model.CLOTHING_GATE_THRESHOLD else ""
        report(f"classifier + zero-shot gate < {threshold}{marker}",
               classifier_rejects(clothing) | (p_clothing < threshold),
               classifier_rejects(non_clothing) | (p_non_clothing < threshold))


if __name__ == "__main__":
    main()

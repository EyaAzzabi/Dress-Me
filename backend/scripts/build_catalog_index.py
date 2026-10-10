"""Builds app/data/catalog_embeddings.npz: one FashionCLIP embedding per in-scope
product of the bundled Tunisian catalog (app/data/tunisian_catalog.parquet).

Uses the exact same model and preprocessing as the Vision Agent
(app/ml/vision_model.py), so catalog vectors are directly comparable with wardrobe
and purchase-candidate vectors — that's what lets PurchaseAgent search the catalog
by image similarity instead of by product-name keywords.

Resumable: downloaded images are cached in scripts/.catalog_images/, so re-running
after a network failure only fetches what's missing.

Usage (from backend/):  python -m scripts.build_catalog_index
"""

import io
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.ml import vision_model  # noqa: E402
from app.services.ecommerce import CATALOG_PATH  # noqa: E402

OUTPUT_PATH = BACKEND / "app" / "data" / "catalog_embeddings.npz"
IMAGE_CACHE = Path(__file__).resolve().parent / ".catalog_images"
BATCH_SIZE = 32
DOWNLOAD_WORKERS = 16


def _download(key_and_url: tuple[str, str]) -> tuple[str, bytes | None]:
    key, url = key_and_url
    cached = IMAGE_CACHE / f"{key}.img"
    if cached.exists():
        return key, cached.read_bytes()
    try:
        response = httpx.get(url, timeout=20.0, follow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0 (compatible; DressMe/1.0)"})
        response.raise_for_status()
    except Exception:  # noqa: BLE001
        return key, None
    cached.write_bytes(response.content)
    return key, response.content


def _embed_batch(images: list) -> np.ndarray:
    import torch

    model, processor, device = vision_model._load_fashionclip()
    inputs = processor(images=images, return_tensors="pt").to(device)
    with torch.no_grad():
        pooled = model.vision_model(pixel_values=inputs["pixel_values"]).pooler_output
        projected = model.visual_projection(pooled)
    return vision_model._normalize(projected.float().cpu().numpy())


def main() -> None:
    from PIL import Image

    IMAGE_CACHE.mkdir(exist_ok=True)
    catalog = pd.read_parquet(CATALOG_PATH)
    catalog = catalog[(catalog["dressme_category"] != "hors_perimetre")
                      & catalog["image_location"].notna() & catalog["item_key"].notna()]
    print(f"{len(catalog)} in-scope catalog products to embed")

    keys, vectors = [], []
    batch_keys, batch_images = [], []
    failed = 0

    def flush() -> None:
        if batch_images:
            vectors.append(_embed_batch(batch_images))
            keys.extend(batch_keys)
            batch_keys.clear()
            batch_images.clear()

    jobs = list(zip(catalog["item_key"], catalog["image_location"]))
    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
        for i, (key, content) in enumerate(pool.map(_download, jobs), 1):
            image = None
            if content is not None:
                try:
                    image = Image.open(io.BytesIO(content)).convert("RGB")
                except Exception:  # noqa: BLE001 — corrupt/unsupported image file
                    image = None
            if image is None:
                failed += 1
            else:
                batch_keys.append(key)
                batch_images.append(image)
                if len(batch_images) == BATCH_SIZE:
                    flush()
            if i % 500 == 0:
                print(f"[{i}/{len(jobs)}] embedded {len(keys)}, failed {failed}", flush=True)
    flush()

    matrix = np.vstack(vectors).astype(np.float16)
    np.savez_compressed(OUTPUT_PATH, item_keys=np.array(keys), embeddings=matrix)
    print(f"Saved {matrix.shape[0]} embeddings ({failed} images unavailable) to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

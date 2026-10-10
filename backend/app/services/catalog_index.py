"""Visual search over the bundled Tunisian catalog.

Each in-scope product has a precomputed FashionCLIP embedding
(app/data/catalog_embeddings.npz, built by scripts/build_catalog_index.py with the
same model as the Vision Agent), so a purchase candidate's own embedding can be
matched against real products by what they look like — not by product-name keywords,
which is all EcommerceService.search_products can do.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from app.services import tunisian_brands
from app.services.ecommerce import _load_catalog

INDEX_PATH = Path(__file__).resolve().parents[1] / "data" / "catalog_embeddings.npz"


def parse_price(raw: object) -> float | None:
    """The scraped prices mix formats ("49,99 TND", "44.9", "1 299,00 DT") — returns
    the amount in TND as a float, or None if there's no usable number."""
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return None
    text = str(raw).replace("\u00a0", " ")
    match = re.search(r"\d[\d ]*(?:[.,]\d+)?", text)
    if not match:
        return None
    number = match.group(0).replace(" ", "").replace(",", ".")
    try:
        value = float(number)
    except ValueError:
        return None
    return value if value > 0 else None


@dataclass(frozen=True)
class CatalogMatch:
    item_key: str
    name: str
    brand: str | None
    category: str
    price: float | None
    image_url: str | None
    similarity: float

    def to_dict(self) -> dict:
        return {
            "item_key": self.item_key,
            "name": self.name,
            "brand": self.brand,
            "category": self.category,
            "price": self.price,
            "image_url": self.image_url,
            "similarity": round(self.similarity, 3),
            **tunisian_brands.links(self.item_key, self.brand),
        }


# A brand's affinity is the mean similarity of its few closest products: one lucky
# match doesn't make a brand, and a big catalog doesn't either.
BRAND_TOP_K = 3
BRAND_MIN_PRODUCTS = 3  # fewer products in the category: not enough to judge the brand
BRAND_SHOWCASE = 2


class CatalogIndex:
    def __init__(self) -> None:
        self._products, self._vectors = _load_index()

    def is_available(self) -> bool:
        return len(self._products) > 0

    def search(self, embedding: np.ndarray, *, category: str | None = None, limit: int = 10) -> list[CatalogMatch]:
        if not self.is_available():
            return []
        candidates = self._candidates(category)
        if candidates.size == 0:
            return []
        scores = self._vectors[candidates] @ np.asarray(embedding, dtype=np.float32)
        order = np.argsort(-scores)[:limit]
        return [self._match(candidates[i], scores[i]) for i in order]

    def get(self, item_key: str) -> CatalogMatch | None:
        rows = np.flatnonzero((self._products["item_key"] == item_key).to_numpy()) if self.is_available() else []
        return self._match(rows[0], 1.0) if len(rows) else None

    def brand_affinity(self, embedding: np.ndarray, *, category: str | None = None) -> list[dict]:
        """Ranks the Tunisian brands by how close their products look to `embedding`
        (FashionCLIP space), each with its best-matching products as a showcase."""
        if not self.is_available():
            return []
        candidates = self._candidates(category)
        if candidates.size == 0:
            return []
        scores = self._vectors[candidates] @ np.asarray(embedding, dtype=np.float32)
        brands = self._products["brand"].to_numpy()[candidates]

        ranking = []
        for name in set(brands) - {None}:
            in_brand = np.flatnonzero(brands == name)
            if in_brand.size < BRAND_MIN_PRODUCTS:
                continue
            best = in_brand[np.argsort(-scores[in_brand])]
            prices = [p for p in self._products["price_tnd"].to_numpy()[candidates[in_brand]] if p is not None]
            brand = tunisian_brands.by_name(name)
            ranking.append({
                "name": name,
                "website": brand.website if brand else None,
                "affinity": round(float(scores[best[:BRAND_TOP_K]].mean()), 3),
                "product_count": int(in_brand.size),
                "price_min": round(min(prices), 2) if prices else None,
                "price_max": round(max(prices), 2) if prices else None,
                "showcase": [self._match(candidates[i], scores[i]).to_dict() for i in best[:BRAND_SHOWCASE]],
            })
        ranking.sort(key=lambda b: b["affinity"], reverse=True)
        return ranking

    def _candidates(self, category: str | None) -> np.ndarray:
        if not category:
            return np.arange(len(self._products))
        return np.flatnonzero((self._products["dressme_category"] == category).to_numpy())

    def _match(self, row_index: int, score: float) -> CatalogMatch:
        row = self._products.iloc[int(row_index)]
        return CatalogMatch(
            item_key=row["item_key"],
            name=row["name"],
            brand=row["brand"],
            category=row["dressme_category"],
            price=row["price_tnd"],
            image_url=row["image_location"],
            similarity=float(score),
        )


@lru_cache
def _load_index() -> tuple[pd.DataFrame, np.ndarray]:
    if not INDEX_PATH.exists():
        return pd.DataFrame(), np.empty((0, 512), dtype=np.float32)

    data = np.load(INDEX_PATH)
    catalog = _load_catalog().dropna(subset=["item_key"]).drop_duplicates("item_key").set_index("item_key")
    keys = pd.Series(data["item_keys"], name="item_key")
    known = keys.isin(catalog.index).to_numpy()  # tolerate an index built from an older catalog
    products = catalog.loc[keys[known]].reset_index()
    products["price_tnd"] = products["price"].map(parse_price)
    products = products.astype(object).where(products.notna(), None)
    return products, data["embeddings"][known].astype(np.float32)

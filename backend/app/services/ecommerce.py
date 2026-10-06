from functools import lru_cache
from pathlib import Path

import pandas as pd

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "tunisian_catalog.parquet"


class EcommerceService:
    """Searches real Tunisian e-commerce products to enrich purchase suggestions.

    The original docstring here named Zara/H&M — international chains with no public
    product-catalog API a prototype could realistically call. What the project
    actually has is real, legitimately-scraped data from nine Tunisian brands
    (ml/scraping/, see ml/README.md): 9,208 products with name/price/category/image.
    That's a grounded substitute, not a stand-in for a real integration elsewhere.
    """

    def __init__(self) -> None:
        self._catalog = _load_catalog()

    def search_products(self, query: str, *, category: str | None = None, limit: int = 10) -> list[dict]:
        if not query or self._catalog.empty:
            return []

        df = self._catalog
        if category:
            df = df[df["dressme_category"] == category]
        if df.empty:
            return []

        words = [w for w in query.lower().split() if w]
        name_lower = df["name"].str.lower()
        scores = sum(name_lower.str.contains(w, regex=False) for w in words)
        matched = df[scores > 0].copy()
        if matched.empty:
            return []
        matched["_score"] = scores[scores > 0]

        results = matched.sort_values("_score", ascending=False).head(limit)
        return [
            {
                "name": row["name"],
                "price": row["price"],
                "brand": row["brand"],
                "category": row["dressme_category"],
                "image_url": row["image_location"],
            }
            for _, row in results.iterrows()
        ]


@lru_cache
def _load_catalog() -> pd.DataFrame:
    if not CATALOG_PATH.exists():
        return pd.DataFrame(columns=["name", "dressme_category", "price", "brand", "image_location"])
    return pd.read_parquet(CATALOG_PATH)

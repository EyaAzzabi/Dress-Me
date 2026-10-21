"""Closed sandbox of Purchase tools. The LLM never gets Python, SQL or the web.

It may only emit a tool name from TOOL_SPECS. The sandbox holds the FashionCLIP
embedding and the wardrobe in memory: the model never sees those vectors, only the
JSON each tool returns (scores, prices, brand names).
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np

from app.services.catalog_index import CatalogIndex
from app.services.ecommerce import EcommerceService

TOOL_SPECS = [
    {
        "name": "inspect_wardrobe",
        "description": "Compare la pièce à la garde-robe : doublons, tenues débloquées, style.",
    },
    {
        "name": "search_tunisian_catalog",
        "description": "Produits tunisiens visuellement proches (FashionCLIP, même catégorie).",
    },
    {
        "name": "compare_market_price",
        "description": "Place le prix saisi parmi les voisins visuels déjà trouvés.",
    },
    {
        "name": "rank_tunisian_brands",
        "description": "Marques tunisiennes dont le catalogue ressemble à la pièce (et au style).",
    },
    {
        "name": "estimate_cost_per_wear",
        "description": "Estime le coût par port à partir du prix et de la polyvalence.",
    },
]


class UnknownPurchaseTool(PermissionError):
    """The LLM asked for a tool that is not in the sandbox."""


class PurchaseToolSandbox:
    """Allow-list only. bind() first; then call(name) uses the bound context."""

    def __init__(self, catalog: CatalogIndex | None = None, ecommerce: EcommerceService | None = None) -> None:
        self.catalog = catalog or CatalogIndex()
        self.ecommerce = ecommerce or EcommerceService()
        self.ctx: dict[str, Any] = {}
        self._cache: dict[str, Any] = {}
        self._tools: dict[str, Callable[..., Any]] = {
            spec["name"]: getattr(self, spec["name"]) for spec in TOOL_SPECS
        }

    def names(self) -> list[str]:
        return list(self._tools)

    def bind(
        self,
        *,
        embedding,
        category: str,
        owned: list,
        price: float | None,
        item: dict,
    ) -> None:
        self.ctx = {
            "embedding": np.asarray(embedding, dtype=float),
            "category": category,
            "owned": owned,
            "price": price,
            "item": item,
        }
        self._cache = {}

    def call(self, name: str, **kwargs: Any) -> Any:
        tool = self._tools.get(name)
        if tool is None:
            raise UnknownPurchaseTool(f"Tool {name!r} is not in the Purchase sandbox.")
        return tool(**kwargs)

    def inspect_wardrobe(self) -> dict:
        from app.agents import purchase_agent as pa

        candidate, category, owned = self.ctx["embedding"], self.ctx["category"], self.ctx["owned"]
        duplicates = pa._find_duplicates(candidate, category, owned)
        outfits = pa._unlocked_outfits(candidate, category, owned)
        versatility = pa._versatility_factor(outfits, category, owned)
        uniqueness = pa._uniqueness_factor(duplicates, category, owned)
        style_fit = pa._style_fit_factor(candidate, owned)
        self._cache.update(duplicates=duplicates, outfits=outfits, versatility=versatility)
        return {
            "wardrobe_size": len(owned),
            "duplicates": [{"similarity": d["similarity"], "category": d["category"]} for d in duplicates],
            "outfits_unlocked": len(outfits),
            "versatility": versatility,
            "uniqueness": uniqueness,
            "style_fit": style_fit,
        }

    def search_tunisian_catalog(self, limit: int = 20) -> list[dict]:
        matches = self.catalog.search(self.ctx["embedding"], category=self.ctx["category"], limit=limit)
        self._cache["neighbours"] = matches
        return [
            {"name": m.name, "brand": m.brand, "price": m.price, "similarity": round(m.similarity, 3)}
            for m in matches[:8]
        ]

    def compare_market_price(self) -> dict | None:
        from app.agents.purchase_agent import _price_insight

        neighbours = self._cache.get("neighbours")
        if neighbours is None:
            neighbours = self.catalog.search(self.ctx["embedding"], category=self.ctx["category"], limit=20)
            self._cache["neighbours"] = neighbours
        insight = _price_insight(self.ctx["price"], neighbours)
        self._cache["price_insight"] = insight
        return insight

    def rank_tunisian_brands(self) -> list[dict]:
        from app.agents.purchase_agent import BRAND_STYLE_BLEND, BRANDS_LIMIT

        query = self.ctx["embedding"]
        owned = self.ctx["owned"]
        if owned:
            centroid = np.mean([vec for _, vec in owned], axis=0)
            query = (1 - BRAND_STYLE_BLEND) * query + BRAND_STYLE_BLEND * centroid / max(np.linalg.norm(centroid), 1e-12)
            query = query / max(np.linalg.norm(query), 1e-12)
        ranking = self.catalog.brand_affinity(query, category=self.ctx["category"])[:BRANDS_LIMIT]
        self._cache["brands"] = ranking
        return [{"name": b["name"], "affinity": b["affinity"]} for b in ranking]

    def estimate_cost_per_wear(self) -> dict | None:
        from app.agents.purchase_agent import DUPLICATE_SIMILARITY, _cost_per_wear

        duplicates = self._cache.get("duplicates") or []
        versatility = self._cache.get("versatility")
        is_duplicate = bool(duplicates) and duplicates[0]["similarity"] >= DUPLICATE_SIMILARITY
        value = _cost_per_wear(self.ctx["price"], self.ctx["category"], versatility, is_duplicate)
        self._cache["cost_per_wear"] = value
        return value

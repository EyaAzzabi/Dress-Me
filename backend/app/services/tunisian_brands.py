"""The Tunisian brands of the bundled catalog, and how to link to their products.

The catalog keeps an `item_key` per product rather than its URL, so each brand's
product page is rebuilt from it:

- Shopify stores: the key is `<source>_<handle>` (ml/src/catalog.py) and Shopify
  serves every product at `<website>/products/<handle>`;
- Barsha and Hamadi Abid: the key only keeps the product id and some products have
  been taken down since, so their pages are resolved and checked once
  (scripts/build_product_urls.py); a product missing there is no longer online.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PRODUCT_URLS_PATH = Path(__file__).resolve().parents[1] / "data" / "product_urls.json"


@dataclass(frozen=True)
class Brand:
    name: str  # as in the catalog's `brand` column
    website: str
    key_prefix: str  # item_key prefix of this brand's products
    shopify: bool  # live stock and cart permalinks available

    def product_id(self, item_key: str) -> str | None:
        if not item_key.startswith(self.key_prefix):
            return None
        return item_key[len(self.key_prefix):] or None

    def product_url(self, item_key: str) -> str | None:
        product_id = self.product_id(item_key)
        if product_id is None:
            return None
        if self.shopify:
            return f"{self.website}/products/{product_id}"
        return _resolved_product_urls().get(item_key)


BRANDS = [
    Brand("Chedly Sisters", "https://chedlysisters.com", "chedly_sisters_", True),
    Brand("Noonclo", "https://noonclo.com", "noonclo_", True),
    Brand("Kontakt", "https://kontakt.com.tn", "kontakt_", True),
    Brand("Lyoum", "https://lyoum.co", "lyoum_", True),
    Brand("Rooh Clothing", "https://www.rooh-clothing.com", "rooh_clothing_", True),
    Brand("MY JEBBA", "https://myjebba.com", "myjebba_", True),
    Brand("Ileycom", "https://ileycom.tn", "ileycom_", True),
    Brand("Hamadi Abid", "https://ha.com.tn", "ha_", False),
    Brand("Barsha", "https://www.barsha.com.tn", "barsha_", False),
]
_BY_NAME = {b.name: b for b in BRANDS}


def by_name(name: str | None) -> Brand | None:
    return _BY_NAME.get(name) if name else None


def by_item_key(item_key: str) -> Brand | None:
    # Longest prefix first: "chedly_sisters_" must not be read as another brand's key.
    for brand in sorted(BRANDS, key=lambda b: len(b.key_prefix), reverse=True):
        if item_key.startswith(brand.key_prefix):
            return brand
    return None


def links(item_key: str | None, brand_name: str | None) -> dict:
    """product_url (the product's own page, or None if it is no longer online),
    store_url (brand site) and whether it can be bought from DressMe (live sizes +
    checkout, Shopify stores only)."""
    brand = by_name(brand_name) or (by_item_key(item_key) if item_key else None)
    if brand is None:
        return {"product_url": None, "store_url": None, "buyable": False}
    product_url = brand.product_url(item_key) if item_key else None
    return {
        "product_url": product_url,
        "store_url": brand.website,
        "buyable": brand.shopify and product_url is not None,
    }


@lru_cache
def _resolved_product_urls() -> dict[str, str]:
    if not PRODUCT_URLS_PATH.exists():
        return {}
    return json.loads(PRODUCT_URLS_PATH.read_text(encoding="utf-8"))

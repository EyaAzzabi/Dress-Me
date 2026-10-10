"""Live product data and checkout links from the Tunisian brands' own stores.

The Shopify stores serve each product's current state at `/products/<handle>.js`
(price, stock, one variant per size/colour), and a cart permalink
`/cart/<variant_id>:<quantity>` opens the store's real checkout with the product
already in the cart. Payment happens on the brand's site — DressMe never handles it.

Only products of the known brands are looked up (from their item_key, never from a
client-supplied URL), and answers are cached briefly to stay polite to the stores.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from app.services import tunisian_brands

CACHE_SECONDS = 120
TIMEOUT_SECONDS = 8.0
USER_AGENT = "Mozilla/5.0 (compatible; DressMe/1.0; +student project)"

_cache: dict[str, tuple[float, dict | None]] = {}


class ProductUnavailable(Exception):
    """The store couldn't be reached, or the product is gone."""


def live_product(item_key: str) -> dict:
    brand = tunisian_brands.by_item_key(item_key)
    product_url = brand.product_url(item_key) if brand and brand.shopify else None
    if product_url is None:
        raise ProductUnavailable(item_key)

    cached = _cache.get(item_key)
    if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        if cached[1] is None:
            raise ProductUnavailable(item_key)
        return cached[1]

    try:
        response = httpx.get(f"{product_url}.js", timeout=TIMEOUT_SECONDS, follow_redirects=True,
                             headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        product = _parse(response.json(), brand, product_url)
    except (httpx.HTTPError, ValueError, KeyError):
        _cache[item_key] = (time.monotonic(), None)
        raise ProductUnavailable(item_key) from None
    _cache[item_key] = (time.monotonic(), product)
    return product


def live_prices(item_keys: list[str]) -> dict[str, dict | None]:
    """live_product for many items at once; None for those that can't be fetched."""
    def fetch(key):
        try:
            return key, live_product(key)
        except ProductUnavailable:
            return key, None

    if not item_keys:
        return {}
    with ThreadPoolExecutor(max_workers=min(8, len(item_keys))) as pool:
        return dict(pool.map(fetch, item_keys))


def _parse(data: dict, brand: tunisian_brands.Brand, product_url: str) -> dict:
    variants = [{
        "id": v["id"],
        "title": None if v["title"] == "Default Title" else v["title"],
        "available": bool(v["available"]),
        "price": _money(v["price"]),
        "checkout_url": f"{brand.website}/cart/{v['id']}:1",
    } for v in data["variants"]]
    image = data.get("featured_image")
    compare_at = _money(data.get("compare_at_price"))
    price = _money(data["price"])
    return {
        "title": data["title"],
        "brand": brand.name,
        "product_url": product_url,
        "store_url": brand.website,
        "image_url": f"https:{image}" if image and image.startswith("//") else image,
        "price": price,
        "compare_at_price": compare_at if compare_at and price and compare_at > price else None,
        "available": bool(data["available"]),
        "variants": variants,
    }


def _money(cents) -> float | None:
    """Shopify amounts are in hundredths of the shop currency (TND here)."""
    return round(cents / 100, 2) if cents else None

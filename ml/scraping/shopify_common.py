"""Shared scraping logic for Tunisian Shopify stores (Chedly Sisters, Noonclo, ...).

Shopify exposes a public, documented `/products.json` endpoint — no Playwright/browser
rendering needed, just plain HTTP. Always check robots.txt before pointing this at a new
store; Shopify's default robots.txt explicitly allows crawling public product data, but
confirm it hasn't been customized to restrict that before reusing this.
"""

import csv
import time
from pathlib import Path

import httpx

USER_AGENT = "Mozilla/5.0 (compatible; DressMe-research-bot/1.0; +educational project)"
REQUEST_DELAY_SECONDS = 1.0


def fetch_page(base_url: str, page: int) -> list[dict]:
    resp = httpx.get(
        f"{base_url}/products.json",
        params={"limit": 250, "page": page},
        headers={"User-Agent": USER_AGENT},
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()["products"]


def extract_colors(product: dict) -> str:
    color_option_idx = None
    for i, option in enumerate(product.get("options", []), start=1):
        if option["name"].strip().lower() in ("color", "colour", "couleur"):
            color_option_idx = i
            break
    if color_option_idx is None:
        return ""
    key = f"option{color_option_idx}"
    colors = {v[key] for v in product["variants"] if v.get(key)}
    return ";".join(sorted(colors))


def parse_product(product: dict, base_url: str, brand: str) -> dict:
    variants = product.get("variants", [])
    prices = [float(v["price"]) for v in variants if v.get("price")]
    compare_prices = [float(v["compare_at_price"]) for v in variants if v.get("compare_at_price")]
    images = product.get("images", [])

    return {
        "brand": brand,
        "name": product["title"],
        "price_current": min(prices) if prices else None,
        "price_original": min(compare_prices) if compare_prices else None,
        "colors": extract_colors(product),
        "image_url": images[0]["src"] if images else None,
        "product_url": f"{base_url}/products/{product['handle']}",
    }


def scrape_shopify_store(base_url: str, brand: str, output_path: Path) -> None:
    all_products: list[dict] = []
    page = 1
    while True:
        products = fetch_page(base_url, page)
        if not products:
            break
        print(f"Page {page}: {len(products)} products")
        all_products.extend(parse_product(p, base_url, brand) for p in products)
        page += 1
        time.sleep(REQUEST_DELAY_SECONDS)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_products[0].keys()) if all_products else [])
        writer.writeheader()
        writer.writerows(all_products)

    print(f"\nSaved {len(all_products)} products to {output_path}")

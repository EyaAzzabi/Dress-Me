"""Scraper for ha.com.tn (Hamadi Abid), one of the Tunisian brands named in the
architecture deck's "Catalogue de mode tunisien" data source (docs/).

Legitimacy check done before writing this (see conversation): robots.txt explicitly
allows general crawling (`User-agent: * / Allow: /`), only account/cart/checkout pages
are disallowed. This scraper only visits public catalogue pages.

The site is a client-rendered SPA (Vue) — raw HTML has no product data, so this uses
Playwright to render pages like a real browser would, rather than calling the site's
authenticated `/api/` directly (which correctly returns 401 for unauthenticated
requests — not something to bypass).

Strategy: hit subcategory listing pages (e.g. /catalogue/femme/t-shirts/t-shirt-fantaisie-mc)
from the sitemap, each of which renders several product cards at once — far fewer
page loads than visiting each of the ~1095 individual product pages.

Usage: python scrape_hamadi_abid.py
Output: ml/data/raw/tunisian_catalog/hamadi_abid.csv
"""

import csv
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import httpx
from playwright.sync_api import sync_playwright

BASE_URL = "https://ha.com.tn"
SITEMAP_URL = "https://ha.com.tn/sitemap.xml"
USER_AGENT = "Mozilla/5.0 (compatible; DressMe-research-bot/1.0; +educational project)"
REQUEST_DELAY_SECONDS = 2.0  # politeness delay between page loads

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw" / "tunisian_catalog"
OUTPUT_PATH = RAW_DIR / "hamadi_abid.csv"
SITEMAP_CACHE = RAW_DIR / "hamadi_abid_sitemap.xml"

# Optional per-section cap, e.g. {"femme": 10}. Leave empty ({}) for full coverage —
# every subcategory across every section/age group in the sitemap.
SECTION_SAMPLE_SIZES: dict[str, int] = {}


def load_subcategory_urls() -> list[str]:
    if not SITEMAP_CACHE.exists():
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        resp = httpx.get(SITEMAP_URL, headers={"User-Agent": USER_AGENT}, timeout=15.0)
        resp.raise_for_status()
        SITEMAP_CACHE.write_text(resp.text, encoding="utf-8")

    urls = re.findall(r"<loc>(https://ha\.com\.tn/catalogue/[^<]*)</loc>", SITEMAP_CACHE.read_text(encoding="utf-8"))
    subcat_urls = [u for u in urls if len(u.split("/")) == 7]  # depth-7 = subcategory listing pages

    if not SECTION_SAMPLE_SIZES:
        return subcat_urls

    sampled: list[str] = []
    for section, cap in SECTION_SAMPLE_SIZES.items():
        section_urls = [u for u in subcat_urls if f"/catalogue/{section}/" in u]
        sampled.extend(section_urls[:cap])
    return sampled


def parse_category_path(product_url: str) -> tuple[str, str, str]:
    # e.g. /catalogue/femme/jeans/pantalon/0039585-article-pantalon-coupe-mom-fit
    parts = product_url.strip("/").split("/")
    # parts: ["catalogue", section, category, subcategory, product-slug]
    section = parts[1] if len(parts) > 1 else ""
    category = parts[2] if len(parts) > 2 else ""
    subcategory = parts[3] if len(parts) > 3 else ""
    return section, category, subcategory


def scrape_page(page, url: str) -> list[dict]:
    page.goto(url, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(1000)

    products = []
    tiles = page.query_selector_all("div.cardInner")
    for tile_inner in tiles:
        tile = tile_inner.evaluate_handle("el => el.parentElement.parentElement").as_element()
        if tile is None:
            continue

        link_el = tile_inner.query_selector("a")
        img_el = tile_inner.query_selector("img.product-image")
        title_el = tile.query_selector(".titleClass")
        price_el = tile.query_selector("div[class*='price']:not(.priceCard)")
        color_els = tile.query_selector_all(".colorSquare")

        if not (link_el and title_el):
            continue

        product_url = link_el.get_attribute("href") or ""
        section, category, subcategory = parse_category_path(product_url)

        products.append(
            {
                "brand": "Hamadi Abid",
                "section": section,
                "category": category,
                "subcategory": subcategory,
                "name": title_el.inner_text().strip(),
                "price": price_el.inner_text().strip() if price_el else None,
                "colors": ";".join(c.get_attribute("title") or "" for c in color_els),
                "image_url": urljoin(BASE_URL, img_el.get_attribute("src")) if img_el else None,
                "product_url": urljoin(BASE_URL, product_url),
            }
        )
    return products


def main() -> None:
    urls = load_subcategory_urls()
    print(f"Scraping {len(urls)} subcategory pages...")

    all_products: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=USER_AGENT)

        for i, url in enumerate(urls, 1):
            try:
                products = scrape_page(page, url)
                print(f"[{i}/{len(urls)}] {url} -> {len(products)} products")
                all_products.extend(products)
            except Exception as e:
                print(f"[{i}/{len(urls)}] {url} -> FAILED: {e}")
            time.sleep(REQUEST_DELAY_SECONDS)

        browser.close()

    # Dedupe by product_url (subcategory pages can overlap)
    seen = set()
    deduped = []
    for p_ in all_products:
        if p_["product_url"] not in seen:
            seen.add(p_["product_url"])
            deduped.append(p_)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(deduped[0].keys()) if deduped else [])
        writer.writeheader()
        writer.writerows(deduped)

    print(f"\nSaved {len(deduped)} unique products to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

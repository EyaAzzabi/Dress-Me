"""Scraper for barsha.com.tn (BARSHA), one of the Tunisian brands named in the
architecture deck's "Catalogue de mode tunisien" data source (docs/).

Legitimacy check done before writing this (see conversation): robots.txt has no
Disallow directives for general crawlers (it only states a "content signals" policy
for search/ai-input/ai-train use, none of which restrict this). This scraper only
visits public category/product pages.

The site is an Angular SPA — raw HTML has no product data, so this uses Playwright to
render pages like a real browser would (same approach as scrape_hamadi_abid.py).

Structure discovered by exploration (see barsha_explore_menu*.py, kept for reference):
- Top-level sections ("POUR ELLE" / "POUR LUI") route to /fr/categorie/{Femme,Homme},
  which shows a grid of subcategory tiles (div.category-item), not products yet.
- Clicking a subcategory tile navigates to a product listing page like
  /fr/tn/5-chaussures-femme, with product cards (div.card).
- No infinite scroll or working pagination found — each subcategory page's initial
  card count appears to be the full set for that subcategory at this brand.

Usage: python scrape_barsha.py
Output: ml/data/raw/tunisian_catalog/barsha.csv
"""

import csv
import time
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import Page, sync_playwright

BASE_URL = "https://www.barsha.com.tn"
USER_AGENT = "Mozilla/5.0 (compatible; DressMe-research-bot/1.0; +educational project)"
REQUEST_DELAY_SECONDS = 2.0

OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "tunisian_catalog" / "barsha.csv"

TOP_SECTIONS = ["Femme", "Homme"]


def dismiss_overlays(page: Page) -> None:
    page.evaluate(
        """
        document.querySelectorAll('.welcome-popup-backdrop, [class*="popup" i], [class*="modal" i]')
            .forEach(el => el.remove());
        """
    )


def discover_subcategory_urls(page: Page, section: str) -> list[str]:
    page.goto(f"{BASE_URL}/fr/categorie/{section}", wait_until="load", timeout=30000)
    page.wait_for_timeout(3000)
    dismiss_overlays(page)

    n_tiles = len(page.query_selector_all("div.category-item"))
    urls = []
    for i in range(n_tiles):
        page.goto(f"{BASE_URL}/fr/categorie/{section}", wait_until="load", timeout=30000)
        page.wait_for_timeout(2000)
        dismiss_overlays(page)

        tiles = page.query_selector_all("div.category-item")
        if i >= len(tiles):
            continue
        page.evaluate("el => el.click()", tiles[i])
        page.wait_for_timeout(2500)

        if page.url != f"{BASE_URL}/fr/categorie/{section}":
            urls.append(page.url)

    return sorted(set(urls))


def scrape_page(page: Page, url: str) -> list[dict]:
    page.goto(url, wait_until="load", timeout=30000)
    page.wait_for_timeout(2500)
    dismiss_overlays(page)

    products = []
    for card in page.query_selector_all("div.card"):
        link_el = card.query_selector("a.product-link")
        img_el = card.query_selector("img.card-image")
        title_el = card.query_selector(".card-title")
        current_price_el = card.query_selector(".current-price")
        original_price_el = card.query_selector(".original-price")
        color_els = card.query_selector_all(".color-circle")

        if not (link_el and title_el):
            continue

        products.append(
            {
                "brand": "Barsha",
                "source_url": url,
                "name": title_el.inner_text().strip(),
                "price_current": current_price_el.inner_text().strip() if current_price_el else None,
                "price_original": original_price_el.inner_text().strip() if original_price_el else None,
                "colors": ";".join(c.get_attribute("title") or "" for c in color_els),
                "image_url": urljoin(BASE_URL, img_el.get_attribute("src")) if img_el else None,
                "product_url": urljoin(BASE_URL, link_el.get_attribute("href") or ""),
            }
        )
    return products


def main() -> None:
    all_products: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=USER_AGENT)

        subcategory_urls: list[str] = []
        for section in TOP_SECTIONS:
            urls = discover_subcategory_urls(page, section)
            print(f"{section}: {len(urls)} subcategory pages discovered")
            subcategory_urls.extend(urls)
            time.sleep(REQUEST_DELAY_SECONDS)

        subcategory_urls = sorted(set(subcategory_urls))
        print(f"\nScraping {len(subcategory_urls)} subcategory pages total...")

        for i, url in enumerate(subcategory_urls, 1):
            try:
                products = scrape_page(page, url)
                print(f"[{i}/{len(subcategory_urls)}] {url} -> {len(products)} products")
                all_products.extend(products)
            except Exception as e:
                print(f"[{i}/{len(subcategory_urls)}] {url} -> FAILED: {e}")
            time.sleep(REQUEST_DELAY_SECONDS)

        browser.close()

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

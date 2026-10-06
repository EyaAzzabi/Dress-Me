"""Scraper for noonclo.com (Noonclo), a Tunisian fashion brand.

Legitimacy check done before writing this: same Shopify platform/robots.txt as
Chedly Sisters — "Public product, collection, page, blog, policy, cart, and localized
HTML is crawlable", `Allow: /`, only private/transactional paths disallowed.

Usage: python scrape_noonclo.py
Output: ml/data/raw/tunisian_catalog/noonclo.csv
"""

from pathlib import Path

from shopify_common import scrape_shopify_store

BASE_URL = "https://noonclo.com"
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "tunisian_catalog" / "noonclo.csv"

if __name__ == "__main__":
    scrape_shopify_store(BASE_URL, "Noonclo", OUTPUT_PATH)

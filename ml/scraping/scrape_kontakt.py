"""Scraper for kontakt.com.tn (Kontakt), a Tunisian fashion brand explicitly named in
the project's own architecture deck (docs/) as a target data source.

Legitimacy check done before writing this: same Shopify platform/robots.txt as Chedly
Sisters/Noonclo — "Public product, collection, page, blog, policy, cart, and localized
HTML is crawlable", `Allow: /`, only private/transactional paths disallowed.

Usage: python scrape_kontakt.py
Output: ml/data/raw/tunisian_catalog/kontakt.csv
"""

from pathlib import Path

from shopify_common import scrape_shopify_store

BASE_URL = "https://kontakt.com.tn"
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "tunisian_catalog" / "kontakt.csv"

if __name__ == "__main__":
    scrape_shopify_store(BASE_URL, "Kontakt", OUTPUT_PATH)

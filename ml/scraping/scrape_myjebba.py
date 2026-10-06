"""Scraper for myjebba.com (MY JEBBA), a Tunisian brand specializing in traditional
jebbas — adds traditional Tunisian attire to the catalog, distinct from the
contemporary/casual brands scraped so far (Kontakt, Noonclo, Chedly Sisters, ...).

Legitimacy check done before writing this: same Shopify platform/robots.txt as the
other Shopify sources — "Public product, collection, page, blog, policy, cart, and
localized HTML is crawlable", `Allow: /`.

Usage: python scrape_myjebba.py
Output: ml/data/raw/tunisian_catalog/myjebba.csv
"""

from pathlib import Path

from shopify_common import scrape_shopify_store

BASE_URL = "https://myjebba.com"
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "tunisian_catalog" / "myjebba.csv"

if __name__ == "__main__":
    scrape_shopify_store(BASE_URL, "MY JEBBA", OUTPUT_PATH)

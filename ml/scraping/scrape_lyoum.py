"""Scraper for lyoum.co (LYOUM), a Tunisian fashion brand explicitly named in the
project's own architecture deck (docs/) as a target data source.

Note: lyoum.tn (the local Tunisian site) is PrestaShop, not Shopify, and has no public
products.json. lyoum.co (the international storefront, same brand) is Shopify and is
what this scraper targets instead.

Legitimacy check done before writing this: same Shopify platform/robots.txt as Chedly
Sisters/Noonclo/Kontakt.

Usage: python scrape_lyoum.py
Output: ml/data/raw/tunisian_catalog/lyoum.csv
"""

from pathlib import Path

from shopify_common import scrape_shopify_store

BASE_URL = "https://lyoum.co"
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "tunisian_catalog" / "lyoum.csv"

if __name__ == "__main__":
    scrape_shopify_store(BASE_URL, "Lyoum", OUTPUT_PATH)

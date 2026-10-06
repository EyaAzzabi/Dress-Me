"""Scraper for rooh-clothing.com (Rooh Clothing), a Tunisian fashion brand explicitly
named in the project's own architecture deck (docs/) as a target data source.

Legitimacy check done before writing this: same Shopify platform/robots.txt as Chedly
Sisters/Noonclo/Kontakt.

Usage: python scrape_rooh_clothing.py
Output: ml/data/raw/tunisian_catalog/rooh_clothing.csv
"""

from pathlib import Path

from shopify_common import scrape_shopify_store

BASE_URL = "https://www.rooh-clothing.com"
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "tunisian_catalog" / "rooh_clothing.csv"

if __name__ == "__main__":
    scrape_shopify_store(BASE_URL, "Rooh Clothing", OUTPUT_PATH)

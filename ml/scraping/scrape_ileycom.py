"""Scraper for ileycom.tn (Ileycom), a Tunisian artisan marketplace (jebbas plus a
broader range of handmade goods — scarves, accessories, crochet items). Largest
Tunisian source found so far (~4,744 products).

Legitimacy check done before writing this: same Shopify platform/robots.txt as the
other Shopify sources.

Usage: python scrape_ileycom.py
Output: ml/data/raw/tunisian_catalog/ileycom.csv
"""

from pathlib import Path

from shopify_common import scrape_shopify_store

BASE_URL = "https://ileycom.tn"
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "tunisian_catalog" / "ileycom.csv"

if __name__ == "__main__":
    scrape_shopify_store(BASE_URL, "Ileycom", OUTPUT_PATH)

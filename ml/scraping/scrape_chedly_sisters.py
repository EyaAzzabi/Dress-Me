"""Scraper for chedlysisters.com (Chedly Sisters), a Tunisian fashion brand.

Legitimacy check done before writing this (see conversation): robots.txt explicitly
states "Public product, collection, page, blog, policy, cart, and localized HTML is
crawlable" with `Allow: /`, only private/transactional paths disallowed (admin, cart,
checkout, account, orders) — this scraper only touches the public product catalog.

Category isn't given directly (product_type is generic Shopify plumbing, not a garment
category) — category is derived downstream from the English product title via
ml/src/preprocessing.py's map_chedly_sisters() (keyword matching on the title).

Usage: python scrape_chedly_sisters.py
Output: ml/data/raw/tunisian_catalog/chedly_sisters.csv
"""

from pathlib import Path

from shopify_common import scrape_shopify_store

BASE_URL = "https://chedlysisters.com"
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "tunisian_catalog" / "chedly_sisters.csv"

if __name__ == "__main__":
    scrape_shopify_store(BASE_URL, "Chedly Sisters", OUTPUT_PATH)

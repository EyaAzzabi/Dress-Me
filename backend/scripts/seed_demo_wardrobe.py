"""Fills a demo account's wardrobe with real Tunisian catalog products, through the
real API (Vision Agent included) — handy to demo the Purchase / Recommendation
agents without photographing a whole wardrobe.

Usage (from backend/, with the API running):
    python -m scripts.seed_demo_wardrobe --email demo@dressme.tn --password Dressme2026!
"""

import argparse

import httpx
import pandas as pd

from app.services.ecommerce import CATALOG_PATH

PER_CATEGORY = {"haut": 4, "bas": 3, "chaussures": 2, "sac": 1, "veste": 1}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000/api/v1")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    with httpx.Client(base_url=args.api, timeout=120.0) as client:
        credentials = {"email": args.email, "password": args.password}
        client.post("/auth/register", json=credentials)  # 400 if it already exists — fine
        token = client.post("/auth/login", json=credentials).raise_for_status().json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"

        catalog = pd.read_parquet(CATALOG_PATH)
        for category, count in PER_CATEGORY.items():
            pool = catalog[catalog["dressme_category"] == category].sample(frac=1, random_state=args.seed)
            added = 0
            for url in pool["image_location"].dropna():
                if added == count:
                    break
                response = client.post("/wardrobe/", json={"image_url": url})
                if response.status_code == 201 and response.json()["category"] == category:
                    added += 1
                    print(f"+ {category:<11} {url}")
                elif response.status_code == 201:
                    client.delete(f"/wardrobe/{response.json()['id']}")  # classified differently — skip it


if __name__ == "__main__":
    main()

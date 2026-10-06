"""Downloads a metadata sample of the public Marqo/polyvore dataset (Hugging Face) via
the datasets-server rows API — no `datasets` library / full parquet download needed for
this data-understanding pass, and no gating (unlike mvasil/polyvore-outfits on HF, or
the Kaggle mirrors, which need an account/token).

Fields: image (signed URL, expires — not for permanent storage), category, text,
item_ID (encodes "{outfit_id}_{position_in_outfit}" — the compatibility signal).

Usage: python download_polyvore_sample.py [n_rows]
Output: ml/data/raw/polyvore_sample.csv
"""

import csv
import sys
import time
from pathlib import Path

import httpx

DATASET = "Marqo/polyvore"
PAGE_SIZE = 100
N_ROWS = int(sys.argv[1]) if len(sys.argv) > 1 else 5000

OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "polyvore_sample.csv"


def fetch_page(offset: int, max_retries: int = 5) -> list[dict]:
    for attempt in range(max_retries):
        resp = httpx.get(
            "https://datasets-server.huggingface.co/rows",
            params={"dataset": DATASET, "config": "default", "split": "data", "offset": offset, "length": PAGE_SIZE},
            timeout=30.0,
        )
        if resp.status_code == 429:
            wait = 2 ** attempt * 2  # 2, 4, 8, 16, 32s
            print(f"  rate limited, waiting {wait}s...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()["rows"]
    raise RuntimeError(f"Gave up after {max_retries} retries at offset {offset}")


def save(rows: list[dict]) -> None:
    if not rows:
        return
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nSaved {len(rows)} rows ({len(set(r['outfit_id'] for r in rows))} distinct outfits) to {OUTPUT_PATH}")


def main() -> None:
    rows = []
    offset = 0
    try:
        while offset < N_ROWS:
            page = fetch_page(offset)
            if not page:
                break
            for r in page:
                row = r["row"]
                outfit_id, _, position = row["item_ID"].partition("_")
                rows.append(
                    {
                        "outfit_id": outfit_id,
                        "position": position,
                        "category": row["category"],
                        "text": row["text"],
                        "image_url": row["image"]["src"],
                    }
                )
            offset += PAGE_SIZE
            print(f"Fetched {len(rows)}/{N_ROWS} rows...")
            time.sleep(1.0)
    finally:
        save(rows)  # always persist whatever was fetched, even on error/interrupt


if __name__ == "__main__":
    main()

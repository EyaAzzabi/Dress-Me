"""Downloads local copies of every Tunisian-source product image referenced in the
unified catalog (ml/src/catalog.py). Previously only Hamadi Abid + Barsha had local
images (pulled for the FashionCLIP test); this fills in Chedly Sisters, Noonclo,
Kontakt, Lyoum, Rooh Clothing, MY JEBBA, Ileycom too.

Images are static CDN files (not page scrapes) — downloaded concurrently since fetching
a brand's own product image via its public CDN is normal, expected traffic (identical to
a shopper's browser loading the same page), unlike the page-scraping steps earlier which
used a polite per-page delay.

Usage: python download_tunisian_images.py
Output: ml/data/raw/tunisian_images/<item_key>.jpg
"""

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import catalog  # noqa: E402

IMAGES_DIR = ROOT / "data" / "raw" / "tunisian_images"
USER_AGENT = "Mozilla/5.0 (compatible; DressMe-research-bot/1.0; +educational project)"
MAX_WORKERS = 12  # these are small hosting plans; high concurrency showed no throughput
                   # gain over a plain sequential run (~300 downloads/30min either way),
                   # just more connections held open per slow host
TUNISIAN_SOURCES = {
    "hamadi_abid", "barsha", "chedly_sisters", "noonclo", "kontakt",
    "lyoum", "rooh_clothing", "myjebba", "ileycom",
}


def download_one(item_key: str, url: str) -> tuple[str, bool, str]:
    dest = IMAGES_DIR / f"{item_key}.jpg"
    if dest.exists():
        return item_key, True, "already local"
    try:
        resp = httpx.get(url, timeout=30.0, follow_redirects=True, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        return item_key, True, "downloaded"
    except Exception as e:  # noqa: BLE001
        return item_key, False, str(e)


def main() -> None:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    df = catalog.build_unified_catalog()
    df = df[df["source"].isin(TUNISIAN_SOURCES) & df["image_location"].notna()]
    print(f"{len(df)} Tunisian items with an image URL to check/download")

    ok, failed = 0, 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(download_one, row["item_key"], row["image_location"]): row["item_key"]
            for _, row in df.iterrows()
        }
        for i, future in enumerate(as_completed(futures), 1):
            item_key, success, msg = future.result()
            if success:
                ok += 1
            else:
                failed += 1
                print(f"  FAILED {item_key}: {msg}")
            if i % 500 == 0:
                print(f"[{i}/{len(df)}] ok={ok} failed={failed}")

    print(f"\nDone: {ok} ok ({len(list(IMAGES_DIR.glob('*.jpg')))} files on disk), {failed} failed")


if __name__ == "__main__":
    main()

"""Loads the official Polyvore Outfits dataset (Vasileva et al. 2018), refactored and
re-hosted on Hugging Face by owj0421 across two companion repos:

- `owj0421/polyvore-outfits` (outfit structure: which items go together) ->
  ml/data/raw/polyvore_official/{train,valid,test}.json (nondisjoint_default split)
- `owj0421/polyvore` (item metadata + embedded images) ->
  ml/data/raw/polyvore_official/data-0000X-of-00005.parquet (6 shards, ~2.1GB)

Both downloaded via ml/scraping/download_polyvore_official.sh. Replaces the partial
Marqo/polyvore sample (2,900 items / 596 outfits) with the full dataset (365,054
item-rows across 68,306 outfits).

Images are embedded as bytes inside the parquet shards, not re-extracted to individual
files eagerly (365k images would add several more GB on disk for marginal benefit before
any of them are actually needed for training). `catalog.load_polyvore_official()` sets
`image_is_local=False` and `image_location` to an `item_id`; use `extract_image_bytes()`
here to materialize any specific item's image on demand (e.g. from a training notebook).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
from pyarrow.lib import ArrowInvalid

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "polyvore_official"
SHARD_PATHS = sorted(RAW_DIR.glob("data-*-of-*.parquet"))
ITEM_INDEX_PATH = ROOT / "data" / "processed" / "polyvore_item_metadata.parquet"
OUTFIT_SPLITS = ["train", "valid", "test"]
METADATA_COLUMNS = ["item_id", "title", "url_name", "category"]


def build_item_metadata_index(force: bool = False) -> pd.DataFrame:
    """Reads item_id/title/url_name/category from all shards (columns pruned — the
    embedded `image` column, by far the biggest, is never loaded here) and caches the
    result plus a `shard` column so extract_image_bytes() can find each item fast.
    """
    if ITEM_INDEX_PATH.exists() and not force:
        return pd.read_parquet(ITEM_INDEX_PATH)

    parts = []
    for shard_path in SHARD_PATHS:
        try:
            table = pq.read_table(shard_path, columns=METADATA_COLUMNS)
        except ArrowInvalid:
            # Shard is still being downloaded (curl writes in place, -C - resume) —
            # its footer isn't there yet. Skip it this run; it'll be picked up once done.
            continue
        df = table.to_pandas()
        df["shard"] = shard_path.name
        parts.append(df)
    if not parts:
        return pd.DataFrame(columns=[*METADATA_COLUMNS, "shard"])

    index = pd.concat(parts, ignore_index=True)
    if len(parts) == len(SHARD_PATHS):
        # Only persist the cache once every shard was readable — otherwise a later run
        # (once downloads finish) would keep reusing a stale, partial index.
        ITEM_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        index.to_parquet(ITEM_INDEX_PATH)
    return index


def load_outfit_structure() -> pd.DataFrame:
    """Flattens {train,valid,test}.json (nondisjoint_default) into one
    (outfit_split, set_id, item_id, position) row per outfit item."""
    rows = []
    for split in OUTFIT_SPLITS:
        path = RAW_DIR / f"{split}.json"
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            outfits = json.load(f)
        for outfit in outfits:
            set_id = outfit["set_id"]
            for item in outfit["items"]:
                rows.append({
                    "outfit_split": split,
                    "set_id": set_id,
                    "item_id": item["item_id"],
                    "position": item["index"],
                })
    return pd.DataFrame(rows, columns=["outfit_split", "set_id", "item_id", "position"])


def extract_image_bytes(item_id: str) -> bytes | None:
    """Pulls one item's embedded image out of whichever shard holds it. Builds/reuses
    the cached index to find the shard, then reads only the matching row."""
    return extract_image_bytes_batch([item_id]).get(str(item_id))


def extract_image_bytes_batch(item_ids: list[str]) -> dict[str, bytes]:
    """Same as extract_image_bytes but for many items at once — groups by shard so
    each shard's (large) image column is read once total, not once per item. Use this
    whenever pulling more than a handful of images (e.g. ml/notebooks/09_*)."""
    index = build_item_metadata_index()
    wanted = {str(i) for i in item_ids}
    relevant = index[index["item_id"].isin(wanted)]

    images: dict[str, bytes] = {}
    for shard_name, group in relevant.groupby("shard"):
        table = pq.read_table(RAW_DIR / shard_name, columns=["item_id", "image"])
        df = table.to_pandas()
        df = df[df["item_id"].isin(set(group["item_id"]))]
        for _, row in df.iterrows():
            image_field = row["image"]
            images[row["item_id"]] = (
                image_field["bytes"] if isinstance(image_field, dict) else image_field
            )
    return images

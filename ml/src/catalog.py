"""Builds one unified DressMe catalog table from all 11 collected sources.

Each source has a different native schema (see ml/data/DATA_DICTIONARY.md); this module
normalizes all of them into one shared schema using ml/src/preprocessing.py's taxonomy
mapping, so the Vision/Purchase agents can query one table instead of eleven CSVs.

Unified schema:
    source, item_key, name, dressme_category, color_family, colors_raw, price,
    season, style, brand, material, image_location, image_is_local, split

`split` (train/val/test/exclu) is a stratified split by `dressme_category` (see
preprocessing.stratified_split, ported from the team's own notebook) — classes with
fewer than MIN_SPLIT_CLASS_COUNT examples are excluded ("exclu") rather than forced into
a split too small to be meaningful.

`material` is best-effort text extraction from the product name/title (see
preprocessing.map_material) — no source has a dedicated material field, and unlike
`pattern` it isn't reliably inferable from a photo via zero-shot CLIP, so coverage is
necessarily partial (NaN for most items). Not a bug — see ml/data/DATA_DICTIONARY.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src import preprocessing  # noqa: E402
RAW = ROOT / "data" / "raw"

SCHEMA_COLUMNS = [
    "source", "item_key", "name", "dressme_category", "color_family", "colors_raw",
    "price", "season", "style", "brand", "material", "image_location", "image_is_local",
    "split",
]
MIN_SPLIT_CLASS_COUNT = 10


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=SCHEMA_COLUMNS)


def load_fashion_products() -> pd.DataFrame:
    path = RAW / "styles.csv"
    if not path.exists():
        return _empty()
    df = pd.read_csv(path, on_bad_lines="skip")

    local_images = {p.stem for p in (RAW / "images").glob("*.jpg")} if (RAW / "images").exists() else set()
    ids = df["id"].astype(str)

    return pd.DataFrame({
        "source": "fashion_products",
        "item_key": "fp_" + ids,
        "name": df["productDisplayName"],
        "dressme_category": preprocessing.map_fashion_products(df),
        "color_family": df["baseColour"].map(preprocessing.normalize_color),
        "colors_raw": df["baseColour"],
        "price": pd.NA,
        "season": df["season"],
        "style": df["usage"],
        "brand": pd.NA,
        "material": df["productDisplayName"].map(preprocessing.map_material),
        "image_location": "images/" + ids + ".jpg",
        "image_is_local": ids.isin(local_images),
    })


def _primary_color(colors_raw: str) -> str | float:
    if not isinstance(colors_raw, str) or not colors_raw:
        return pd.NA
    return colors_raw.split(";")[0]


def load_hamadi_abid() -> pd.DataFrame:
    path = RAW / "tunisian_catalog" / "hamadi_abid.csv"
    if not path.exists():
        return _empty()
    df = pd.read_csv(path)

    primary_color = df["colors"].map(_primary_color)
    fallback_id = pd.Series(df.index.astype(str), index=df.index)
    return pd.DataFrame({
        "source": "hamadi_abid",
        "item_key": "ha_" + df["product_url"].str.extract(r"/(\d+)-", expand=False).fillna(fallback_id),
        "name": df["name"],
        "dressme_category": preprocessing.map_hamadi_abid(df),
        "color_family": primary_color.map(preprocessing.normalize_color),
        "colors_raw": df["colors"],
        "price": df["price"],
        "season": pd.NA,
        "style": pd.NA,
        "brand": "Hamadi Abid",
        "material": df["name"].map(preprocessing.map_material),
        "image_location": df["image_url"],
        "image_is_local": False,
    })


def load_barsha() -> pd.DataFrame:
    path = RAW / "tunisian_catalog" / "barsha.csv"
    if not path.exists():
        return _empty()
    df = pd.read_csv(path)

    primary_color = df["colors"].map(_primary_color)
    price = df["price_current"].fillna(df["price_original"])
    fallback_id = pd.Series(df.index.astype(str), index=df.index)
    return pd.DataFrame({
        "source": "barsha",
        "item_key": "barsha_" + df["product_url"].str.extract(r"/(\d+)-", expand=False).fillna(fallback_id),
        "name": df["name"],
        "dressme_category": preprocessing.map_barsha(df),
        "color_family": primary_color.map(preprocessing.normalize_color),
        "colors_raw": df["colors"],
        "price": price,
        "season": pd.NA,
        "style": pd.NA,
        "brand": "Barsha",
        "material": df["name"].map(preprocessing.map_material),
        "image_location": df["image_url"],
        "image_is_local": False,
    })


def _load_shopify_source(filename: str, source_key: str, brand: str, map_fn) -> pd.DataFrame:
    """Shared loader for Tunisian Shopify sources (all scraped via
    ml/scraping/shopify_common.py, same raw schema: name, price_current,
    price_original, colors, image_url, product_url).
    """
    path = RAW / "tunisian_catalog" / filename
    if not path.exists():
        return _empty()
    df = pd.read_csv(path)

    primary_color = df["colors"].map(_primary_color)
    price = df["price_current"].fillna(df["price_original"])
    return pd.DataFrame({
        "source": source_key,
        "item_key": f"{source_key}_" + df["product_url"].str.extract(r"/products/([\w-]+)", expand=False),
        "name": df["name"],
        "dressme_category": map_fn(df),
        "color_family": primary_color.map(preprocessing.normalize_color),
        "colors_raw": df["colors"],
        "price": price,
        "season": pd.NA,
        "style": pd.NA,
        "brand": brand,
        "material": df["name"].map(preprocessing.map_material),
        "image_location": df["image_url"],
        "image_is_local": False,
    })


def load_chedly_sisters() -> pd.DataFrame:
    return _load_shopify_source("chedly_sisters.csv", "chedly_sisters", "Chedly Sisters", preprocessing.map_chedly_sisters)


def load_noonclo() -> pd.DataFrame:
    return _load_shopify_source("noonclo.csv", "noonclo", "Noonclo", preprocessing.map_noonclo)


def load_kontakt() -> pd.DataFrame:
    return _load_shopify_source("kontakt.csv", "kontakt", "Kontakt", preprocessing.map_kontakt)


def load_lyoum() -> pd.DataFrame:
    return _load_shopify_source("lyoum.csv", "lyoum", "Lyoum", preprocessing.map_lyoum)


def load_rooh_clothing() -> pd.DataFrame:
    return _load_shopify_source("rooh_clothing.csv", "rooh_clothing", "Rooh Clothing", preprocessing.map_rooh_clothing)


def load_myjebba() -> pd.DataFrame:
    return _load_shopify_source("myjebba.csv", "myjebba", "MY JEBBA", preprocessing.map_myjebba)


def load_ileycom() -> pd.DataFrame:
    return _load_shopify_source("ileycom.csv", "ileycom", "Ileycom", preprocessing.map_ileycom)


def load_polyvore_sample() -> pd.DataFrame:
    """The original partial sample (Marqo/polyvore, 2,900 items / 596 outfits) — kept as
    a fallback for load_polyvore() when the full official dataset isn't downloaded."""
    path = RAW / "polyvore_sample.csv"
    if not path.exists():
        return _empty()
    df = pd.read_csv(path)

    dressme_category = (
        df["category"].astype(str).str.strip().str.lower().map(preprocessing.POLYVORE_CATEGORY_TO_DRESSME)
        .fillna(df["category"].map(preprocessing.map_keywords))
    )
    return pd.DataFrame({
        "source": "polyvore",
        "item_key": "polyvore_" + df["outfit_id"].astype(str) + "_" + df["position"].astype(str),
        "name": df["text"],
        "dressme_category": dressme_category,
        "color_family": pd.NA,
        "colors_raw": pd.NA,
        "price": pd.NA,
        "season": pd.NA,
        "style": pd.NA,
        "brand": pd.NA,
        "material": df["text"].map(preprocessing.map_material),
        "image_location": df["image_url"],
        "image_is_local": False,
    })


def load_polyvore_official() -> pd.DataFrame:
    """Full official Polyvore Outfits dataset (Vasileva et al. 2018), 365,054 item-rows
    across 68,306 outfits — see ml/src/polyvore_official.py. Falls back to the partial
    sample if the official files haven't been downloaded yet (run
    ml/scraping/download_polyvore_official.sh)."""
    from src import polyvore_official

    if not polyvore_official.SHARD_PATHS:
        return load_polyvore_sample()

    outfits = polyvore_official.load_outfit_structure()
    if outfits.empty:
        return load_polyvore_sample()

    metadata = polyvore_official.build_item_metadata_index()
    df = outfits.merge(metadata, on="item_id", how="inner")
    text = preprocessing.polyvore_text(df)

    return pd.DataFrame({
        "source": "polyvore",
        "item_key": "polyvore_" + df["set_id"].astype(str) + "_" + df["position"].astype(str),
        "name": df["title"],
        "dressme_category": preprocessing.map_polyvore(df),
        "color_family": text.map(preprocessing.map_color_from_text),
        "colors_raw": pd.NA,
        "price": pd.NA,
        "season": pd.NA,
        "style": pd.NA,
        "brand": pd.NA,
        "material": text.map(preprocessing.map_material),
        # Images are embedded in the local parquet shards, not materialized as individual
        # files — item_id here is a pointer for polyvore_official.extract_image_bytes(),
        # not a filesystem path.
        "image_location": df["item_id"],
        "image_is_local": False,
    })


def load_polyvore() -> pd.DataFrame:
    return load_polyvore_official()


def build_unified_catalog() -> pd.DataFrame:
    parts = [
        load_fashion_products(), load_hamadi_abid(), load_barsha(),
        load_chedly_sisters(), load_noonclo(), load_kontakt(), load_lyoum(),
        load_rooh_clothing(), load_myjebba(), load_ileycom(), load_polyvore(),
    ]
    catalog = pd.concat([p for p in parts if len(p)], ignore_index=True)
    # Sources mix raw price text ("49,99 TND") and parsed floats (143.4) — normalize to
    # one consistent string type so pyarrow can infer a single column type on write.
    catalog["price"] = catalog["price"].astype("string")

    # Stratified train/val/test split by dressme_category (incl. hors_perimetre — useful
    # for the Vision Agent to also learn to recognize out-of-scope items). No group_col:
    # unlike the team's Kaggle/Clothing-Full splits (grouped by product name / sender_id),
    # we don't have a reliable cross-source duplicate-product identifier, so near-duplicate
    # items (e.g. the same jebba in 5 colorways) could land in different splits. Documented
    # limitation, not hidden — see ml/data/DATA_DICTIONARY.md.
    catalog["split"] = preprocessing.stratified_split(
        catalog, label_col="dressme_category", group_col=None, min_count=MIN_SPLIT_CLASS_COUNT
    )
    return catalog[SCHEMA_COLUMNS]


def main() -> None:
    catalog = build_unified_catalog()
    out_dir = ROOT / "data" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "dressme_catalog.parquet"
    catalog.to_parquet(out_path, index=False)

    print(f"Unified catalog: {len(catalog)} items from {catalog['source'].nunique()} sources")
    print(catalog.groupby("source").size())
    print("\nBy DressMe category:")
    print(pd.crosstab(catalog["dressme_category"], catalog["source"]))
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()

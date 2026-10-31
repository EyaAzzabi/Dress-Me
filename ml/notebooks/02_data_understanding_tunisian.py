# %% [markdown]
# # DressMe — Data Understanding: Tunisian catalog (Hamadi Abid)
#
# Run as a Jupyter/VS Code interactive script (`# %%` cells). Expects
# `ml/scraping/scrape_hamadi_abid.py` to have been run first — see `ml/README.md`.

# %%
import re
from pathlib import Path

import pandas as pd

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "tunisian_catalog" / "hamadi_abid.csv"

# %% [markdown]
# ## 1. Load and describe

# %%
df = pd.read_csv(DATA_PATH)
print(f"{len(df)} products, {df.shape[1]} columns")
df.head()

# %%
df.info()

# %% [markdown]
# ## 2. Missing values and duplicates

# %%
print(df.isna().sum().sort_values(ascending=False))
print(f"\nDuplicate product_url: {df['product_url'].duplicated().sum()}")

# %% [markdown]
# ## 3. Category distribution (section / category / subcategory)
#
# `subcategory` is the closest match to `ClothingItem.category` — check granularity
# against the Kaggle dataset's `articleType` (see `ml/data/DATA_DICTIONARY.md`).

# %%
for column in ["section", "category", "subcategory"]:
    print(f"\n--- {column} ({df[column].nunique()} unique values) ---")
    print(df[column].value_counts())

# %% [markdown]
# ## 4. Price parsing
#
# Prices come as raw strings like "49,99 TND" or, when discounted, both prices on one
# line ("13,99 TND 19,99 TND" = sale price + original price). Parse before treating as
# a number.

# %%
def parse_prices(raw: str) -> tuple[float | None, float | None]:
    if not isinstance(raw, str):
        return None, None
    amounts = [float(m.replace(",", ".")) for m in re.findall(r"[\d,]+(?=\s*TND)", raw)]
    if len(amounts) == 1:
        return amounts[0], None
    if len(amounts) >= 2:
        return amounts[0], amounts[1]  # sale price, original price
    return None, None


df[["price_current", "price_original"]] = df["price"].apply(lambda r: pd.Series(parse_prices(r)))
df["on_sale"] = df["price_original"].notna()

print(f"On sale: {df['on_sale'].sum()} / {len(df)}")
df["price_current"].describe()

# %% [markdown]
# ## 5. Color coverage
#
# `colors` is a `;`-joined list of color names (e.g. "BEIGE;BLACK;BROWN;RED"). This
# dataset gives *all* available colors per product, unlike Kaggle's single `baseColour` —
# richer, but needs picking one strategy: keep as a list (matches `ClothingItem.colors`
# directly) or pick a primary color per product.

# %%
df["n_colors"] = df["colors"].fillna("").apply(lambda c: len(c.split(";")) if c else 0)
print(df["n_colors"].value_counts().sort_index())

all_colors = df["colors"].fillna("").str.split(";").explode()
all_colors = all_colors[all_colors != ""]
print(f"\n{all_colors.nunique()} unique color names across {len(all_colors)} color entries")
print(all_colors.value_counts().head(20))

# %% [markdown]
# ## 6. Image URL reachability (sample check)
#
# Confirms scraped image URLs actually resolve before relying on them downstream.

# %%
import httpx

sample = df.sample(min(10, len(df)), random_state=0)
for url in sample["image_url"]:
    try:
        r = httpx.head(url, timeout=5.0, follow_redirects=True)
        print(r.status_code, url)
    except httpx.HTTPError as e:
        print("ERROR", url, e)

# %% [markdown]
# ## 7. Findings to carry into `DATA_DICTIONARY.md`
#
# - Note how `subcategory` values here should map to the `category` taxonomy chosen
#   for the Kaggle dataset (same field, two different sources — must reconcile).
# - Note the `on_sale` / `price_original` handling decision (keep both? only current
#   price?) for anything that feeds the Purchase Agent's budget reasoning.
# - Note whether to keep all colors per product or pick one primary color, and whether
#   that decision should match how Kaggle's single `baseColour` is used.

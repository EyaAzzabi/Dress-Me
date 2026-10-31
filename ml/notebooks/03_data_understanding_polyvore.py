# %% [markdown]
# # DressMe — Data Understanding: Outfit compatibility (Polyvore)
#
# Run as a Jupyter/VS Code interactive script (`# %%` cells). Expects
# `ml/scraping/download_polyvore_sample.py` to have been run first — see `ml/README.md`.

# %%
from pathlib import Path

import pandas as pd

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "polyvore_sample.csv"

# %% [markdown]
# ## 1. Load and describe

# %%
df = pd.read_csv(DATA_PATH)
print(f"{len(df)} items, {df['outfit_id'].nunique()} distinct outfits")
df.head()

# %% [markdown]
# ## 2. Outfit size distribution
#
# How many items make up a typical outfit? Matters for how the Recommendation Agent
# should sample positive/negative pairs.

# %%
outfit_sizes = df.groupby("outfit_id").size()
print(outfit_sizes.describe())
print(outfit_sizes.value_counts().sort_index().head(15))

# %% [markdown]
# ## 3. Non-fashion contamination
#
# Polyvore is a general mood-board site — some "outfits" are home decor / lifestyle
# collages, not clothing. Flag categories that are clearly not wearable items.

# %%
NON_FASHION_KEYWORDS = [
    "chair", "table", "decor", "toy", "food", "drink", "font", "wallpaper",
    "art", "furniture", "room", "book", "candle", "plant", "phone case",
]

df["is_non_fashion"] = df["category"].str.lower().apply(
    lambda c: any(kw in c for kw in NON_FASHION_KEYWORDS)
)
print(f"Non-fashion items (keyword match): {df['is_non_fashion'].sum()} / {len(df)}")
print("\nTop categories overall:")
print(df["category"].value_counts().head(20))
print("\nCategories flagged as non-fashion:")
print(df.loc[df["is_non_fashion"], "category"].value_counts())

# %% [markdown]
# ## 4. Outfits fully contaminated vs. partially vs. clean
#
# An outfit with even one non-fashion item still has usable fashion items in it —
# only fully non-fashion outfits need dropping entirely.

# %%
contamination = df.groupby("outfit_id")["is_non_fashion"].agg(["sum", "count"])
contamination["fully_non_fashion"] = contamination["sum"] == contamination["count"]
contamination["partially_non_fashion"] = (contamination["sum"] > 0) & ~contamination["fully_non_fashion"]

print(f"Fully non-fashion outfits (drop entirely): {contamination['fully_non_fashion'].sum()}")
print(f"Partially contaminated (drop only flagged items): {contamination['partially_non_fashion'].sum()}")
print(f"Clean outfits: {(~contamination['fully_non_fashion'] & ~contamination['partially_non_fashion']).sum()}")

# %% [markdown]
# ## 5. Findings to carry forward
#
# - `NON_FASHION_KEYWORDS` is a first-pass heuristic — review flagged categories above
#   and refine the list before using this for compatibility training.
# - Outfit size distribution should inform how many negative samples to draw per
#   positive pair when training the Recommendation Agent's compatibility model.
# - This is a partial sample (rate-limited during download, see `ml/README.md`) —
#   re-run `download_polyvore_sample.py` with a higher offset later to extend it.

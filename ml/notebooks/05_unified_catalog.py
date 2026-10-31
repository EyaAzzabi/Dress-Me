# %% [markdown]
# # DressMe — Unified catalog
#
# Merges all 9 collected sources (Fashion Product Images, Hamadi Abid, Barsha,
# Chedly Sisters, Noonclo, Kontakt, Lyoum, Rooh Clothing, Polyvore) into one catalog
# table using `ml/src/catalog.py`, built on top of the taxonomy reconciliation from
# `04_taxonomy_reconciliation.py`.
#
# Run as a Jupyter/VS Code interactive script (`# %%` cells).

# %%
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import catalog  # noqa: E402

# %% [markdown]
# ## 1. Build the catalog

# %%
df = catalog.build_unified_catalog()
print(f"{len(df)} items from {df['source'].nunique()} sources")
df.head()

# %% [markdown]
# ## 2. Coverage per source

# %%
print(df.groupby("source").size())
print("\nLocal images available:")
print(df.groupby("source")["image_is_local"].sum())

# %% [markdown]
# ## 3. DressMe category distribution across the merged catalog

# %%
import pandas as pd

cross_tab = pd.crosstab(df["dressme_category"], df["source"])
print(cross_tab)

# %% [markdown]
# ## 4. Color coverage (where available)

# %%
has_color = df["color_family"].notna()
print(f"{has_color.sum()} / {len(df)} items have a normalized color_family")
print(df.loc[has_color, "color_family"].value_counts())

# %% [markdown]
# ## 5. Save

# %%
out_path = ROOT / "data" / "processed" / "dressme_catalog.parquet"
out_path.parent.mkdir(parents=True, exist_ok=True)
df.to_parquet(out_path, index=False)
print(f"Saved {len(df)} rows to {out_path}")

# %% [markdown]
# ## 6. Findings
#
# - One schema, 9 sources — `source` column keeps provenance for anything that
#   needs it (e.g. only training on real Tunisian photos).
# - `image_is_local` tells you which rows have a usable local file today vs. a remote
#   URL (Tunisian sources) or a sampled-only Kaggle image.
# - `color_family` is only populated for sources with a color field (Kaggle, Tunisian) —
#   Polyvore items need the full parquet download (not just this metadata sample) to
#   get images for color extraction, or stay text-only for now.

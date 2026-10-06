# %% [markdown]
# # DressMe — Data Understanding (S3)
#
# Run this as a Jupyter/VS Code interactive script (`# %%` cells). Expects the
# Fashion Product Images dataset downloaded into `ml/data/raw/` — see `ml/README.md`.

# %%
import sys
from pathlib import Path

import matplotlib
import pandas as pd
from PIL import Image

# Running as a plain script (not inside Jupyter) would otherwise open a blocking
# GUI window on plt.show(). Detect that case and save figures to disk instead.
RUNNING_INTERACTIVELY = hasattr(sys, "ps1") or "ipykernel" in sys.modules
if not RUNNING_INTERACTIVELY:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
STYLES_CSV = DATA_DIR / "styles.csv"
IMAGES_DIR = DATA_DIR / "images"
FIGURES_DIR = Path(__file__).resolve().parents[1] / "reports"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)


def show_or_save(fig, filename: str) -> None:
    if RUNNING_INTERACTIVELY:
        plt.show()
    else:
        fig.savefig(FIGURES_DIR / filename, dpi=120, bbox_inches="tight")
        plt.close(fig)
        print(f"Saved {FIGURES_DIR / filename}")

# %% [markdown]
# ## 1. Load and describe

# %%
df = pd.read_csv(STYLES_CSV, on_bad_lines="skip")
print(f"{len(df)} rows, {df.shape[1]} columns")
df.head()

# %%
df.info()

# %% [markdown]
# ## 2. Missing values and duplicates

# %%
print(df.isna().sum().sort_values(ascending=False))
print(f"\nDuplicate ids: {df['id'].duplicated().sum()}")

# %% [markdown]
# ## 3. Class distributions for fields we map to `ClothingItem`
#
# See `ml/data/DATA_DICTIONARY.md` for the mapping rationale.

# %%
for column in ["articleType", "baseColour", "season", "usage"]:
    print(f"\n--- {column} ({df[column].nunique()} unique values) ---")
    print(df[column].value_counts().head(15))

# %% [markdown]
# ## 4. Long-tail check
#
# Classes with very few samples are candidates to merge or drop before training.

# %%
counts = df["articleType"].value_counts()
rare = counts[counts < 50]
print(f"{len(rare)} articleType classes have fewer than 50 images:")
print(rare)

# %% [markdown]
# ## 5. Sample images per category (sanity check labels look right)

# %%
available_ids = {p.stem for p in IMAGES_DIR.glob("*.jpg")} if IMAGES_DIR.exists() else set()
print(f"{len(available_ids)} images available locally out of {len(df)} rows "
      f"(only a sample was extracted to save disk space — see ml/README.md)")


def show_samples(category_column: str, category_value: str, n: int = 6) -> None:
    candidates = df[(df[category_column] == category_value) & (df["id"].astype(str).isin(available_ids))]
    if candidates.empty:
        print(f"No locally-available images for {category_column} = {category_value}; "
              f"extract more via ml/scraping or re-run download_polyvore_sample.py-style sampling.")
        return
    subset = candidates.sample(min(n, len(candidates)))
    fig, axes = plt.subplots(1, len(subset), figsize=(3 * len(subset), 3))
    if len(subset) == 1:
        axes = [axes]
    for ax, (_, row) in zip(axes, subset.iterrows()):
        image_path = IMAGES_DIR / f"{row['id']}.jpg"
        ax.imshow(Image.open(image_path))
        ax.set_title(row["articleType"], fontsize=8)
        ax.axis("off")
    fig.suptitle(f"{category_column} = {category_value}")
    show_or_save(fig, f"01_sample_{category_column}_{category_value}.png")


show_samples("usage", "Casual")

# %% [markdown]
# ## 6. Findings to carry into `DATA_DICTIONARY.md`
#
# - Note here which `articleType` values you decide to collapse into a single
#   wardrobe `category`.
# - Note which `usage` values you merge for the `style` field.
# - Note the minimum sample count threshold you chose for dropping rare classes.

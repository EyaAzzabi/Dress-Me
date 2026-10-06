# %% [markdown]
# # DressMe — Pattern weak-labeling (FashionCLIP zero-shot)
#
# **No source has a `pattern` field** — not Kaggle, not any Tunisian scrape, not
# Polyvore. This has been a known, undecided gap since the very first data-understanding
# pass. There's no dataset to download our way out of it; the practical fix is a weak
# label from FashionCLIP zero-shot classification, the same mechanism already validated
# (with real, imperfect accuracy — see `06_fashionclip_tunisian.py`) for category.
#
# **This produces model-inferred labels, not ground truth.** Saved as a separate file
# (`ml/data/processed/pattern_weak_labels.csv`), joinable to the catalog by `item_key` —
# never merged silently into the main catalog as if it were a scraped fact.
#
# Run as a Jupyter/VS Code interactive script (`# %%` cells). Requires local images —
# run `ml/scraping/download_tunisian_images.py` first for Tunisian coverage.

# %%
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import catalog, features  # noqa: E402

IMAGES_DIR = ROOT / "data" / "raw" / "tunisian_images"
OUT_PATH = ROOT / "data" / "processed" / "pattern_weak_labels.csv"

# %% [markdown]
# ## 1. Find catalog items with a local image available

# %%
df = catalog.build_unified_catalog()
local_ids = {p.stem for p in IMAGES_DIR.glob("*.jpg")} if IMAGES_DIR.exists() else set()
df = df[df["item_key"].isin(local_ids)].copy()
df["local_path"] = df["item_key"].apply(lambda k: IMAGES_DIR / f"{k}.jpg")
print(f"{len(df)} items with a local image available for pattern labeling")

# %% [markdown]
# ## 2. Load FashionCLIP and embed

# %%
model, processor, device = features.load_fashionclip()
print(f"FashionCLIP loaded on {device}")

vectors, kept_idx = features.embed_images(df["local_path"].tolist(), model, processor, device)
df = df.iloc[kept_idx].reset_index(drop=True)
print(f"{len(vectors)} images embedded")

# %% [markdown]
# ## 3. Zero-shot pattern classification

# %%
labels = list(features.PATTERN_PROMPTS)
prompts = [features.PATTERN_PROMPTS[l] for l in labels]
predicted_idx, probs = features.zero_shot(vectors, prompts, model, processor, device, template="{}")
df["pattern_weak_label"] = [labels[i] for i in predicted_idx]
df["pattern_confidence"] = probs.max(axis=1)

print(df["pattern_weak_label"].value_counts())
print(f"\nMean confidence: {df['pattern_confidence'].mean():.3f}")
print(f"Low-confidence (<0.3) items: {(df['pattern_confidence'] < 0.3).sum()} / {len(df)} "
      f"— treat these as unreliable, not just low-priority")

# %% [markdown]
# ## 4. Save (separate file, not merged into the catalog)

# %%
out = df[["item_key", "source", "dressme_category", "pattern_weak_label", "pattern_confidence"]]
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
out.to_csv(OUT_PATH, index=False)
print(f"Saved {len(out)} weak labels to {OUT_PATH}")

# %% [markdown]
# ## 5. Findings
#
# **Run on the full downloaded Tunisian image set: 8,929 items labeled** (up from an
# initial partial pass of 942 while `download_tunisian_images.py` was still running).
#
# | Pattern | Count |
# |---|---|
# | uni (plain) | 3,520 |
# | brode (embroidered) | 1,860 |
# | geometrique | 1,107 |
# | fleuri (floral) | 887 |
# | rayures (striped) | 573 |
# | imprime_animal | 426 |
# | a_pois (polka dot) | 381 |
# | carreaux (checkered) | 175 |
#
# Mean confidence 0.731 (vs. 0.817 on the smaller 942-item pass — expected, a larger and
# more visually diverse sample pulls the average down slightly). 161/8,929 (1.8%)
# low-confidence (<0.3) predictions — treat those as unreliable, not just low-priority.
#
# - Treat `pattern_confidence` as a filter: low-confidence predictions are closer to
#   noise than signal. No ground truth exists to measure real accuracy against (unlike
#   category, which could be checked against the taxonomy mapping) — this is a best
#   effort, not a validated classifier.
# - If pattern becomes important enough to need real accuracy, the actual fix is manual
#   labeling of a sample, not a bigger model.

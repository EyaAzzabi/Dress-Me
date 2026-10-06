# %% [markdown]
# # DressMe — FashionCLIP sanity check on Tunisian catalog photos
#
# Your teammates already validated FashionCLIP zero-shot classification on Fashion
# Product Images, Clothing Dataset Full, and Polyvore (real F1 scores, see their
# notebook). Nobody has checked whether it generalizes to the Tunisian catalog photos
# (Hamadi Abid + Barsha) specifically — different photography style, different CDN.
# This notebook closes that gap.
#
# Run as a Jupyter/VS Code interactive script (`# %%` cells).

# %%
import sys
import time
from pathlib import Path

import matplotlib
import pandas as pd

RUNNING_INTERACTIVELY = hasattr(sys, "ps1") or "ipykernel" in sys.modules
if not RUNNING_INTERACTIVELY:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import features  # noqa: E402

RAW = ROOT / "data" / "raw"
IMAGES_DIR = RAW / "tunisian_images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
REPORTS = ROOT / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)

# %% [markdown]
# ## 1. Load the Tunisian subset of the unified catalog
#
# Ground truth `dressme_category` already comes from `ml/src/preprocessing.py`'s
# verified taxonomy mapping — no new labeling needed, just reused for evaluation.

# %%
catalog = pd.read_parquet(ROOT / "data" / "processed" / "dressme_catalog.parquet")
tunisian = catalog[catalog["source"].isin(["hamadi_abid", "barsha"])].copy()
tunisian = tunisian[tunisian["dressme_category"].isin(features.DRESSME_CATEGORY_PROMPTS.keys())]
print(f"{len(tunisian)} Tunisian items in-scope for zero-shot evaluation "
      f"(hors_perimetre items excluded — no matching prompt class)")
print(tunisian["dressme_category"].value_counts())

# %% [markdown]
# ## 2. Download images (not yet local — Tunisian sources are remote URLs)

# %%
import httpx


def download_image(url: str, dest: Path) -> bool:
    if dest.exists():
        return True
    try:
        resp = httpx.get(url, timeout=10.0, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 (compatible; DressMe-research-bot/1.0)"})
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  FAILED {url}: {e}")
        return False


tunisian["local_path"] = tunisian["item_key"].apply(lambda k: IMAGES_DIR / f"{k}.jpg")
downloaded = 0
for i, (_, row) in enumerate(tunisian.iterrows(), 1):
    if download_image(row["image_location"], row["local_path"]):
        downloaded += 1
    if i % 100 == 0:
        print(f"[{i}/{len(tunisian)}] downloaded so far: {downloaded}")
    time.sleep(0.1)

tunisian["image_ok"] = tunisian["local_path"].apply(lambda p: p.exists())
print(f"\n{tunisian['image_ok'].sum()} / {len(tunisian)} images available locally")
tunisian = tunisian[tunisian["image_ok"]]

# %% [markdown]
# ## 3. Load FashionCLIP and compute embeddings

# %%
model, processor, device = features.load_fashionclip()
print(f"FashionCLIP loaded on {device}")

vectors, kept_idx = features.embed_images(tunisian["local_path"].tolist(), model, processor, device)
tunisian = tunisian.iloc[kept_idx].reset_index(drop=True)
print(f"{len(vectors)} images embedded ({vectors.shape[1]}-dim)")

# %% [markdown]
# ## 4. Zero-shot classification against the 7 DressMe categories

# %%
from sklearn.metrics import classification_report, confusion_matrix

labels = list(features.DRESSME_CATEGORY_PROMPTS)
prompts = [features.DRESSME_CATEGORY_PROMPTS[l] for l in labels]
predicted_idx, probs = features.zero_shot(vectors, prompts, model, processor, device, template="{}")
tunisian["predicted_category"] = [labels[i] for i in predicted_idx]

report = classification_report(tunisian["dressme_category"], tunisian["predicted_category"],
                               labels=labels, zero_division=0)
print(report)

# %% [markdown]
# ## 5. Confusion matrix

# %%
cm = confusion_matrix(tunisian["dressme_category"], tunisian["predicted_category"], labels=labels)
fig, ax = plt.subplots(figsize=(7, 6))
im = ax.imshow(cm, cmap="Blues")
ax.set_xticks(range(len(labels)), labels, rotation=45, ha="right")
ax.set_yticks(range(len(labels)), labels)
ax.set_xlabel("Predicted (FashionCLIP zero-shot)")
ax.set_ylabel("Actual (from taxonomy mapping)")
ax.set_title("FashionCLIP zero-shot on Tunisian catalog photos")
for i in range(len(labels)):
    for j in range(len(labels)):
        ax.text(j, i, cm[i, j], ha="center", va="center",
               color="white" if cm[i, j] > cm.max() / 2 else "black", fontsize=8)
fig.tight_layout()
if RUNNING_INTERACTIVELY:
    plt.show()
else:
    fig.savefig(REPORTS / "06_fashionclip_tunisian_confusion.png", dpi=120)
    plt.close(fig)
    print(f"Saved {REPORTS / '06_fashionclip_tunisian_confusion.png'}")

# %% [markdown]
# ## 6. Comparison to the team's Kaggle/Clothing Full results
#
# Their F1 (from notebook 3): haut 0.91, bas 0.96, robe 0.73, veste 0.80,
# chaussures 0.98, sac 0.87. Compare the printed classification_report above against
# these — if Tunisian F1 is notably lower on the same categories, that's a real
# domain-gap finding (different photography style/background than Kaggle's studio
# shots), not a bug.

# %% [markdown]
# ## 7. Findings
#
# Fill in after running:
# - Overall accuracy vs. the team's Kaggle/Clothing Full numbers
# - Which categories transfer well vs. poorly to Tunisian photos
# - Main confusions (off-diagonal cells in the matrix)

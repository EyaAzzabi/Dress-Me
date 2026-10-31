# %% [markdown]
# # DressMe — Category classifier: linear probe on frozen FashionCLIP embeddings
#
# `06_fashionclip_tunisian.py` found real weak spots in FashionCLIP's **zero-shot**
# category classification on Tunisian photos: veste (F1 0.17), robe (F1 0.30). Full
# fine-tuning of CLIP's vision encoder would be the textbook fix, but needs a GPU to be
# practical — this environment is CPU-only. A **linear probe** (train a small classifier
# on top of FashionCLIP's frozen embeddings) is the CPU-feasible middle ground: FashionCLIP
# still does the hard visual work, we only train a lightweight head on top, using the
# labels we already trust (the taxonomy mapping, not zero-shot guesses).
#
# This is not "fine-tuning" in the full sense (the vision encoder itself never updates),
# but it is a genuine trained classifier evaluated on a held-out split, not just a
# zero-shot prompt — and it directly tests whether the veste/robe weakness is fixable
# with supervision instead of being a hard embedding-quality ceiling.
#
# Run as a Jupyter/VS Code interactive script (`# %%` cells). Requires local images and
# the `split` column — run `download_tunisian_images.py` and rebuild `catalog.py` first.

# %%
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import catalog, features, preprocessing  # noqa: E402

IMAGES_DIR = ROOT / "data" / "raw" / "tunisian_images"
EMB_PATH = ROOT / "data" / "processed" / "tunisian_embeddings.npz"

# %% [markdown]
# ## 1. Tunisian, in-scope, locally-available items with their train/val/test split

# %%
TUNISIAN_SOURCES = {
    "hamadi_abid", "barsha", "chedly_sisters", "noonclo", "kontakt",
    "lyoum", "rooh_clothing", "myjebba", "ileycom",
}
df = catalog.build_unified_catalog()
# Includes hors_perimetre as its own class (not just the 7 DressMe categories) — without
# it, the classifier would be forced to always guess a real category even for a photo
# that isn't clothing at all (haircare products, etc.), which is worse than abstaining.
# It's also the single largest locally-available Tunisian class (4,296 items).
df = df[df["source"].isin(TUNISIAN_SOURCES) & (
    df["dressme_category"].isin(preprocessing.DRESSME_CATEGORIES)
    | (df["dressme_category"] == preprocessing.OUT_OF_SCOPE)
)]

local_ids = {p.stem for p in IMAGES_DIR.glob("*.jpg")} if IMAGES_DIR.exists() else set()
df = df[df["item_key"].isin(local_ids)].copy()
df["local_path"] = df["item_key"].apply(lambda k: IMAGES_DIR / f"{k}.jpg")
print(f"{len(df)} labeled, locally-available Tunisian items")
print(df.groupby(["split", "dressme_category"]).size().unstack(fill_value=0))

# %% [markdown]
# ## 2. Embed with FashionCLIP (cached — re-running reuses saved embeddings)

# %%
if EMB_PATH.exists():
    cached = np.load(EMB_PATH, allow_pickle=False)
    vectors, cached_keys = cached["vectors"], cached["ids"].tolist()
    key_to_vec = dict(zip(cached_keys, vectors))
    have = df["item_key"].isin(key_to_vec)
    print(f"{have.sum()} / {len(df)} already embedded (cached)")
else:
    key_to_vec = {}
    have = pd.Series(False, index=df.index)

to_embed = df[~have]
if len(to_embed):
    model, processor, device = features.load_fashionclip()
    new_vectors, kept_idx = features.embed_images(to_embed["local_path"].tolist(), model, processor, device)
    for key, vec in zip(to_embed.iloc[kept_idx]["item_key"], new_vectors):
        key_to_vec[key] = vec
    features.save_embeddings(EMB_PATH, np.array(list(key_to_vec.values())), list(key_to_vec.keys()))

df = df[df["item_key"].isin(key_to_vec)].reset_index(drop=True)
X = np.stack([key_to_vec[k] for k in df["item_key"]])
print(f"{len(df)} items with embeddings, matrix shape {X.shape}")

# %% [markdown]
# ## 3. Train a linear classifier on the train split, evaluate on test

# %%
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix

train_mask = df["split"] == "train"
test_mask = df["split"] == "test"
print(f"train: {train_mask.sum()}, test: {test_mask.sum()}")

clf = LogisticRegression(max_iter=2000, class_weight="balanced")
clf.fit(X[train_mask], df.loc[train_mask, "dressme_category"])

predicted = clf.predict(X[test_mask])
actual = df.loc[test_mask, "dressme_category"]
print(classification_report(actual, predicted, zero_division=0))

# %% [markdown]
# ## 4. Compare veste/robe specifically against the zero-shot baseline
#
# Zero-shot baseline (from `06_fashionclip_tunisian.py`): veste F1 0.17, robe F1 0.30.

# %%
report = classification_report(actual, predicted, zero_division=0, output_dict=True)
for cat in ["veste", "robe"]:
    if cat in report:
        print(f"{cat}: linear-probe F1 = {report[cat]['f1-score']:.2f} "
              f"(zero-shot was {'0.17' if cat == 'veste' else '0.30'})")

# %% [markdown]
# ## 5. Save the production classifier
#
# The train/test split above is for honest evaluation (the numbers reported are real
# generalization performance, not overfit to everything we have). For the artifact the
# Vision Agent actually loads, retrain on **all** available labeled Tunisian embeddings
# (train+val+test) — standard practice once the held-out metrics have validated the
# approach, since more training data only helps a linear head with no held-out set left
# to protect.

# %%
import joblib

CLASSIFIER_PATH = ROOT / "data" / "processed" / "category_classifier.joblib"

production_clf = LogisticRegression(max_iter=2000, class_weight="balanced")
production_clf.fit(X, df["dressme_category"])
joblib.dump(production_clf, CLASSIFIER_PATH)
print(f"Saved production classifier ({len(df)} items, classes={list(production_clf.classes_)}) to {CLASSIFIER_PATH}")

# %% [markdown]
# ## 6. Findings
#
# **Result, run on the full downloaded Tunisian image set (4,636 in-scope, locally
# available items — up from the 761 used in `06_fashionclip_tunisian.py`; 7 fewer than
# an earlier pass after `grenouillere`/`tablier-*` were reclassified to `hors_perimetre`,
# see `DATA_DICTIONARY.md`):**
#
# | Category | Zero-shot F1 (06) | Linear-probe F1 (08) |
# |---|---|---|
# | veste | 0.17 | **0.69** |
# | robe | 0.30 | **0.71** |
# | accessoire | 0.62 | 0.94 |
# | bas | 0.67 | 0.71 |
# | chaussures | 1.00 | 0.90 |
# | haut | 0.52 | 0.83 |
# | sac | 0.60 | 0.89 |
#
# Macro F1 0.81, accuracy 81% (up from 0.55 macro F1 / 62% zero-shot).
#
# **Supervision fixed the veste/robe weak spots — they were not a hard embedding-quality
# ceiling.** FashionCLIP's frozen embeddings already separate these categories reasonably
# well visually; zero-shot's failure was a *prompting* problem (matching an embedding to
# "a jacket"/"a dress" text), not an *embedding* problem. A small trained head on top of
# the same frozen features recovers most of the gap, at zero GPU cost.
#
# veste and robe remain the weakest categories (~0.7) — plausibly the residual
# taxonomy-mapping ambiguity flagged in `06` and acted on partially in `DATA_DICTIONARY.md`
# (suits, kimono, coordinated sets still mapped to veste/robe for taxonomy consistency but
# visually atypical) rather than a model limitation at this point. Full fine-tuning of the
# vision encoder (GPU-dependent) is no longer the obvious next step — reviewing those
# remaining ambiguous ground-truth labels would likely pay off more.
#
# ## 7. hors_perimetre as an 8th class — a real tradeoff, kept anyway
#
# The production artifact (saved above) is actually trained on **8 classes**, not 7 — it
# includes `hors_perimetre` (4,296 locally-available items, the single largest class).
# Without it, the Vision Agent would be forced to always guess a real garment category
# even for a photo that isn't clothing at all (haircare bottles, jewelry boxes, perfume),
# which is worse for a wardrobe app than being able to say "this isn't clothing."
#
# This costs accuracy elsewhere: macro F1 0.81 → 0.74, accuracy 81% → 79%, and
# specifically veste 0.69 → 0.60 and robe 0.71 → 0.64 (hors_perimetre is a visually
# heterogeneous "everything else" bucket that overlaps more with the already-ambiguous
# categories). hors_perimetre itself: 0.86 F1, 97% precision / 77% recall — when it says
# "not clothing" it's almost always right, but it misses ~1 in 4 actual out-of-scope
# items (small-sample spot check: 5/8). This is the artifact actually shipped to
# `backend/app/ml/artifacts/category_classifier.joblib` — see
# `backend/app/agents/vision_agent.py`.

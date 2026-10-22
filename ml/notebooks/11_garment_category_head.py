# %% [markdown]
# # DressMe — Garment category head: SVM on frozen FashionCLIP embeddings, garments only
#
# `08_category_classifier.py` trains ONE 8-class linear probe that also has to say
# "hors_perimetre" (non-clothing catalog products). Two different jobs in one model.
# This script trains the garment decision alone — 7 classes, garments only — with an RBF
# SVM, which beat every logistic-regression C / class-weight setting we tried on the
# validation split.
#
# Honest size of the gain (13_vision_agent_evaluation.py, held-out test, garments the
# "hors_perimetre" gate keeps): accuracy 85.2% -> 87.0% (+1.8 points, paired-bootstrap 95% CI
# [-0.4, +4.2]) and macro-F1 over the 7 garment labels 0.851 -> 0.871. Clear on robes (F1
# 0.77 -> 0.86), also up on bas / sac / chaussures, slightly down on veste (0.76 -> 0.71,
# 47 test photos). A modest improvement, not a statistically significant one on its own.
#
# The 8-class artifact stays in place: it is still the "is this a garment at all" check
# (hors_perimetre) and `ExtractionAgent` reads its probabilities.
#
# Same split and same cached embeddings as 08 (`data/processed/tunisian_embeddings.npz`):
# hyper-parameters are chosen on val; test is only read to report. The shipped artifact is
# then refit on train+val (more data, same hyper-parameters).
#
# Run as a Jupyter/VS Code interactive script (`# %%` cells), or `python 11_garment_category_head.py`.

# %%
import shutil
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import accuracy_score, f1_score
from sklearn.svm import SVC

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import catalog, preprocessing  # noqa: E402

IMAGES_DIR = ROOT / "data" / "raw" / "tunisian_images"
EMB_PATH = ROOT / "data" / "processed" / "tunisian_embeddings.npz"
OUT_PATH = ROOT / "data" / "processed" / "garment_category_classifier.joblib"
BACKEND_COPY = ROOT.parent / "backend" / "app" / "ml" / "artifacts" / "garment_category_classifier.joblib"

TUNISIAN_SOURCES = {
    "hamadi_abid", "barsha", "chedly_sisters", "noonclo", "kontakt",
    "lyoum", "rooh_clothing", "myjebba", "ileycom",
}

# %% [markdown]
# ## 1. Garments with a cached embedding (non-clothing products are excluded on purpose)

# %%
df = catalog.build_unified_catalog()
df = df[df["source"].isin(TUNISIAN_SOURCES) & df["dressme_category"].isin(preprocessing.DRESSME_CATEGORIES)]
cached = np.load(EMB_PATH, allow_pickle=False)
key_to_vec = dict(zip(cached["ids"].tolist(), cached["vectors"]))
df = df[df["item_key"].isin(key_to_vec)].reset_index(drop=True)
X = np.stack([key_to_vec[k] for k in df["item_key"]])
y = df["dressme_category"].values
train, val, test = (df["split"] == s for s in ("train", "val", "test"))
train, val, test = train.values, val.values, test.values
print(f"{len(df)} garments — train {train.sum()} / val {val.sum()} / test {test.sum()}")

# %% [markdown]
# ## 2. Choose C on validation, report held-out test
#
# C=3 (validation accuracy 0.879) vs C=10 (0.878) vs C=30 (0.869); logistic regression
# peaked at 0.849 on the same split.

# %%
for C in (1, 3, 10, 30):
    model = SVC(C=C).fit(X[train], y[train])
    print(f"C={C:>3}  val acc {accuracy_score(y[val], model.predict(X[val])):.3f}")

CHOSEN_C = 3
model = SVC(C=CHOSEN_C, probability=True, random_state=0).fit(X[train], y[train])
for name, mask in (("val", val), ("test", test)):
    pred = model.predict(X[mask])
    print(f"{name}: accuracy {accuracy_score(y[mask], pred):.3f}  macro-F1 {f1_score(y[mask], pred, average='macro'):.3f}")

# %% [markdown]
# ## 3. Ship: refit on train+val, copy next to the Vision Agent

# %%
final = SVC(C=CHOSEN_C, probability=True, random_state=0).fit(X[train | val], y[train | val])
pred = final.predict(X[test])
print(f"refit on train+val -> test accuracy {accuracy_score(y[test], pred):.3f}  macro-F1 {f1_score(y[test], pred, average='macro'):.3f}")
joblib.dump(final, OUT_PATH, compress=3)
BACKEND_COPY.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(OUT_PATH, BACKEND_COPY)
print(f"saved {OUT_PATH} ({OUT_PATH.stat().st_size / 1e6:.1f} MB) and copied to {BACKEND_COPY}")

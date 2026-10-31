# %% [markdown]
# # DressMe — Outfit compatibility model (real Polyvore outfit pairs)
#
# `RecommendationAgent` (backend/) currently scores a candidate outfit by mean pairwise
# FashionCLIP embedding *similarity* — a reasonable visual-coherence proxy, explicitly
# documented as a stand-in for a real trained compatibility model. This notebook builds
# that model: a linear classifier on top of frozen FashionCLIP embeddings, trained to
# tell "these two items were styled together in a real Polyvore outfit" apart from "these
# two items are from unrelated outfits" — using the 68,306 real outfits in ml/, the same
# positive-pair signal the team's own notebook identified for the Recommendation Agent.
#
# Mirrors ml/notebooks/08_category_classifier.py's approach (linear probe on frozen
# embeddings, honest train/test split, compare against a naive baseline) applied to a
# different task: pairwise compatibility instead of single-item category.

# %%
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import features, polyvore_official  # noqa: E402

RNG = np.random.default_rng(42)
TRAIN_OUTFITS_N = 2000
TEST_OUTFITS_N = 400
MODEL_PATH = ROOT / "data" / "processed" / "compatibility_model.joblib"
EMB_CACHE_PATH = ROOT / "data" / "processed" / "compatibility_embeddings.npz"

# %% [markdown]
# ## 1. Sample outfits (3-6 items — common size, keeps pair counts tractable) from
# genuinely different splits: train outfits to build training pairs, test outfits
# (unseen during training) to evaluate honestly.

# %%
outfits = polyvore_official.load_outfit_structure()
sizes = outfits.groupby(["outfit_split", "set_id"]).size()
usable = sizes[(sizes >= 3) & (sizes <= 6)]


def sample_outfits(split: str, n: int) -> pd.DataFrame:
    set_ids = usable.loc[split].index
    chosen = RNG.choice(set_ids, size=min(n, len(set_ids)), replace=False)
    return outfits[(outfits["outfit_split"] == split) & (outfits["set_id"].isin(chosen))]


train_items = sample_outfits("train", TRAIN_OUTFITS_N)
test_items = sample_outfits("test", TEST_OUTFITS_N)
print(f"train: {train_items['set_id'].nunique()} outfits, {train_items['item_id'].nunique()} unique items")
print(f"test: {test_items['set_id'].nunique()} outfits, {test_items['item_id'].nunique()} unique items")

# %% [markdown]
# ## 2. Build positive (same outfit) and negative (different, random outfit) pairs

# %%
def build_pairs(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    by_outfit = df.groupby("set_id")["item_id"].apply(list)
    all_items = df["item_id"].to_numpy()
    rows = []
    for set_id, items in by_outfit.items():
        for a, b in combinations(items, 2):
            rows.append({"item_a": a, "item_b": b, "label": 1})
        # one random negative per positive, each paired with an item from *some other*
        # outfit (rejection-sample to avoid accidentally picking from the same outfit —
        # items can repeat across outfits in this nondisjoint dataset).
        other_outfit_items = set(all_items) - set(items)
        if not other_outfit_items:
            continue
        other_pool = np.array(list(other_outfit_items))
        for a, _ in combinations(items, 2):
            b = rng.choice(other_pool)
            rows.append({"item_a": a, "item_b": b, "label": 0})
    return pd.DataFrame(rows)


train_pairs = build_pairs(train_items, RNG)
test_pairs = build_pairs(test_items, RNG)
print(f"train pairs: {len(train_pairs)} ({train_pairs['label'].mean():.0%} positive)")
print(f"test pairs: {len(test_pairs)} ({test_pairs['label'].mean():.0%} positive)")

# %% [markdown]
# ## 3. Embed every unique item involved (cached — re-running reuses saved embeddings)

# %%
needed_ids = sorted(set(train_pairs["item_a"]) | set(train_pairs["item_b"])
                     | set(test_pairs["item_a"]) | set(test_pairs["item_b"]))

if EMB_CACHE_PATH.exists():
    cached = np.load(EMB_CACHE_PATH, allow_pickle=False)
    vectors, cached_ids = cached["vectors"], cached["ids"].tolist()
    id_to_vec = dict(zip(cached_ids, vectors))
    print(f"{len(id_to_vec)} already embedded (cached)")
else:
    id_to_vec = {}

missing = [i for i in needed_ids if i not in id_to_vec]
if missing:
    print(f"embedding {len(missing)} new items...")
    model, processor, device = features.load_fashionclip()
    images_by_id = polyvore_official.extract_image_bytes_batch(missing)
    ordered_ids = [i for i in missing if i in images_by_id]
    ordered_bytes = [images_by_id[i] for i in ordered_ids]
    vectors, kept_idx = features.embed_image_bytes(ordered_bytes, model, processor, device)
    for idx, vec in zip(kept_idx, vectors):
        id_to_vec[ordered_ids[idx]] = vec
    np.savez_compressed(EMB_CACHE_PATH, vectors=np.array(list(id_to_vec.values())),
                         ids=np.array(list(id_to_vec.keys())))

print(f"{len(id_to_vec)} total embeddings available")


def with_embeddings(pairs: pd.DataFrame) -> pd.DataFrame:
    has_both = pairs["item_a"].isin(id_to_vec) & pairs["item_b"].isin(id_to_vec)
    return pairs[has_both].reset_index(drop=True)


train_pairs = with_embeddings(train_pairs)
test_pairs = with_embeddings(test_pairs)
print(f"after dropping pairs missing an embedding: {len(train_pairs)} train, {len(test_pairs)} test")

# %% [markdown]
# ## 4. Features: element-wise product of the two (already L2-normalized) embeddings —
# the standard pairwise-compatibility feature (sums to cosine similarity under uniform
# weights, but lets the classifier weight dimensions unevenly, unlike raw similarity).

# %%
def pair_features(pairs: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    a = np.stack([id_to_vec[i] for i in pairs["item_a"]])
    b = np.stack([id_to_vec[i] for i in pairs["item_b"]])
    return a * b, (a * b).sum(axis=1)  # elementwise product, plain cosine similarity


X_train, cos_train = pair_features(train_pairs)
X_test, cos_test = pair_features(test_pairs)
y_train, y_test = train_pairs["label"].to_numpy(), test_pairs["label"].to_numpy()

# %% [markdown]
# ## 5. Train, and compare against the naive cosine-similarity baseline on the *same*
# held-out test pairs — the actual question this notebook exists to answer.

# %%
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score

clf = LogisticRegression(max_iter=2000, class_weight="balanced")
clf.fit(X_train, y_train)
pred = clf.predict(X_test)
proba = clf.predict_proba(X_test)[:, 1]

# Naive baseline: raw cosine similarity thresholded at its own best point on *training*
# data (not peeking at test labels to pick the threshold).
best_threshold, best_train_acc = 0.5, 0.0
for t in np.linspace(cos_train.min(), cos_train.max(), 50):
    acc = accuracy_score(y_train, cos_train >= t)
    if acc > best_train_acc:
        best_threshold, best_train_acc = t, acc
baseline_pred = cos_test >= best_threshold

print("Trained compatibility model:")
print(f"  accuracy={accuracy_score(y_test, pred):.3f}  f1={f1_score(y_test, pred):.3f}  "
      f"auc={roc_auc_score(y_test, proba):.3f}")
print(f"Naive cosine-similarity baseline (threshold={best_threshold:.3f}):")
print(f"  accuracy={accuracy_score(y_test, baseline_pred):.3f}  f1={f1_score(y_test, baseline_pred):.3f}  "
      f"auc={roc_auc_score(y_test, cos_test):.3f}")

# %% [markdown]
# ## 6. Save — backend/app/ml/artifacts/compatibility_model.joblib is a copy of this

# %%
import joblib

joblib.dump(clf, MODEL_PATH)
print(f"Saved to {MODEL_PATH}")

# %% [markdown]
# ## 7. Findings
#
# Fill in after running — does the trained model meaningfully beat raw cosine
# similarity on held-out, never-seen-during-training outfits? If not, that's real
# evidence RecommendationAgent's existing heuristic is already close to what's
# achievable from FashionCLIP embeddings alone, and the gap would need something
# beyond a linear probe (e.g. fine-tuning, or non-visual signal like co-purchase data)
# to close — not a reason to claim a bigger win than the numbers support either way.

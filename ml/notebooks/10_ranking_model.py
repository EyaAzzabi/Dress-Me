# %% [markdown]
# # DressMe — Contextual outfit ranker (learned ranking on visual_coherence + context_fit)
#
# `RecommendationAgent` (backend/) scores a candidate outfit by mean pairwise
# compatibility (the model from notebook 09) plus a hand-tuned style bonus and a
# freshness penalty. What it never used: the **occasion / season / weather** only
# appeared in the explanation text, never in the ranking. This notebook adds that
# signal as a learned ranker.
#
# Two features are *learnable* on the Polyvore training data (the only metadata it has
# per item is a `dressme_category`; items have `season=pd.NA`/`style=pd.NA` and there is
# no per-user usage history — see ml/src/catalog.py, verified):
# - `visual_coherence` — mean pairwise `compatibility_model.pair_compatibility` (reuses
#   the artifact trained in notebook 09).
# - `context_fit` — `mean(outfit image embeddings) . ctx_vec`, where `ctx_vec` is a
#   FashionCLIP **text** embedding of a prompt like "an outfit suitable for a summer
#   wedding in hot weather". FashionCLIP is a CLIP model, so image and text share one
#   space — this dot product is a legitimate zero-shot "does this outfit suit this
#   context" match.
#
# The four other contextual signals the design wants (`season_compat`, `style_match`,
# `freshness`, `history_fit`) are **not** computable on Polyvore, so they are applied as
# a fixed-weight deterministic additive layer at inference time (see
# backend/app/ml/ranking_model.py), NOT learned here (review-F1, voie A). This notebook
# only trains the 2-feature logistic ranker and precomputes the 96 context vectors.
#
# Mirrors ml/notebooks/09_compatibility_model.py's approach: honest train/test split
# (test outfits never seen during training), compare against a naive baseline, and an
# explicit **ship-gate** — the artifact is committed only if the ranker beats the
# baseline by at least +0.02 AUC. Otherwise it stays absent and the runtime falls back
# to the exact existing heuristic.

# %%
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import features, polyvore_official, preprocessing  # noqa: E402

# Reuse the backend's trained compatibility model for visual_coherence (torch-free:
# compatibility_model.py only loads numpy/joblib). The ml/ env has torch/transformers
# for the FashionCLIP text/image embeddings below; the *runtime* in backend/ does not.
BACKEND = ROOT.parent / "backend"
sys.path.insert(0, str(BACKEND))
from app.ml import compatibility_model  # noqa: E402
from app.services.occasions import OCCASION_CATEGORIES  # noqa: E402

RNG = np.random.default_rng(42)
TRAIN_OUTFITS_N = 2000
TEST_OUTFITS_N = 400
SHIP_GATE_DELTA = 0.02  # commit the artifact only if AUC_ranker >= AUC_baseline + this

MODEL_OUT = ROOT / "data" / "processed" / "ranking_model.joblib"
VECTORS_OUT = ROOT / "data" / "processed" / "context_vectors.npz"
EMB_CACHE_PATH = ROOT / "data" / "processed" / "compatibility_embeddings.npz"
ARTIFACTS_DIR = BACKEND / "app" / "ml" / "artifacts"

# Seasons/bands the runtime context vectors cover (coherent with backend seasons.py:
# ete/hiver/mi_saison + froid/modere/chaud). toutes_saisons is permissive, not a context.
SEASONS = ["ete", "hiver", "mi_saison"]
BANDS = ["froid", "modere", "chaud"]

# FashionCLIP is trained on English, so the context prompts are English (same convention
# as ml/src/features.py DRESSME_CATEGORY_PROMPTS).
_OCCASION_PROMPTS = {
    "mariage": "a wedding", "soiree": "an evening party", "travail": "a work outfit",
    "casual_quotidien": "a casual everyday outfit", "sport": "a sporty outfit",
    "plage": "a beach outfit", "voyage": "a travel outfit", "ceremonie": "a ceremony outfit",
}
_SEASON_PROMPTS = {"ete": "summer", "hiver": "winter", "mi_saison": "a mild season"}
_BAND_PROMPTS = {"froid": "cold", "modere": "mild", "chaud": "hot"}

# %% [markdown]
# ## 1. Composition `dressme_category -> occasion_category` (review-F4)
#
# Polyvore's per-item metadata is only a `dressme_category` (haut/bas/robe/veste/
# chaussures/sac/accessoire — no swimwear, no sportswear). We synthesize each real
# outfit's occasion from the **composition** of its items' categories. This means:
# - `sport` / `plage` / `voyage` are **weakly coverable** on Polyvore (no swimwear or
#   gym clothes in the vocabulary) — the `context_fit` signal concentrates on
#   `travail` / `ceremonie` / `mariage` / `soiree` / `casual_quotidien`.
# - `mariage` vs `ceremonie` can't be told apart from composition alone, so dress-led
#   outfits fold into `ceremonie` (the broader label).
#
# The ship-gate (§5) is the final arbiter: if this synthesized signal doesn't beat the
# baseline, the artifact isn't committed and the runtime keeps the exact heuristic.

# %%
_POLYVORE_CAT_TO_DRESSME = preprocessing.POLYVORE_CATEGORY_TO_DRESSME


def occasion_from_composition(categories: set[str]) -> str:
    """Synthesize an occasion_category from the set of dressme_categories in an outfit.

    - A dress (robe) leads -> dressed-up occasion (ceremonie; mariage folded in).
    - top+bottom+jacket+shoes -> work.
    - everything else -> casual everyday.
    sport/plage/voyage are unreachable from Polyvore's vocabulary (no swimwear/gym).
    """
    if "robe" in categories:
        return "ceremonie"
    if {"haut", "bas", "veste", "chaussures"} <= categories:
        return "travail"
    return "casual_quotidien"


# %% [markdown]
# ## 2. Sample train/test outfits (genuinely different splits, like notebook 09)

# %%
outfits = polyvore_official.load_outfit_structure()
metadata = polyvore_official.build_item_metadata_index()
# dressme_category per item (via the same mapping catalog.load_polyvore uses).
metadata["dressme_category"] = preprocessing.map_polyvore(metadata)
item_category = dict(zip(metadata["item_id"].astype(str), metadata["dressme_category"]))

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
# ## 3. Embed every unique item involved (reuse the cache notebook 09 produced)

# %%
needed_ids = sorted(set(train_items["item_id"]) | set(test_items["item_id"]))

if EMB_CACHE_PATH.exists():
    cached = np.load(EMB_CACHE_PATH, allow_pickle=False)
    vectors, cached_ids = cached["vectors"], cached["ids"].astype(str).tolist()
    id_to_vec = dict(zip(cached_ids, vectors))
    print(f"{len(id_to_vec)} already embedded (cached)")
else:
    id_to_vec = {}

missing = [i for i in needed_ids if str(i) not in id_to_vec]
if missing:
    print(f"embedding {len(missing)} new items...")
    model, processor, device = features.load_fashionclip()
    images_by_id = polyvore_official.extract_image_bytes_batch([str(i) for i in missing])
    ordered_ids = [str(i) for i in missing if str(i) in images_by_id]
    ordered_bytes = [images_by_id[i] for i in ordered_ids]
    vecs, kept_idx = features.embed_image_bytes(ordered_bytes, model, processor, device)
    for idx, vec in zip(kept_idx, vecs):
        id_to_vec[ordered_ids[idx]] = vec
    np.savez_compressed(EMB_CACHE_PATH, vectors=np.array(list(id_to_vec.values())),
                        ids=np.array(list(id_to_vec.keys())))

print(f"{len(id_to_vec)} total embeddings available")


def outfit_vecs(set_id: str) -> np.ndarray | None:
    items = outfits[outfits["set_id"] == set_id]["item_id"].astype(str)
    vecs = [id_to_vec[i] for i in items if i in id_to_vec]
    if len(vecs) < 2:
        return None
    return np.stack(vecs)


def visual_coherence(vecs: np.ndarray) -> float:
    """Mean pairwise compatibility (reuses the trained notebook-09 model)."""
    total, count = 0.0, 0
    for i in range(len(vecs)):
        for j in range(i + 1, len(vecs)):
            total += compatibility_model.pair_compatibility(vecs[i], vecs[j])
            count += 1
    return float(total / count) if count else 1.0


# %% [markdown]
# ## 4. Precompute the 96 context vectors (FashionCLIP text, L2-normalized)
#
# 72 specific `occasion|season|band` (8×3×3) + 24 band-agnostic `occasion|season|_any`
# (8×3) = 96 stored vectors (review-F9). The `season=None` case is zeros computed at
# runtime, not stored.

# %%
ctx_keys = []
ctx_texts = []
for occasion in OCCASION_CATEGORIES:
    for season in SEASONS:
        for band in BANDS:
            ctx_keys.append(f"{occasion}|{season}|{band}")
            ctx_texts.append(
                f"an outfit suitable for a {_SEASON_PROMPTS[season]} "
                f"{_OCCASION_PROMPTS[occasion]} in {_BAND_PROMPTS[band]} weather"
            )
        ctx_keys.append(f"{occasion}|{season}|_any")
        ctx_texts.append(
            f"an outfit suitable for a {_SEASON_PROMPTS[season]} "
            f"{_OCCASION_PROMPTS[occasion]}"
        )

clip_model, clip_processor, clip_device = features.load_fashionclip()
ctx_vectors = features.embed_texts(ctx_texts, clip_model, clip_processor, clip_device)
assert ctx_vectors.shape == (96, 512), f"expected 96 context vectors of dim 512, got {ctx_vectors.shape}"
print(f"precomputed {ctx_vectors.shape[0]} context vectors (expected 96)")
np.savez_compressed(VECTORS_OUT, keys=np.array(ctx_keys), vectors=ctx_vectors.astype(np.float32))
print(f"saved context vectors to {VECTORS_OUT}")

key_to_ctx = dict(zip(ctx_keys, ctx_vectors))


def ctx_vec(occasion: str, season: str, band: str | None) -> np.ndarray:
    if season is None:
        return np.zeros(ctx_vectors.shape[1], dtype=np.float32)
    key = f"{occasion}|{season}|{band if band is not None else '_any'}"
    return key_to_ctx[key]


# %% [markdown]
# ## 5. Build (visual_coherence, context_fit) features with synthesized labels
#
# Positives: a real outfit + its composition-deduced occasion + a plausible
# season/band. `context_fit = mean(outfit_vecs) . ctx_vec` should be high (the outfit
# matches the context).
# Negatives: (i) the **same** outfit + an **incoherent** (different) occasion — same
# `visual_coherence`, lower `context_fit`; (ii) a **random assembly** of items from
# different outfits + any context — low `visual_coherence`. This gives `context_fit` a
# real signal to learn (separates type-(i) negatives from positives) on top of
# `visual_coherence` (separates type-(ii) negatives).
#
# On Polyvore `style_match=False` and `recent=0` always, so the **baseline** the ranker
# must beat is just `visual_coherence` (= `min(1, visual)`).

# %%
def composition_categories(set_id: str) -> set[str]:
    items = outfits[outfits["set_id"] == set_id]["item_id"].astype(str)
    cats = {item_category.get(i) for i in items}
    cats.discard(None)
    return {c for c in cats if c != preprocessing.OUT_OF_SCOPE}


def build_rows(items_df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    set_ids = items_df["set_id"].drop_duplicates().tolist()
    X, y = [], []
    for set_id in set_ids:
        vecs = outfit_vecs(set_id)
        if vecs is None:
            continue
        mean_vec = vecs.mean(axis=0)
        visual = visual_coherence(vecs)
        occ = occasion_from_composition(composition_categories(set_id))
        season = str(RNG.choice(SEASONS))
        band = str(RNG.choice(BANDS))
        # positive: coherent context
        X.append([visual, float(mean_vec @ ctx_vec(occ, season, band))])
        y.append(1)
        # negative (i): same outfit, incoherent occasion
        other_occ = str(RNG.choice([o for o in OCCASION_CATEGORIES if o != occ]))
        X.append([visual, float(mean_vec @ ctx_vec(other_occ, season, band))])
        y.append(0)
        # negative (ii): random assembly + any context (low visual_coherence)
        pool = [v for sid in set_ids for v in (outfit_vecs(sid) or [])]
        if len(pool) >= 3:
            rnd = np.stack(RNG.choice(len(pool), size=min(4, len(pool)), replace=False))
            rnd_vecs = np.array(pool)[rnd]
            X.append([visual_coherence(rnd_vecs), float(rnd_vecs.mean(axis=0) @ ctx_vec(occ, season, band))])
            y.append(0)
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.int32)


X_train, y_train = build_rows(train_items)
X_test, y_test = build_rows(test_items)
print(f"train: {len(y_train)} rows ({y_train.mean():.0%} positive)")
print(f"test: {len(y_test)} rows ({y_test.mean():.0%} positive)")

# %% [markdown]
# ## 6. Train the 2-feature logistic ranker, honest split, AUC vs baseline + ship-gate

# %%
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

clf = LogisticRegression(max_iter=2000, class_weight="balanced")
clf.fit(X_train, y_train)
ranker_proba = clf.predict_proba(X_test)[:, 1]
baseline_proba = X_test[:, 0]  # visual_coherence alone (style_match=False, recent=0)

auc_ranker = roc_auc_score(y_test, ranker_proba)
auc_baseline = roc_auc_score(y_test, baseline_proba)
print(f"ranker AUC  = {auc_ranker:.3f}  (visual_coherence + context_fit)")
print(f"baseline AUC = {auc_baseline:.3f}  (visual_coherence alone)")
print(f"delta       = {auc_ranker - auc_baseline:+.3f}  (ship-gate needs >= +{SHIP_GATE_DELTA:.2f})")

# %% [markdown]
# ## 7. Ship-gate + save
#
# Only copy `ranking_model.joblib` and `context_vectors.npz` to
# `backend/app/ml/artifacts/` if the ranker beats the baseline by >= +0.02 AUC on the
# held-out test outfits. Otherwise leave them absent: the runtime
# (`ranking_model.score_outfit`) falls back to the exact existing heuristic, and the
# `context_fit` zero-shot signal stays available for a future, better-calibrated
# iteration. This is the publication criterion (review-F5); the kill-switch
# `RANKING_ENABLED` is a complement, not a replacement.

# %%
import joblib

joblib.dump(clf, MODEL_OUT)
print(f"saved trained ranker to {MODEL_OUT}")

if auc_ranker >= auc_baseline + SHIP_GATE_DELTA:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy(MODEL_OUT, ARTIFACTS_DIR / "ranking_model.joblib")
    shutil.copy(VECTORS_OUT, ARTIFACTS_DIR / "context_vectors.npz")
    print(f"SHIP-GATE PASSED (+{auc_ranker - auc_baseline:.3f} AUC) — copied artifacts to {ARTIFACTS_DIR}")
else:
    print(
        f"SHIP-GATE FAILED (+{auc_ranker - auc_baseline:.3f} AUC < +{SHIP_GATE_DELTA:.2f}) — "
        "artifacts left ABSENT; runtime keeps the exact heuristic fallback."
    )

# %% [markdown]
# ## 8. Findings
#
# Fill in after running — does adding the zero-shot `context_fit` signal beat ranking on
# `visual_coherence` alone by at least +0.02 AUC on held-out, never-seen outfits? The
# honest expectation: `context_fit` is a *weak* signal here because the occasion is
# *synthesized* from composition (not labeled), and sport/plage/voyage are barely
# coverable on Polyvore's vocabulary. If the ship-gate fails, that is real evidence the
# learned ranker isn't yet worth shipping over the existing heuristic — not a reason to
# commit it anyway. The `context_fit` machinery (context vectors + score_outfit's
# artifact path) remains in place for a future iteration with real occasion labels or a
# better signal; the fallback guarantees no regression meanwhile.
#
# - AUC ranker: ___ / AUC baseline: ___ / delta: ___
# - Ship-gate: PASSED / FAILED (delete as appropriate)
# - Notes on the synthesized-context limitation:

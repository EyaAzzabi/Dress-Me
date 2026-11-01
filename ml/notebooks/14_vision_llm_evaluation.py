# %% [markdown]
# # DressMe — Does an OpenAI vision model help the Vision Agent? (CRISPE prompt)
#
# `backend/app/ml/vision_llm.py` asks `gpt-4o-mini` (image, low detail, temperature 0) to
# describe a garment photo with a CRISPE-structured system prompt, and validates every value
# against the project's vocabularies. This script measures whether it beats FashionCLIP, per
# attribute, on labeled photos: 200 random held-out Tunisian garments (category) and the 300
# Kaggle photos (color / season / style). ~500 calls, a few cents; answers are cached in
# `data/processed/vision_llm_eval_cache.json` so re-running is free.
#
# Needs OPENAI_API_KEY in backend/.env. Run FROM backend/ so the .env is found:
#     cd backend && python ../ml/notebooks/14_vision_llm_evaluation.py
#
# Result (2026-10-26; 12 of 500 calls failed and count as "no answer"):
#   category  FashionCLIP 87.5% | OpenAI alone 81.9% | hybrid (OpenAI only below 0.60 confidence)
#             88.0% (+0.5 pt, 95% CI [-1.5, +3.0]) -> NOT adopted
#   color     FashionCLIP 70.4% | OpenAI 68.7%                                -> NOT adopted
#   season    OpenAI answers 58% of photos with 43% accuracy (0.33 balanced)  -> NOT adopted
#   style     on the 76 photos FashionCLIP leaves empty: OpenAI 89.5% vs 39.5%
#             (difference +0.50, 95% CI [+0.36, +0.65]); but those photos are 80% Casual, so versus
#             "always Casual" the gain is ~9 points, concentrated on Sports   -> ADOPTED (fill-in only)

# %%
import json
import os
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, balanced_accuracy_score

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "backend"))
os.environ["VISION_LLM_ENABLED"] = "true"
from src import catalog, preprocessing  # noqa: E402
from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()
from app.ml import garment_types, vision_llm, vision_model  # noqa: E402

CACHE = ROOT / "data" / "processed" / "vision_llm_eval_cache.json"
cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
rng = np.random.default_rng(0)
COLORS = list(vision_model.COLOR_PROMPTS)
TUN = {"hamadi_abid", "barsha", "chedly_sisters", "noonclo", "kontakt", "lyoum", "rooh_clothing", "myjebba", "ileycom"}

# %% [markdown]
# ## Data and the (cached) OpenAI answers

# %%
df = catalog.build_unified_catalog()
ids = {p.stem for p in (ROOT / "data/raw/tunisian_images").glob("*.jpg")}
df = df[df["source"].isin(TUN) & df["item_key"].isin(ids) & df["dressme_category"].isin(preprocessing.DRESSME_CATEGORIES)]
z = np.load(ROOT / "data/processed/tunisian_embeddings.npz", allow_pickle=False)
vec = dict(zip(z["ids"].tolist(), z["vectors"]))
df = df[df["item_key"].isin(vec) & (df["split"] == "test")].reset_index(drop=True)
sample = df.iloc[rng.choice(len(df), 200, replace=False)]

styles = pd.read_csv(ROOT / "data/raw/styles.csv", on_bad_lines="skip")
have = {int(p.stem): p for p in (ROOT / "data/raw/images").glob("*.jpg") if p.stem.isdigit()}
kag = styles[styles["id"].isin(have)].reset_index(drop=True)
kvec = dict(zip(*[np.load(ROOT / "data/processed/kaggle300_embeddings.npz", allow_pickle=False)[k] for k in ("ids", "vectors")]))
kag["season_label"] = kag["season"].map({"Summer": "ete", "Winter": "hiver", "Fall": "mi_saison", "Spring": "mi_saison"})
kag["color_label"] = [preprocessing.normalize_color(v) for v in kag["baseColour"]]

jobs = {f"tun:{r.item_key}": ROOT / "data/raw/tunisian_images" / f"{r.item_key}.jpg" for r in sample.itertuples()}
jobs |= {f"kag:{r.id}": have[int(r.id)] for r in kag.itertuples()}
todo = {k: p for k, p in jobs.items() if k not in cache}
print(f"{len(jobs)} photos, {len(todo)} to ask")
with ThreadPoolExecutor(8) as pool:
    for key, answer in pool.map(lambda kp: (kp[0], vision_llm.describe_image(kp[1].read_bytes())), todo.items()):
        cache[key] = answer
CACHE.write_text(json.dumps(cache))
print("failed calls:", sum(v is None for v in cache.values()))

# %% [markdown]
# ## Category (random held-out Tunisian garments)

# %%
yt = sample["dressme_category"].values
fc = [vision_model.predict_category(vec[k]) for k in sample["item_key"]]
fc_pred, fc_conf = np.array([p[0] for p in fc]), np.array([p[1] for p in fc])
llm = [cache[f"tun:{k}"] for k in sample["item_key"]]
answered = np.array([a is not None for a in llm])
llm_pred = np.array([a["category"] if a else "?" for a in llm])
unsure = fc_conf < vision_model.CATEGORY_MIN_CONFIDENCE
hybrid = np.where(unsure & answered, llm_pred, fc_pred)
print(f"FashionCLIP {accuracy_score(yt, fc_pred):.3f} | OpenAI alone {accuracy_score(yt[answered], llm_pred[answered]):.3f} "
      f"| hybrid {accuracy_score(yt, hybrid):.3f} (OpenAI asked on {unsure.mean():.1%})")
diffs = [accuracy_score(yt[s], hybrid[s]) - accuracy_score(yt[s], fc_pred[s]) for s in (rng.integers(0, len(yt), len(yt)) for _ in range(2000))]
print(f"hybrid - FashionCLIP: {np.mean(diffs):+.3f}  95% CI [{np.percentile(diffs, 2.5):+.3f}, {np.percentile(diffs, 97.5):+.3f}]")

# %% [markdown]
# ## Color, season, style (Kaggle photos)

# %%
kx = np.stack([kvec[int(i)] for i in kag["id"]])
ka = [cache[f"kag:{i}"] for i in kag["id"]]
cl = kag["color_label"].isin(COLORS).values
fc_col = np.array([vision_model.predict_colors(e)[0][0] for e in kx])
llm_col = np.array([(a["colors"][0] if a and a["colors"] else "?") for a in ka])
print(f"COLOR FashionCLIP {accuracy_score(kag['color_label'][cl], fc_col[cl]):.3f} | OpenAI {accuracy_score(kag['color_label'][cl], llm_col[cl]):.3f}")

ys = kag["season_label"].values
llm_s = np.array([(a["season"] if a and a["season"] else None) for a in ka], dtype=object)
ans = np.array([s is not None for s in llm_s])
print(f"SEASON OpenAI answers {ans.mean():.1%}: acc {accuracy_score(ys[ans], llm_s[ans].astype(str)):.3f} "
      f"balanced {balanced_accuracy_score(ys[ans], llm_s[ans].astype(str)):.3f}")

ku = kag["usage"].isin(vision_llm.STYLES).values
yu = kag["usage"].values[ku]
post = [garment_types.usage_posterior(e) for e in kx[ku]]
fc_u = np.array([max(p, key=p.get) for p in post])
fc_conf_u = np.array([max(p.values()) for p in post])
llm_u = np.array([(a["style"] if a and a["style"] else None) for a, k in zip(ka, ku) if k], dtype=object)
fill = (fc_conf_u < vision_model.STYLE_MIN_CONFIDENCE) & np.array([s is not None for s in llm_u])
print(f"STYLE on the {fill.sum()} photos FashionCLIP leaves empty: OpenAI {accuracy_score(yu[fill], llm_u[fill].astype(str)):.3f} "
      f"vs FashionCLIP {accuracy_score(yu[fill], fc_u[fill]):.3f}; majority class there "
      f"{pd.Series(yu[fill]).value_counts(normalize=True).max():.3f}")
idx = np.where(fill)[0]
diffs = [accuracy_score(yu[s], llm_u[s].astype(str)) - accuracy_score(yu[s], fc_u[s]) for s in (rng.choice(idx, len(idx)) for _ in range(3000))]
print(f"OpenAI - FashionCLIP: {np.mean(diffs):+.3f}  95% CI [{np.percentile(diffs, 2.5):+.3f}, {np.percentile(diffs, 97.5):+.3f}]")

# %% [markdown]
# # DressMe — Vision Agent evaluation: before vs. after, on labeled photos
#
# Measures the real backend code (`backend/app/ml/vision_model.py`) against the previous
# behavior (8-class probe for category; zero-shot prompts for season and style), so every
# claim in the Vision Agent docstrings can be re-checked. Writes `reports/vision_agent_evaluation.md`.
#
#   * category / color: the held-out Tunisian test split (cached embeddings, same split as
#     08 and 11). The shipped garment head was refit on train+val, so test is untouched.
#   * season / style: the 300 Kaggle photos available locally (`data/raw/images`) with their
#     `season` / `usage` labels. Small, and the labels are noisy — that is why every
#     comparison carries a paired-bootstrap interval.
#
# Needs: `data/processed/tunisian_embeddings.npz`, the backend artifacts, `data/raw/styles.csv`
# and the 300 images. Run `python 13_vision_agent_evaluation.py`.

# %%
import sys
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "backend"))
from src import catalog, preprocessing  # noqa: E402
from app.ml import garment_types, vision_model  # noqa: E402

TUNISIAN_SOURCES = {"hamadi_abid", "barsha", "chedly_sisters", "noonclo", "kontakt",
                    "lyoum", "rooh_clothing", "myjebba", "ileycom"}
COLORS = list(vision_model.COLOR_PROMPTS)
OOS = preprocessing.OUT_OF_SCOPE
REPORT = ROOT / "reports" / "vision_agent_evaluation.md"
lines: list[str] = []


def say(text: str = "") -> None:
    print(text)
    lines.append(text)


# %% [markdown]
# ## Data

# %%
df = catalog.build_unified_catalog()
ids = {p.stem for p in (ROOT / "data/raw/tunisian_images").glob("*.jpg")}
df = df[df["source"].isin(TUNISIAN_SOURCES) & df["item_key"].isin(ids)
        & (df["dressme_category"].isin(preprocessing.DRESSME_CATEGORIES) | (df["dressme_category"] == OOS))]
cached = np.load(ROOT / "data/processed/tunisian_embeddings.npz", allow_pickle=False)
vec = dict(zip(cached["ids"].tolist(), cached["vectors"]))
df = df[df["item_key"].isin(vec)].reset_index(drop=True)
X = np.stack([vec[k] for k in df["item_key"]])
y = df["dressme_category"].values
test = (df["split"] == "test").values
garment = y != OOS

styles = pd.read_csv(ROOT / "data/raw/styles.csv", on_bad_lines="skip")
have = {int(p.stem): p for p in (ROOT / "data/raw/images").glob("*.jpg") if p.stem.isdigit()}
kag = styles[styles["id"].isin(have)].reset_index(drop=True)
cache = ROOT / "data/processed/kaggle300_embeddings.npz"
if cache.exists():
    z = np.load(cache, allow_pickle=False)
    kvec = dict(zip(z["ids"].tolist(), z["vectors"]))
else:
    kvec = {int(i): vision_model.embed_image_bytes(have[int(i)].read_bytes()) for i in kag["id"]}
    np.savez(cache, ids=np.array(list(kvec)), vectors=np.stack(list(kvec.values())))
XK = np.stack([kvec[int(i)] for i in kag["id"]])
kag["season_label"] = kag["season"].map({"Summer": "ete", "Winter": "hiver", "Fall": "mi_saison", "Spring": "mi_saison"})
kag["color_label"] = [preprocessing.normalize_color(v) for v in kag["baseColour"]]

rng = np.random.default_rng(0)


def paired_bootstrap(truth, before, after, metric, n=2000):
    truth, before, after = map(np.asarray, (truth, before, after))
    diffs = []
    for _ in range(n):
        i = rng.integers(0, len(truth), len(truth))
        diffs.append(metric(truth[i], after[i]) - metric(truth[i], before[i]))
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return metric(truth, after) - metric(truth, before), lo, hi


# %% [markdown]
# ## 1. Category (held-out Tunisian test split)

# %%
say("# Vision Agent evaluation (before vs. after)\n")
say("## Category — held-out Tunisian test photos\n")
gate = joblib.load(vision_model.CATEGORY_CLASSIFIER_PATH)
before = gate.predict(X[test])
after_pairs = [vision_model.predict_category(e) for e in X[test]]
after = np.array([p[0] for p in after_pairs])
conf = np.array([p[1] for p in after_pairs])
yt, gt = y[test], garment[test]


GARMENT_LABELS = list(preprocessing.DRESSME_CATEGORIES)
kept = before[gt] != OOS  # the 8-class probe is the gate in both versions, so the same photos are kept


def cat_row(name, pred):
    return (f"| {name} | {accuracy_score(yt[gt], pred[gt]):.3f} | "
            f"{f1_score(yt[gt], pred[gt], labels=GARMENT_LABELS, average='macro'):.3f} | "
            f"{accuracy_score(yt[gt][kept], pred[gt][kept]):.3f} | "
            f"{f1_score(yt[gt][kept], pred[gt][kept], labels=GARMENT_LABELS, average='macro'):.3f} |")


say(f"{len(yt)} photos ({int(gt.sum())} real garments, {int((~gt).sum())} non-clothing catalog products). "
    f"The \"hors_perimetre\" gate is unchanged: it keeps {kept.mean():.1%} of garments and rejects "
    f"{(after[~gt] == OOS).mean():.1%} of the non-clothing products, before and after.\n")
say("Macro-F1 is over the 7 garment labels only (a photo sent to hors_perimetre counts as a miss).\n")
say("| | accuracy, all garments | macro-F1, all garments | accuracy, garments kept by the gate | macro-F1, garments kept by the gate |")
say("|---|---|---|---|---|")
say(cat_row("before: 8-class linear probe", before))
say(cat_row("after: probe as gate + SVM garment head", after))
b_kept, a_kept, t_kept = before[gt][kept], after[gt][kept], yt[gt][kept]
d, lo, hi = paired_bootstrap(t_kept, b_kept, a_kept, accuracy_score)
say(f"\nCategory head alone (garments kept by the gate): accuracy {d:+.3f} (95% CI [{lo:+.3f}, {hi:+.3f}]) — "
    f"{'a significant' if lo > 0 else 'a modest, NOT statistically significant'} gain.\n")
from sklearn.metrics import precision_recall_fscore_support  # noqa: E402

pb = precision_recall_fscore_support(t_kept, b_kept, labels=GARMENT_LABELS, zero_division=0)
pa = precision_recall_fscore_support(t_kept, a_kept, labels=GARMENT_LABELS, zero_division=0)
say("| class | test photos | F1 before | F1 after |")
say("|---|---|---|---|")
for i, label in enumerate(GARMENT_LABELS):
    say(f"| {label} | {pa[3][i]} | {pb[2][i]:.3f} | {pa[2][i]:.3f} |")
say()

ok = after[gt] == yt[gt]
held = conf[gt] < vision_model.CATEGORY_MIN_CONFIDENCE
say(f"Confidence gate at {vision_model.CATEGORY_MIN_CONFIDENCE}: asks the user to confirm {held.mean():.1%} of garments "
    f"({(held & ok).sum() / ok.sum():.1%} of the correct ones, {(held & ~ok).sum() / (~ok).sum():.1%} of the wrong ones); "
    f"accuracy of what is accepted: {ok[~held].mean():.3f}.\n")

# %% [markdown]
# ## 2. Season and style (300 labeled Kaggle photos)

# %%
say("## Season and style — 300 labeled Kaggle photos\n")
sp, stp = vision_model.SEASON_PROMPTS, vision_model.STYLE_PROMPTS
legacy_season = np.array(list(sp))[[np.argmax([v for v in vision_model._zero_shot_probs(e, sp, "{}").values()]) for e in XK]]
legacy_style = np.array(list(stp))[[np.argmax([v for v in vision_model._zero_shot_probs(
    e, stp, "a photo of a {} item of clothing").values()]) for e in XK]]
new_season_p = [garment_types.season_posterior(e) for e in XK]
new_usage_p = [garment_types.usage_posterior(e) for e in XK]
new_season = np.array([max(p, key=p.get) for p in new_season_p])
new_usage = np.array([max(p, key=p.get) for p in new_usage_p])

ys = kag["season_label"].values
say(f"**Season** (always answering the majority class gets {pd.Series(ys).value_counts(normalize=True).max():.3f})\n")
say("| | accuracy | balanced accuracy |")
say("|---|---|---|")
say(f"| before: zero-shot prompts | {accuracy_score(ys, legacy_season):.3f} | {balanced_accuracy_score(ys, legacy_season):.3f} |")
say(f"| after: via garment type | {accuracy_score(ys, new_season):.3f} | {balanced_accuracy_score(ys, new_season):.3f} |")
for nm, metric in (("accuracy", accuracy_score), ("balanced accuracy", balanced_accuracy_score)):
    d, lo, hi = paired_bootstrap(ys, legacy_season, new_season, metric)
    say(f"\n{nm}: {d:+.3f} (95% CI [{lo:+.3f}, {hi:+.3f}])")
cs = np.array([max(p.values()) for p in new_season_p])
m = cs >= vision_model.SEASON_MIN_CONFIDENCE
say(f"\nWhat the agent actually stores (suggest only at confidence >= {vision_model.SEASON_MIN_CONFIDENCE}): "
    f"answers {m.mean():.1%} of photos, accuracy there {accuracy_score(ys[m], new_season[m]):.3f} "
    f"(majority class on that subset: {pd.Series(ys[m]).value_counts(normalize=True).max():.3f}). "
    f"The Kaggle season is a collection label, not a visible property — the ceiling is low.\n")

ku = kag["usage"].isin(garment_types._priors()["usages"]).values
yu = kag["usage"].values[ku]
say(f"**Style** — Casual / Sports / Ethnic / Formal only ({ku.sum()} photos; majority class "
    f"{pd.Series(yu).value_counts(normalize=True).max():.3f}; Smart Casual / Party / Travel / Home are ~0.5% of the labels)\n")
legacy_cmp = np.array(["Casual", "Formal", "Sports", "Ethnic"])[[
    np.argmax([vision_model._zero_shot_probs(e, stp, "a photo of a {} item of clothing")[c] for c in ("Casual", "Formal", "Sports", "Ethnic")])
    for e in XK[ku]]]
say("| | accuracy | balanced accuracy |")
say("|---|---|---|")
say(f"| before: zero-shot prompts (restricted to the 4) | {accuracy_score(yu, legacy_cmp):.3f} | {balanced_accuracy_score(yu, legacy_cmp):.3f} |")
say(f"| after: via garment type | {accuracy_score(yu, new_usage[ku]):.3f} | {balanced_accuracy_score(yu, new_usage[ku]):.3f} |")
for nm, metric in (("accuracy", accuracy_score), ("balanced accuracy", balanced_accuracy_score)):
    d, lo, hi = paired_bootstrap(yu, legacy_cmp, new_usage[ku], metric)
    say(f"\n{nm}: {d:+.3f} (95% CI [{lo:+.3f}, {hi:+.3f}])")
cu = np.array([max(p.values()) for p in new_usage_p])[ku]
m = cu >= vision_model.STYLE_MIN_CONFIDENCE
say(f"\nWhat the agent stores (style only at confidence >= {vision_model.STYLE_MIN_CONFIDENCE}): answers {m.mean():.1%} of photos, "
    f"accuracy there {accuracy_score(yu[m], new_usage[ku][m]):.3f}, balanced accuracy {balanced_accuracy_score(yu[m], new_usage[ku][m]):.3f}.\n")

# %% [markdown]
# ## 3. Color (unchanged — kept here as the reference point)

# %%
say("## Color — zero-shot, unchanged\n")
labeled = (df["dressme_category"].isin(preprocessing.DRESSME_CATEGORIES)).values
first = df["colors_raw"].astype(str).str.split(";").str[0]
df["color_label"] = [preprocessing.normalize_color(v) for v in first]
lab = labeled & df["color_label"].isin(COLORS).values
pred = np.array([vision_model.predict_colors(e)[0][0] for e in X[lab]])
say(f"Tunisian in-scope photos with a usable color label: {int(lab.sum())} — accuracy {accuracy_score(df['color_label'][lab], pred):.3f}.")
kl = kag["color_label"].isin(COLORS).values
pk = np.array([vision_model.predict_colors(e)[0][0] for e in XK[kl]])
say(f"Kaggle photos: {int(kl.sum())} — accuracy {accuracy_score(kag['color_label'][kl], pk):.3f}.\n")
say("Tried and rejected (same labels, val/test discipline): five prompt templates (+0.0 to -3.3 pts), color synonyms "
    "(-3 to +1.7 pts, inconsistent across the two datasets), and logistic-regression probes trained on the Tunisian color "
    "labels (best 69.5% on Tunisian test vs 64.2% zero-shot, but 47-56% on Kaggle vs 70.4% zero-shot: the labels are few, "
    "imbalanced — 7 violet, 9 red, 10 green training photos — and multi-color products carry only their first color).\n")

REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"\nwrote {REPORT}")

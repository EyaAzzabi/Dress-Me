# %% [markdown]
# # DressMe — Garment-type priors for season and style
#
# FashionCLIP is poor at abstract prompts ("a lightweight summer garment": 46% season
# accuracy on 300 labeled Kaggle photos — below the 50.7% of always answering "ete";
# "a photo of a formal item of clothing": 39.5% style accuracy). It is good at concrete
# garments ("a pair of shorts", "a knitted sweater": ~69% top-1 over 40 article types).
# So season and style are read through the garment type:
#
#     P(season | photo) = sum over types of  P(type | photo) * leaning(type -> season)
#
# `leaning(type -> season)` comes from the 44k labeled rows of Fashion Product Images
# (`styles.csv`), as a likelihood ratio — P(season | type) / P(season), renormalized — so
# the dataset's own skew (48% Summer, 78% Casual) is not baked into the answer.
#
# Honest limits, measured on the 300 locally available Kaggle photos (paired bootstrap):
#   * season: balanced accuracy 0.35 -> 0.48 (+0.126, 95% CI [+0.05, +0.21]); plain accuracy
#     unchanged (+0.02, CI [-0.06, +0.10]). The Kaggle "season" is a collection label, not a
#     visible property (a t-shirt is 49% Summer / 47% Fall+Spring), so the ceiling is low —
#     which is why the Vision Agent only *suggests* a season when this is confident.
#   * style: balanced accuracy 0.64 -> 0.78 (+0.133, CI [+0.05, +0.22]) on Casual/Sports/
#     Ethnic/Formal. Smart Casual / Party / Travel / Home are ~0.5% of the labels, so they
#     cannot be learned or validated from this data and are no longer output.
#
# Writes `backend/app/ml/artifacts/garment_type_priors.json`. Needs only `styles.csv`
# (no images). Run as an interactive script or `python 12_garment_type_priors.py`.

# %%
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parent / "backend" / "app" / "ml" / "artifacts" / "garment_type_priors.json"

SEASONS = ["ete", "hiver", "mi_saison"]
USAGES = ["Casual", "Sports", "Ethnic", "Formal"]

# Wardrobe-relevant Fashion Product Images article types -> a natural description for CLIP.
# (Cosmetics, watches, underwear, gift sets... are left out: not wardrobe pieces.)
TYPE_PROMPTS = {
    "Tshirts": "a t-shirt", "Shirts": "a button-up shirt", "Tops": "a women's top", "Kurtas": "a kurta",
    "Kurtis": "a kurti", "Tunics": "a tunic", "Sweatshirts": "a sweatshirt", "Sweaters": "a knitted sweater",
    "Jackets": "a jacket", "Innerwear Vests": "a sleeveless undershirt", "Jeans": "a pair of jeans",
    "Shorts": "a pair of shorts", "Trousers": "a pair of trousers", "Track Pants": "a pair of track pants",
    "Leggings": "leggings", "Capris": "capri pants", "Skirts": "a skirt", "Dresses": "a dress",
    "Sarees": "a saree", "Casual Shoes": "casual shoes", "Sports Shoes": "sports shoes",
    "Formal Shoes": "formal leather shoes", "Heels": "high heels", "Flats": "flat shoes", "Sandals": "sandals",
    "Flip Flops": "flip flops", "Handbags": "a handbag", "Backpacks": "a backpack", "Clutches": "a clutch bag",
    "Wallets": "a wallet", "Belts": "a belt", "Caps": "a cap", "Scarves": "a scarf", "Stoles": "a stole",
    "Ties": "a necktie", "Socks": "socks", "Sunglasses": "sunglasses", "Earrings": "earrings",
    "Nightdress": "a nightdress", "Night suits": "pajamas",
}

# %%
styles = pd.read_csv(ROOT / "data" / "raw" / "styles.csv", on_bad_lines="skip")
styles["season_label"] = styles["season"].map({"Summer": "ete", "Winter": "hiver", "Fall": "mi_saison", "Spring": "mi_saison"})
subset = styles[styles["articleType"].isin(TYPE_PROMPTS)]
print(f"{len(subset)} rows over {subset['articleType'].nunique()} article types")


def leaning(column: str, classes: list[str]) -> np.ndarray:
    """Per type: P(class | type) / P(class), renormalized to sum to 1 (a posterior under a uniform prior)."""
    base = subset[column].value_counts(normalize=True).reindex(classes).fillna(1e-6)
    out = np.zeros((len(TYPE_PROMPTS), len(classes)))
    for i, article_type in enumerate(TYPE_PROMPTS):
        counts = subset[subset["articleType"] == article_type][column].value_counts().reindex(classes).fillna(0) + 1
        ratio = (counts / counts.sum()) / base
        out[i] = ratio / ratio.sum()
    return out


season = leaning("season_label", SEASONS)
usage = leaning("usage", USAGES)

# %%
payload = {
    "seasons": SEASONS,
    "usages": USAGES,
    "types": [
        {"article_type": t, "prompt": TYPE_PROMPTS[t], "season": season[i].round(4).tolist(), "usage": usage[i].round(4).tolist()}
        for i, t in enumerate(TYPE_PROMPTS)
    ],
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
print(f"wrote {OUT} ({len(payload['types'])} types)")

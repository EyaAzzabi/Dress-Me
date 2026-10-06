"""Nettoyage et harmonisation des données vers la taxonomie DressMe.

Taxonomie DressMe (libellés métier en français) :
    haut, bas, robe, veste, chaussures, sac, accessoire, hors_perimetre

Origine : les mappings Fashion Product Images / Clothing Dataset Full / Polyvore
viennent du notebook de l'équipe
(01_data_understanding_exploration_transformation (1).ipynb, src/preprocessing.py),
copiés ici tels quels pour servir de source commune. Les mappings Hamadi Abid et
Barsha (catalogue tunisien scrapé, voir ml/scraping/) ont été ajoutés pour réconcilier
la troisième taxonomie encore manquante (voir ml/data/DATA_DICTIONARY.md).
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

DRESSME_CATEGORIES = ["haut", "bas", "robe", "veste", "chaussures", "sac", "accessoire"]
OUT_OF_SCOPE = "hors_perimetre"

# --------------------------------------------------------------------------- #
# Taxonomie — Fashion Product Images (articleType prioritaire, puis subCategory)
# --------------------------------------------------------------------------- #
FASHION_ARTICLE_TO_DRESSME = {
    # vestes / couches extérieures
    "Jackets": "veste", "Blazers": "veste", "Rain Jacket": "veste", "Nehru Jackets": "veste",
    "Waistcoat": "veste", "Shrug": "veste", "Sweaters": "haut", "Sweatshirts": "haut",
    # une-pièce
    "Dresses": "robe", "Jumpsuit": "robe", "Rompers": "robe", "Sarees": "robe",
    "Lehenga Choli": "robe", "Kurtas": "haut", "Kurtis": "haut", "Tunics": "haut",
}
FASHION_SUBCATEGORY_TO_DRESSME = {
    "Topwear": "haut", "Bottomwear": "bas", "Dress": "robe", "Saree": "robe",
    "Apparel Set": "robe", "Shoes": "chaussures", "Sandal": "chaussures", "Flip Flops": "chaussures",
    "Bags": "sac", "Wallets": "accessoire", "Belts": "accessoire", "Watches": "accessoire",
    "Jewellery": "accessoire", "Eyewear": "accessoire", "Headwear": "accessoire",
    "Scarves": "accessoire", "Ties": "accessoire", "Cufflinks": "accessoire", "Gloves": "accessoire",
    "Mufflers": "accessoire", "Stoles": "accessoire", "Accessories": "accessoire",
    "Socks": OUT_OF_SCOPE, "Innerwear": OUT_OF_SCOPE, "Loungewear and Nightwear": OUT_OF_SCOPE,
}

# --------------------------------------------------------------------------- #
# Taxonomie — Clothing Dataset Full (label)
# --------------------------------------------------------------------------- #
CLOTHING_LABEL_TO_DRESSME = {
    "T-Shirt": "haut", "Longsleeve": "haut", "Shirt": "haut", "Polo": "haut", "Top": "haut",
    "Blouse": "haut", "Hoodie": "haut", "Undershirt": OUT_OF_SCOPE, "Body": "robe",
    "Pants": "bas", "Shorts": "bas", "Skirt": "bas", "Dress": "robe",
    "Outwear": "veste", "Blazer": "veste", "Shoes": "chaussures", "Hat": "accessoire",
    "Not sure": OUT_OF_SCOPE, "Other": OUT_OF_SCOPE, "Skip": OUT_OF_SCOPE,
}

# --------------------------------------------------------------------------- #
# Taxonomie — Polyvore (catégorie sémantique, puis mots-clés du titre)
# --------------------------------------------------------------------------- #
POLYVORE_CATEGORY_TO_DRESSME = {
    "tops": "haut", "bottoms": "bas", "all-body": "robe", "outerwear": "veste",
    "shoes": "chaussures", "bags": "sac", "jewellery": "accessoire", "accessories": "accessoire",
    "sunglasses": "accessoire", "hats": "accessoire", "scarves": "accessoire",
}
KEYWORDS_TO_DRESSME = [
    # English + French (Tunisian store titles are often one or the other, sometimes mixed).
    # "robe" is included despite English ambiguity (bathrobe vs. dress) — real evidence
    # across several French-titled Tunisian catalogs (Kontakt: 103 occurrences, almost
    # all genuine dresses) shows it's net-positive for this project's actual brand mix.
    ("veste", ["jacket", "coat", "blazer", "parka", "trench", "cardigan", "vest", "puffer",
               "manteau", "kimono", "surchemise", "bombers", "poncho"]),
    ("robe", ["dress", "jumpsuit", "romper", "playsuit", "gown", "abaya", "robe", "body", "jebba"]),
    ("bas", ["jeans", "pants", "trousers", "skirt", "shorts", "leggings", "chino",
             "pantalon", "jean", "jupe", "short", "jogger", "legging", "cargo"]),
    ("chaussures", ["shoe", "sneaker", "boot", "heel", "sandal", "pump", "loafer", "flat"]),
    ("sac", ["bag", "tote", "clutch", "backpack", "purse", "handbag", "sac", "cabas"]),
    ("accessoire", ["necklace", "earring", "bracelet", "ring", "watch", "sunglasses", "hat",
                    "scarf", "belt", "cap", "beanie", "collier"]),
    ("haut", ["top", "shirt", "blouse", "tee", "t-shirt", "sweater", "hoodie", "tank", "camisole",
              "polo", "sweatshirt", "pullover", "knit", "chemise", "pull", "sweat", "débardeur",
              "t-loose"]),
]

# --------------------------------------------------------------------------- #
# Taxonomie — Hamadi Abid (catalogue tunisien scrapé, champ `subcategory`)
# --------------------------------------------------------------------------- #
# Construit à partir des 83 paires (category, subcategory) réellement présentes dans
# ml/data/raw/tunisian_catalog/hamadi_abid.csv (voir ml/data/DATA_DICTIONARY.md).
# Mêmes conventions que ci-dessus : un ensemble coordonné (haut+bas) -> "robe" comme
# "Apparel Set" ; sous-vêtements/pyjamas/linge de maison -> hors_perimetre.
HAMADI_ABID_SUBCATEGORY_TO_DRESSME = {
    # accessoires
    "banane": "sac", "casquette": "accessoire", "ceinture": "accessoire", "chapeau": "accessoire",
    "chaussette": OUT_OF_SCOPE, "cravate": "accessoire", "porte-feuille": "accessoire",
    "sac-à-main": "sac", "sac-de-plage": "sac",
    # chaussures
    "basket": "chaussures", "derby": "chaussures", "escarpin": "chaussures", "mocassin": "chaussures",
    "mules": "chaussures", "sandale": "chaussures", "slip-on": "chaussures", "tennis": "chaussures",
    "tongs": "chaussures",
    # hauts
    "blouse-mc": "haut", "chemise-mc": "haut", "chemise-ml": "haut", "liquette-ml": "haut",
    "top": "haut", "top-": "haut", "top-basic": "haut", "tunique-ml": "haut",
    "polo-mc": "haut", "polo-ml": "haut", "pull-basic-ml": "haut", "pull-fantaisie-mc": "haut",
    "pull-fantaisie-ml": "haut", "sweat-capuche": "haut", "sweat-shirt": "haut",
    "sweat-zippe": "haut", "sweat-zippe-": "haut", "t-shirt-basic-mc": "haut",
    "t-shirt-fantaisie-mc": "haut", "t-shirt-fantaisie-mc-": "haut", "t-shirt-fantaisie-ml": "haut",
    "debardeur": "haut", "debardeur-basic": "haut",
    # bas
    "pantalon": "bas", "pantalon-": "bas", "jupe-courte": "bas", "jupe-midi": "bas",
    "jupe-short": "bas", "cycliste": "bas", "chino": "bas", "jogger": "bas",
    "pantalon-5-poches": "bas", "pantalon-formel": "bas", "bermuda": "bas", "jort": "bas",
    "pantacourt": "bas", "short": "bas", "legging": "bas",
    # robes / ensembles coordonnés (même convention que "Apparel Set" -> robe)
    "combinaison": "robe", "body-ml": "robe",
    "ensemble-cycliste": "robe", "ensemble-pantalon": "robe", "ensemble-short": "robe",
    "jogging": "robe", "ensemble-legging": "robe",
    "robe-courte": "robe", "robe-longue": "robe", "robe-midi": "robe",
    # vestes
    "costume": "veste", "gilet-court": "veste", "gilet-long": "veste", "kimino": "veste",
    # hors périmètre (sous-vêtements, nuit, linge de maison, parfum, bébé/écolier)
    "sortie-de-bain": OUT_OF_SCOPE, "coussin-et-couverture": OUT_OF_SCOPE,
    "couverture-et-jouet": OUT_OF_SCOPE, "couverture-poncho": OUT_OF_SCOPE,
    "parfums": OUT_OF_SCOPE, "pyjama-pantalon": OUT_OF_SCOPE, "knite-boxer": OUT_OF_SCOPE,
    "shorty": OUT_OF_SCOPE, "slip": OUT_OF_SCOPE, "brassiere": OUT_OF_SCOPE,
    # grenouillere (baby onesie) and tablier-college/ecolier (school smock) were
    # previously forced into robe/veste for taxonomy coverage, but they're neither adult
    # fashion nor visually similar to those categories — out of scope is the honest label
    # (7 items total; see the linear-probe veste/robe review in DATA_DICTIONARY.md).
    "grenouillere": OUT_OF_SCOPE, "tablier-college": OUT_OF_SCOPE, "tablier-ecolier": OUT_OF_SCOPE,
}

# --------------------------------------------------------------------------- #
# Taxonomie — Barsha (catalogue tunisien scrapé, slug extrait de `source_url`)
# --------------------------------------------------------------------------- #
BARSHA_SLUG_TO_DRESSME = {
    "barsha-fragrances": OUT_OF_SCOPE, "barsha-fragrances-homme": OUT_OF_SCOPE,
    "chaussures-homme": "chaussures", "chaussures-femme": "chaussures",
    "jeans-homme": "bas", "jeans-femme": "bas",
    "t-shirts-homme": "haut", "t-shirts-femme": "haut",
    "chapeau-casquette-homme": "accessoire", "chapeau-casquette-femme": "accessoire",
}


# --------------------------------------------------------------------------- #
# Normalisation des couleurs → familles
# --------------------------------------------------------------------------- #
COLOR_FAMILIES = {
    "noir": ["black", "charcoal", "noir", "jeans noir", "black stone"],
    "blanc": ["white", "off white", "cream", "blanc", "ecru", "ivoire", "creme"],
    "gris": ["grey", "gray", "grey melange", "steel", "silver", "gris", "light grey",
             "dark grey", "grege", "heather grey", "heather dark grey", "heather meduim grey",
             "anthracite", "grey stone", "jeans gris"],
    "beige": ["beige", "khaki", "tan", "nude", "skin", "taupe", "mushroom brown", "camel",
              "kaki", "beige clair"],
    "marron": ["brown", "coffee brown", "bronze", "copper", "rust", "marron", "coffee",
               "dark brown"],
    "rouge": ["red", "maroon", "burgundy", "bordeau"],
    "rose": ["pink", "rose", "magenta", "peach", "fushia", "coral", "pastel pink",
             "light pink", "powder pink", "rose bebe", "rose indien"],
    "orange": ["orange"],
    "jaune": ["yellow", "mustard", "gold", "jaune", "pastel yellow"],
    "vert": ["green", "olive", "sea green", "lime green", "fluorescent green", "light green",
             "acid green", "acacia"],
    "bleu": ["blue", "navy blue", "navy", "teal", "turquoise blue", "light blue", "dark blue",
             "medium blue", "jeans", "jeans stone", "bleach", "blue denim", "raw",
             "jeans dirty", "blue stone", "jeans snow", "blue acid wash", "aqua",
             "dirty light blue", "dirty blue", "pastel blue", "jeans bleach", "stone blue",
             "sky blue", "stripe blue", "dirty bleach", "acid wash", "blue duck", "dust blue",
             "bleu aqua"],
    "violet": ["purple", "lavender", "mauve", "lavande", "parme", "lilac"],
    "multicolore": ["multi", "multi-colors"],
    "metallique": ["metallic"],
}
_COLOR_LOOKUP = {name: family for family, names in COLOR_FAMILIES.items() for name in names}

# Scraped "color" values that aren't actually colors (e.g. the color-swatch slot was empty
# or mislabeled for these products) — honestly reported as missing, not guessed.
_NOT_A_COLOR = {"parfum", "pack 1", "pack 2"}


def normalize_color(value) -> str | float:
    """'Navy Blue' → 'bleu'. Valeur inconnue → 'autre', valeur manquante/non-couleur → NaN."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return np.nan
    key = str(value).strip().lower()
    if not key or key in _NOT_A_COLOR:
        return np.nan
    return _COLOR_LOOKUP.get(key, "autre")


# Words/phrases from COLOR_FAMILIES too ambiguous to trust as a free-text substring match
# (fine as an exact value in a structured `colors` field, risky inside a product title):
# "jeans"/"jean*" names the garment (a pair of jeans), not necessarily a blue one; "raw"
# and "multi" are common words unrelated to color in most titles; "skin" is more often
# "skincare" in a fashion/beauty title than a color.
_TEXT_COLOR_EXCLUDE = {
    "jeans", "jeans noir", "jeans gris", "jeans stone", "jeans dirty", "jeans snow",
    "jeans bleach", "raw", "multi", "skin",
}
# Longest phrase first, so "navy blue" matches before the standalone "navy"/"blue" would.
_TEXT_COLOR_WORDS = sorted(
    ((w, f) for w, f in _COLOR_LOOKUP.items() if w not in _TEXT_COLOR_EXCLUDE),
    key=lambda pair: len(pair[0]), reverse=True,
)


def map_color_from_text(text: str | float) -> str | float:
    """Best-effort color extraction from a free-text product name/title, for sources
    (Polyvore) that have no structured color field at all. Reuses COLOR_FAMILIES — the
    same vocabulary already validated on Kaggle/Tunisian `colors_raw` values — rather
    than inventing a parallel list. Coverage is necessarily partial, like `material`."""
    if not isinstance(text, str):
        return pd.NA
    lowered = f" {text.lower()} "
    for word, family in _TEXT_COLOR_WORDS:
        if f" {word} " in lowered:
            return family
    return pd.NA


def map_keywords(text: str | float) -> str:
    if not isinstance(text, str):
        return OUT_OF_SCOPE
    lowered = f" {text.lower()} "
    for category, words in KEYWORDS_TO_DRESSME:
        if any(f" {w}" in lowered for w in words):
            return category
    return OUT_OF_SCOPE


# --------------------------------------------------------------------------- #
# `material` — no source has a dedicated field; extracted from free-text names
# --------------------------------------------------------------------------- #
# Real evidence before building this (counts of each term across product names/titles):
# Tunisian catalogs (9,208 names): cuir 195+13(leather), coton 182+4(cotton), laine
# 105+3(wool), satin 97, lin 87+11(linen), soie 63+8(silk), denim 63, dentelle 38+21(lace),
# velours 39+3(velvet), maille 23, jersey 11, viscose 7, acrylique 18. Polyvore (251k
# items, title/url_name): leather 25,624, lace 13,554, suede 10,148, denim 7,882, cotton
# 5,928, wool 5,542, silk 5,513, knit 5,376, velvet 3,214, cashmere 2,476, satin 2,794,
# jersey 1,875, linen 1,009. Kaggle (44,417 names): leather 723, jersey 173, lace 247,
# denim 80, knit 78, silk 144, cotton 137, velvet 54, suede 22. "jean"/"jeans" deliberately
# excluded — in French it names the garment (already a `bas` category keyword), not
# reliably the fabric, unlike the unambiguous "denim".
MATERIAL_KEYWORDS = [
    ("cuir", ["leather", "cuir"]),
    ("daim", ["suede", "daim"]),
    ("denim", ["denim"]),
    ("coton", ["cotton", "coton"]),
    ("laine", ["wool", "laine"]),
    ("cachemire", ["cashmere", "cachemire"]),
    ("soie", ["silk", "soie"]),
    ("lin", ["linen", "lin "]),
    ("velours", ["velvet", "velours"]),
    ("dentelle", ["lace", "dentelle"]),
    ("satin", ["satin"]),
    ("viscose", ["viscose"]),
    ("polyester", ["polyester"]),
    ("acrylique", ["acrylic", "acrylique"]),
    ("nylon", ["nylon"]),
    ("maille", ["knit", "jersey", "maille"]),
]


def map_material(text: str | float) -> str | float:
    """Best-effort material extraction from a free-text product name/title. No source has
    a dedicated material field; coverage is necessarily partial (only items whose name
    happens to mention fabric) — most items will get NaN, which is honest, not a bug."""
    if not isinstance(text, str):
        return pd.NA
    lowered = f" {text.lower()} "
    for material, words in MATERIAL_KEYWORDS:
        if any(f" {w}" in lowered for w in words):
            return material
    return pd.NA


def map_fashion_products(df: pd.DataFrame) -> pd.Series:
    by_article = df["articleType"].map(FASHION_ARTICLE_TO_DRESSME)
    by_sub = df["subCategory"].map(FASHION_SUBCATEGORY_TO_DRESSME)
    return by_article.fillna(by_sub).fillna(OUT_OF_SCOPE)


def map_clothing_full(df: pd.DataFrame) -> pd.Series:
    return df["label"].map(CLOTHING_LABEL_TO_DRESSME).fillna(OUT_OF_SCOPE)


def is_blank(series: pd.Series) -> pd.Series:
    """Vrai si la valeur est manquante ou ne contient que des espaces."""
    return series.isna() | series.astype(str).str.strip().eq("")


def polyvore_text(df: pd.DataFrame) -> pd.Series:
    """Texte descriptif d'un article Polyvore : `title`, ou `url_name` quand le titre est vide."""
    title = df["title"].where(~is_blank(df["title"]))
    url_name = df["url_name"].where(~is_blank(df["url_name"]))
    return title.fillna(url_name).fillna("")


def map_polyvore(df: pd.DataFrame) -> pd.Series:
    by_category = df["category"].astype(str).str.strip().str.lower().map(POLYVORE_CATEGORY_TO_DRESSME)
    by_text = polyvore_text(df).map(map_keywords).replace(OUT_OF_SCOPE, np.nan)
    return by_category.fillna(by_text).fillna(OUT_OF_SCOPE)


def map_hamadi_abid(df: pd.DataFrame) -> pd.Series:
    """Catalogue Hamadi Abid scrapé (ml/scraping/scrape_hamadi_abid.py) -> taxonomie DressMe."""
    return df["subcategory"].map(HAMADI_ABID_SUBCATEGORY_TO_DRESSME).fillna(OUT_OF_SCOPE)


def _barsha_slug(source_url: str) -> str:
    """'https://www.barsha.com.tn/fr/tn/5-chaussures-femme' -> 'chaussures-femme'."""
    tail = source_url.rstrip("/").split("/")[-1]
    return re.sub(r"^\d+-", "", tail)


def map_barsha(df: pd.DataFrame) -> pd.Series:
    """Catalogue Barsha scrapé (ml/scraping/scrape_barsha.py) -> taxonomie DressMe."""
    slugs = df["source_url"].astype(str).map(_barsha_slug)
    return slugs.map(BARSHA_SLUG_TO_DRESSME).fillna(OUT_OF_SCOPE)


def map_chedly_sisters(df: pd.DataFrame) -> pd.Series:
    """Catalogue Chedly Sisters scrapé (ml/scraping/scrape_chedly_sisters.py) -> taxonomie
    DressMe. No direct category field (Shopify's product_type is generic plumbing, not a
    garment category) — titles are descriptive English product names, so the existing
    keyword fallback (built for Polyvore's text field) applies directly.
    """
    return df["name"].map(map_keywords)


def map_noonclo(df: pd.DataFrame) -> pd.Series:
    """Catalogue Noonclo scrapé (ml/scraping/scrape_noonclo.py) -> taxonomie DressMe.
    Same mechanism as Chedly Sisters, but titles are mostly French — this is what drove
    adding French terms (pantalon, jean, jupe, chemise, pull, sweat, manteau, sac, ...)
    to KEYWORDS_TO_DRESSME, which also benefits any other French-titled source.
    """
    return df["name"].map(map_keywords)


def map_kontakt(df: pd.DataFrame) -> pd.Series:
    """Catalogue Kontakt scrapé (ml/scraping/scrape_kontakt.py) -> taxonomie DressMe.
    Largest Tunisian source by far (3063 products). Drove adding robe/body/débardeur/
    jogger/bombers/legging/cargo/collier to KEYWORDS_TO_DRESSME (word-frequency analysis
    over its hors_perimetre items, not guessed).
    """
    return df["name"].map(map_keywords)


def map_lyoum(df: pd.DataFrame) -> pd.Series:
    """Catalogue Lyoum scrapé (ml/scraping/scrape_lyoum.py) -> taxonomie DressMe. Lyoum is
    a lifestyle concept-store, not pure clothing (notebooks, beach towels/fouta also in
    the catalog) — a real hors_perimetre rate here is partly expected, not all a keyword
    gap. Drove adding "cabas" (tote bag) and "t-loose" (Lyoum's own loose-tee product line).
    """
    return df["name"].map(map_keywords)


def map_rooh_clothing(df: pd.DataFrame) -> pd.Series:
    """Catalogue Rooh Clothing scrapé (ml/scraping/scrape_rooh_clothing.py) -> taxonomie
    DressMe. Small catalog (9 products), all loungewear "Set" items — deliberately not
    guessed (see KEYWORDS_TO_DRESSME's skip of bare "set"), so this source is expected to
    be ~0% in-scope rather than a bug to chase.
    """
    return df["name"].map(map_keywords)


def map_myjebba(df: pd.DataFrame) -> pd.Series:
    """Catalogue MY JEBBA scrapé (ml/scraping/scrape_myjebba.py) -> taxonomie DressMe.
    Traditional Tunisian jebbas — "jebba" itself was missing from KEYWORDS_TO_DRESSME
    (every single product failed before the fix: 8.8% -> 100% in-scope after adding it).
    """
    return df["name"].map(map_keywords)


def map_ileycom(df: pd.DataFrame) -> pd.Series:
    """Catalogue Ileycom scrapé (ml/scraping/scrape_ileycom.py) -> taxonomie DressMe.
    Despite showing up in jebba searches, Ileycom is a broad Tunisian artisan marketplace
    (food — jam, vinegar; home decor; art; stationery — alongside some clothing/jewelry),
    not a dedicated clothing store. ~26% in-scope is a real reflection of that mix, not a
    keyword gap to chase further.
    """
    return df["name"].map(map_keywords)


def normalize_name(series: pd.Series) -> pd.Series:
    """Nom de produit normalisé (minuscules, espaces simples) pour regrouper les quasi-doublons."""
    return series.fillna("").astype(str).str.lower().str.replace(r"\s+", " ", regex=True).str.strip()


def missing_report(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """Valeurs manquantes et chaînes vides par colonne."""
    rows = []
    for column in df.columns:
        n_missing = int(df[column].isna().sum())
        textual = df[column].dtype == object or pd.api.types.is_string_dtype(df[column])
        n_blank = int(is_blank(df[column]).sum() - n_missing) if textual else 0
        rows.append({"source": name, "colonne": column, "manquantes": n_missing, "vides": n_blank,
                     "pct_manquantes_ou_vides": round(100 * (n_missing + n_blank) / max(len(df), 1), 2)})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Qualité des images
# --------------------------------------------------------------------------- #
def check_image(path: str | Path) -> dict:
    """Ouvre l'image sans la charger entièrement : existence, lisibilité, taille."""
    from PIL import Image

    path = Path(path)
    if not path.exists():
        return {"image_ok": False, "problem": "absente", "width": np.nan, "height": np.nan}
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
            mode = image.mode
        return {"image_ok": True, "problem": None, "width": width, "height": height, "mode": mode}
    except Exception as error:  # noqa: BLE001
        return {"image_ok": False, "problem": f"illisible ({type(error).__name__})", "width": np.nan, "height": np.nan}


def check_images(paths: pd.Series) -> pd.DataFrame:
    return pd.DataFrame([check_image(p) for p in paths], index=paths.index)


# --------------------------------------------------------------------------- #
# Split stratifié sans fuite
# --------------------------------------------------------------------------- #
def stratified_split(df: pd.DataFrame, label_col: str, group_col: str | None = None,
                     val_size: float = 0.15, test_size: float = 0.15, seed: int = 42,
                     min_count: int = 10) -> pd.Series:
    """Renvoie une série 'train' / 'val' / 'test'.

    - Les classes trop rares (< min_count) sont exclues ('exclu') : impossible de les stratifier.
    - Si `group_col` est fourni (ex. même produit photographié plusieurs fois, même tenue),
      tous les éléments d'un groupe restent dans le même split → pas de fuite de données.
    """
    from sklearn.model_selection import StratifiedGroupKFold, train_test_split

    split = pd.Series("exclu", index=df.index, dtype="object")
    counts = df[label_col].value_counts()
    keep = df[label_col].isin(counts[counts >= min_count].index)
    data = df[keep]

    if group_col is None:
        train_idx, temp_idx = train_test_split(
            data.index, test_size=val_size + test_size, stratify=data[label_col], random_state=seed
        )
        temp = data.loc[temp_idx]
        val_idx, test_idx = train_test_split(
            temp.index, test_size=test_size / (val_size + test_size), stratify=temp[label_col], random_state=seed
        )
    else:
        n_folds = round(1 / test_size)
        folds = StratifiedGroupKFold(n_splits=n_folds, shuffle=True, random_state=seed)
        rest_pos, test_pos = next(folds.split(data, data[label_col], data[group_col]))
        test_idx = data.index[test_pos]
        rest = data.iloc[rest_pos]
        n_folds_val = max(2, round((1 - test_size) / val_size))
        folds_val = StratifiedGroupKFold(n_splits=n_folds_val, shuffle=True, random_state=seed)
        train_pos, val_pos = next(folds_val.split(rest, rest[label_col], rest[group_col]))
        train_idx, val_idx = rest.index[train_pos], rest.index[val_pos]

    split.loc[train_idx] = "train"
    split.loc[val_idx] = "val"
    split.loc[test_idx] = "test"
    return split


def assert_no_leakage(df: pd.DataFrame, split_col: str, key_col: str) -> None:
    """Vérifie qu'une même clé (ex. image, produit, tenue) n'apparaît pas dans deux splits."""
    per_key = df[df[split_col] != "exclu"].groupby(key_col)[split_col].nunique()
    leaking = per_key[per_key > 1]
    if len(leaking):
        raise AssertionError(f"{len(leaking)} clés présentes dans plusieurs splits (ex. {list(leaking.index[:5])})")

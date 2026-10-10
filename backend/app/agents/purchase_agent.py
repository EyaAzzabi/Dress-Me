import math
from typing import Any

import numpy as np

from app.agents.base import BaseAgent
from app.ml import compatibility_model, purchase_calibration
from app.models.clothing_item import ClothingItem
from app.services.catalog_index import CatalogIndex
from app.services.ecommerce import EcommerceService

# Cosine similarity between FashionCLIP embeddings of the same category. On the
# catalog, a random same-category pair is above 0.79 only 1 % of the time.
DUPLICATE_SIMILARITY = 0.95  # near-identical embedding -> likely the exact same item
REDUNDANT_SIMILARITY = 0.80  # below this, the candidate brings something new

# Two pieces "go together" when the compatibility model scores them better than this
# share of random pairings of real garments (app/ml/purchase_calibration.py).
MATCH_PERCENTILE = 0.5

FACTOR_WEIGHTS = {"versatility": 0.40, "uniqueness": 0.25, "style_fit": 0.20, "price": 0.15}
RECOMMENDED_SCORE = 65
THINK_TWICE_SCORE = 45
NO_EVIDENCE_SCORE = RECOMMENDED_SCORE  # empty wardrobe and no price: nothing argues against it

BASE_PARTNERS = {"haut": "bas", "bas": "haut"}
OPTIONAL_CATEGORIES = ["veste", "chaussures", "sac", "accessoire"]

PRICE_NEIGHBOURS = 20
ALTERNATIVES_LIMIT = 4
OUTFIT_EXAMPLES_LIMIT = 3

# Brands are matched on the piece itself, pulled towards the wardrobe's style
# centroid: a brand for this piece *and* for the person who'll wear it.
BRAND_STYLE_BLEND = 0.3
BRANDS_LIMIT = 4

# Rough wears per year of a piece that goes with everything, per category — the
# versatility factor scales it (a piece that matches nothing gets worn far less).
# Orders of magnitude, not measurements: enough to compare purchases by cost per wear.
TYPICAL_WEARS_PER_YEAR = {
    "haut": 30, "bas": 45, "robe": 12, "veste": 40, "chaussures": 80, "sac": 90, "accessoire": 40,
}
DUPLICATE_WEAR_SHARE = 0.3  # a near-twin of an owned piece shares its wears with it
GOOD_COST_PER_WEAR = 2.0  # TND
HIGH_COST_PER_WEAR = 6.0

# (demonstrative, indefinite) French forms per category, for the explanation text.
CATEGORY_WORDING = {
    "haut": ("Ce haut", "un haut"), "bas": ("Ce bas", "un bas"), "robe": ("Cette robe", "une robe"),
    "veste": ("Cette veste", "une veste"), "chaussures": ("Ces chaussures", "des chaussures"),
    "sac": ("Ce sac", "un sac"), "accessoire": ("Cet accessoire", "un accessoire"),
}


class PurchaseAgent(BaseAgent):
    """Decides whether a potential purchase is worth it, from four explainable
    signals combined into a 0-100 score:

    - versatility: how many complete outfits the piece unlocks with the existing
      wardrobe, each pairing scored by the compatibility model trained on 68,306 real
      Polyvore outfits (app/ml/compatibility_model.py), calibrated against random
      pairings of real garments (app/ml/purchase_calibration.py);
    - uniqueness: 1 - redundancy with the closest same-category item already owned
      (FashionCLIP cosine similarity);
    - style_fit: similarity to the centroid of the wardrobe's embeddings — the user's
      visual style as a single vector — calibrated the same way;
    - price: where the given price sits among the prices of the visually closest
      products of the Tunisian catalog (CatalogIndex).

    Factors without evidence (empty wardrobe, no price given) are left out and the
    remaining weights renormalized, rather than guessed. A near-identical item already
    owned overrides the score: buying it twice is never recommended.

    Alongside the verdict: the estimated cost per wear, visually similar products of
    the Tunisian catalog (linked to their page on the brand's site), and the Tunisian
    brands whose products look closest to the piece and to the wardrobe's style.

    Never persists the candidate's embedding — it isn't owned yet.
    """

    name = "purchase_agent"

    def __init__(self) -> None:
        self.catalog_index = CatalogIndex()
        self.ecommerce_service = EcommerceService()

    def run(
        self,
        *,
        attributes: dict[str, Any],
        wardrobe_items: list[ClothingItem],
        embeddings: dict[str, list[float]],
        price: float | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        category = attributes["category"]
        item_summary = {
            "category": category,
            "color": attributes["colors"][0] if attributes["colors"] else None,
            "pattern": attributes.get("pattern"),
            "style": attributes.get("style"),
        }
        if category == "hors_perimetre":
            return {
                **_empty_result(item_summary),
                "verdict": "not_recommended",
                "explanation": "Cette photo ne ressemble pas à un vêtement — essaie une photo de l'article seul.",
            }

        candidate = np.asarray(attributes["embedding"], dtype=float)
        owned = [(item, np.asarray(embeddings[str(item.id)], dtype=float))
                 for item in wardrobe_items if str(item.id) in embeddings]

        duplicates = _find_duplicates(candidate, category, owned)
        outfits = _unlocked_outfits(candidate, category, owned)
        neighbours = self.catalog_index.search(candidate, category=category, limit=PRICE_NEIGHBOURS)
        price_insight = _price_insight(price, neighbours)

        versatility = _versatility_factor(outfits, category, owned)
        factors = [f for f in (
            versatility,
            _uniqueness_factor(duplicates, category, owned),
            _style_fit_factor(candidate, owned),
            _price_factor(price_insight),
        ) if f is not None]

        if factors:
            total_weight = sum(f["weight"] for f in factors)
            for f in factors:
                f["weight"] = round(f["weight"] / total_weight, 3)
            score = round(100 * sum(f["score"] * f["weight"] for f in factors))
        else:
            score = NO_EVIDENCE_SCORE

        is_duplicate = bool(duplicates) and duplicates[0]["similarity"] >= DUPLICATE_SIMILARITY
        if is_duplicate:
            verdict = "not_recommended"
            score = min(score, THINK_TWICE_SCORE - 1)
        elif score >= RECOMMENDED_SCORE:
            verdict = "recommended"
        elif score >= THINK_TWICE_SCORE:
            verdict = "think_twice"
        else:
            verdict = "not_recommended"

        return {
            "verdict": verdict,
            "score": score,
            "compatibility_score": round(score / 100, 2),
            "explanation": _explain(verdict, category, is_duplicate, outfits, owned, price_insight),
            "item": item_summary,
            "factors": factors,
            "outfits_unlocked": len(outfits),
            "outfit_examples": outfits[:OUTFIT_EXAMPLES_LIMIT],
            "duplicates": duplicates,
            "similar_item_ids": [d["id"] for d in duplicates],
            "price_insight": price_insight,
            "cost_per_wear": _cost_per_wear(price, category, versatility, is_duplicate),
            "catalog_alternatives": self._alternatives(candidate, item_summary, neighbours, price),
            "tunisian_brands": self._brands(candidate, category, owned),
        }

    def _brands(self, candidate, category, owned) -> list[dict]:
        query = candidate
        if owned:
            centroid = np.mean([vec for _, vec in owned], axis=0)
            query = (1 - BRAND_STYLE_BLEND) * candidate + BRAND_STYLE_BLEND * centroid / max(np.linalg.norm(centroid), 1e-12)
            query = query / max(np.linalg.norm(query), 1e-12)
        return self.catalog_index.brand_affinity(query, category=category)[:BRANDS_LIMIT]

    def _alternatives(self, candidate, item_summary, neighbours, price) -> list[dict]:
        if not neighbours:
            # No visual index built: fall back to the keyword search over product names.
            return self.ecommerce_service.search_products(
                item_summary["color"] or "", category=item_summary["category"], limit=ALTERNATIVES_LIMIT
            )
        alternatives = [m.to_dict() for m in neighbours]
        for alt in alternatives:
            alt["cheaper"] = price is not None and alt["price"] is not None and alt["price"] < price
        if price is not None:
            # Visually close *and* cheaper first — the actionable "buy this instead".
            alternatives.sort(key=lambda a: (not a["cheaper"], -a["similarity"]))
        return alternatives[:ALTERNATIVES_LIMIT]


def _empty_result(item_summary: dict) -> dict:
    return {
        "score": 0, "compatibility_score": 0.0, "item": item_summary, "factors": [],
        "outfits_unlocked": 0, "outfit_examples": [], "duplicates": [], "similar_item_ids": [],
        "price_insight": None, "cost_per_wear": None, "catalog_alternatives": [], "tunisian_brands": [],
    }


def _item_ref(item: ClothingItem) -> dict:
    return {"id": str(item.id), "image_url": item.image_url, "category": item.category}


def _find_duplicates(candidate, category, owned) -> list[dict]:
    same_category = [(item, float(vec @ candidate)) for item, vec in owned if item.category == category]
    same_category.sort(key=lambda pair: pair[1], reverse=True)
    return [{**_item_ref(item), "similarity": round(sim, 3)}
            for item, sim in same_category if sim >= REDUNDANT_SIMILARITY][:3]


def _unlocked_outfits(candidate, category, owned) -> list[dict]:
    """Complete outfits the candidate would be part of. Each pairing with the
    candidate is scored by the Polyvore compatibility model, then calibrated to a
    percentile of random real pairings; an outfit is kept only if every piece clears
    MATCH_PERCENTILE, and scored by the mean percentile."""
    def match(vec, kind: str) -> float:
        raw = compatibility_model.pair_compatibility(candidate, vec)
        return purchase_calibration.percentile(kind, raw)

    by_category: dict[str, list] = {}
    for item, vec in owned:
        by_category.setdefault(item.category, []).append((item, vec))

    outfits = []
    if category in BASE_PARTNERS:
        # A haut needs a bas (and vice versa): each compatible partner is a new outfit.
        for item, vec in by_category.get(BASE_PARTNERS[category], []):
            score = match(vec, "base_compatibility")
            if score >= MATCH_PERCENTILE:
                outfits.append({"items": [_item_ref(item)], "score": score})
    elif category == "robe":
        # A robe is an outfit on its own; each compatible optional piece styles it differently.
        for slot in OPTIONAL_CATEGORIES:
            for item, vec in by_category.get(slot, []):
                score = match(vec, "optional_compatibility")
                if score >= MATCH_PERCENTILE:
                    outfits.append({"items": [_item_ref(item)], "score": score})
    else:
        # Optional piece (veste, chaussures, ...): which existing outfits does it complete?
        bases = [[h, b] for h in by_category.get("haut", []) for b in by_category.get("bas", [])]
        bases += [[r] for r in by_category.get("robe", [])]
        for base in bases:
            scores = [match(vec, "optional_compatibility") for _, vec in base]
            if min(scores) >= MATCH_PERCENTILE:
                outfits.append({"items": [_item_ref(item) for item, _ in base],
                                "score": float(np.mean(scores))})

    outfits.sort(key=lambda o: o["score"], reverse=True)
    for outfit in outfits:
        outfit["score"] = round(outfit["score"], 3)
    return outfits


def _complementary_count(category, owned) -> int:
    if category in BASE_PARTNERS:
        return sum(1 for item, _ in owned if item.category == BASE_PARTNERS[category])
    if category == "robe":
        return sum(1 for item, _ in owned if item.category in OPTIONAL_CATEGORIES)
    hauts = sum(1 for item, _ in owned if item.category == "haut")
    bas = sum(1 for item, _ in owned if item.category == "bas")
    robes = sum(1 for item, _ in owned if item.category == "robe")
    return hauts * bas + robes


def _versatility_factor(outfits, category, owned) -> dict | None:
    possible = _complementary_count(category, owned)
    if possible == 0:
        return None
    n = len(outfits)
    # Half absolute (diminishing returns past a handful of outfits), half relative to
    # what the wardrobe could offer at most.
    score = 0.5 * (1 - math.exp(-n / 3)) + 0.5 * (n / possible)
    return {
        "key": "versatility", "label": "Polyvalence", "score": round(score, 3),
        "weight": FACTOR_WEIGHTS["versatility"],
        "detail": f"{n} tenue{'s' if n != 1 else ''} possible{'s' if n != 1 else ''} "
                  f"sur {possible} combinaison{'s' if possible != 1 else ''} testée{'s' if possible != 1 else ''}",
    }


def _uniqueness_factor(duplicates, category, owned) -> dict | None:
    if not any(item.category == category for item, _ in owned):
        return None
    closest = duplicates[0]["similarity"] if duplicates else None
    if closest is None:
        score, detail = 1.0, "Rien de similaire dans ta garde-robe"
    else:
        score = max(0.0, (DUPLICATE_SIMILARITY - closest) / (DUPLICATE_SIMILARITY - REDUNDANT_SIMILARITY))
        detail = f"Ressemble à {round(closest * 100)} % à une pièce que tu as déjà"
    return {"key": "uniqueness", "label": "Originalité", "score": round(min(score, 1.0), 3),
            "weight": FACTOR_WEIGHTS["uniqueness"], "detail": detail}


def _style_fit_factor(candidate, owned) -> dict | None:
    if not owned:
        return None
    centroid = np.mean([vec for _, vec in owned], axis=0)
    centroid /= max(np.linalg.norm(centroid), 1e-12)
    score = purchase_calibration.percentile("style_fit", float(centroid @ candidate))
    if score >= 0.66:
        detail = "Dans la lignée de ton style actuel"
    elif score >= 0.33:
        detail = "Proche de ton style, avec une touche nouvelle"
    else:
        detail = "Assez éloigné de ce que tu portes d'habitude"
    return {"key": "style_fit", "label": "Cohérence de style", "score": round(score, 3),
            "weight": FACTOR_WEIGHTS["style_fit"], "detail": detail}


def _price_insight(price, neighbours) -> dict | None:
    market = [m.price for m in neighbours if m.price is not None]
    if not market:
        return None
    median = float(np.median(market))
    insight = {"price": price, "market_median": round(median, 2),
               "market_min": round(min(market), 2), "market_max": round(max(market), 2),
               "sample_size": len(market), "percentile": None, "label": None}
    if price is not None:
        percentile = float(np.mean([p < price for p in market]))
        insight["percentile"] = round(percentile, 2)
        if price <= median * 0.9:
            insight["label"] = "bon_prix"
        elif price <= median * 1.25:
            insight["label"] = "prix_marche"
        else:
            insight["label"] = "cher"
    return insight


def _price_factor(price_insight) -> dict | None:
    if not price_insight or price_insight["percentile"] is None:
        return None
    pct = price_insight["percentile"]
    return {
        "key": "price", "label": "Prix", "score": round(1 - pct, 3), "weight": FACTOR_WEIGHTS["price"],
        "detail": f"Plus cher que {round(pct * 100)} % des articles similaires "
                  f"(médiane {price_insight['market_median']:.0f} TND)",
    }


def _cost_per_wear(price, category, versatility, is_duplicate) -> dict | None:
    """Price divided by an estimate of how often the piece will actually be worn in a
    year: the category's typical rate, scaled by versatility (0.5x for a piece that
    matches nothing, up to 1.5x for one that matches everything)."""
    if price is None or category not in TYPICAL_WEARS_PER_YEAR:
        return None
    scale = 0.5 + versatility["score"] if versatility else 1.0
    if is_duplicate:
        scale *= DUPLICATE_WEAR_SHARE
    wears = max(1, round(TYPICAL_WEARS_PER_YEAR[category] * scale))
    cost = price / wears
    label = "excellent" if cost <= GOOD_COST_PER_WEAR else "correct" if cost <= HIGH_COST_PER_WEAR else "eleve"
    return {"wears_per_year": wears, "cost_per_wear": round(cost, 2), "label": label}


def _explain(verdict, category, is_duplicate, outfits, owned, price_insight) -> str:
    this, one = CATEGORY_WORDING.get(category, ("Cet article", "un article"))
    if is_duplicate:
        return f"Tu as déjà {one} presque identique — garde ton budget pour autre chose."
    if not owned:
        return ("Ta garde-robe est encore vide : rien ne s'oppose à cet achat. "
                "Ajoute tes vêtements pour une analyse personnalisée.")

    parts = []
    n = len(outfits)
    plural = "s" if n > 1 else ""
    if n == 0:
        parts.append(f"{this} ne s'associe bien à aucune pièce de ta garde-robe pour l'instant.")
    elif category in BASE_PARTNERS:
        parts.append(f"{this} crée {n} nouvelle{plural} tenue{plural} avec ce que tu as déjà.")
    elif category == "robe":
        parts.append(f"{this} se porte avec {n} pièce{plural} de ta garde-robe.")
    else:
        parts.append(f"{this} complète {n} de tes tenues.")
    if price_insight and price_insight["label"] == "bon_prix":
        parts.append("Et c'est un bon prix par rapport au marché tunisien.")
    elif price_insight and price_insight["label"] == "cher":
        parts.append(f"Attention : plus cher que le marché (médiane {price_insight['market_median']:.0f} TND).")

    lead = {"recommended": "Bon achat !", "think_twice": "À réfléchir.", "not_recommended": "Pas convaincant."}[verdict]
    return " ".join([lead, *parts])

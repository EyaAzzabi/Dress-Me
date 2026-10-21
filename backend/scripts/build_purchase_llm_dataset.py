"""Gold tool-calling trajectories for LoRA fine-tuning the Purchase LLM.

Each example is a full sandbox dialogue: the model must emit <tool_call> tags in
the teacher order, then a <final> explanation that only uses the tool results.
Run from backend/:  python -m scripts.build_purchase_llm_dataset
"""

from __future__ import annotations

import json
from pathlib import Path

from app.ml.purchase_llm import teacher_trajectory

OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "purchase_llm_sft.jsonl"

TEACHER_ORDER = [
    "inspect_wardrobe",
    "search_tunisian_catalog",
    "compare_market_price",
    "rank_tunisian_brands",
    "estimate_cost_per_wear",
]


def _case(task, tools, text) -> dict:
    return {"messages": teacher_trajectory(task, {k: tools[k] for k in TEACHER_ORDER if k in tools}, text)}


def examples() -> list[dict]:
    rows = []
    rows.append(_case(
        {"category": "hors_perimetre", "color": None, "price": None, "wardrobe_size": 0},
        {},
        "Cette photo ne ressemble pas à un vêtement. Reprends une photo de l'article seul.",
    ))
    for category, label in [("haut", "ce haut"), ("bas", "ce bas"), ("robe", "cette robe"),
                            ("veste", "cette veste"), ("chaussures", "ces chaussures"), ("sac", "ce sac")]:
        rows.append(_case(
            {"category": category, "color": "noir", "price": 59, "wardrobe_size": 0},
            {
                "inspect_wardrobe": {"wardrobe_size": 0, "duplicates": [], "outfits_unlocked": 0,
                                     "versatility": None, "uniqueness": None, "style_fit": None},
                "search_tunisian_catalog": [{"name": "Tee essential", "brand": "Kontakt", "price": 49, "similarity": 0.81}],
                "compare_market_price": {"price": 59, "market_median": 70, "label": "bon_prix", "percentile": 0.2},
                "rank_tunisian_brands": [{"name": "Kontakt", "affinity": 0.71}],
                "estimate_cost_per_wear": {"wears_per_year": 30, "cost_per_wear": 1.97, "label": "excellent"},
            },
            f"Ta garde-robe est encore vide, rien ne s'oppose à {label}. "
            f"À 59 TND tu es sous la médiane du marché tunisien (70 TND). Kontakt a des pièces proches.",
        ))
        rows.append(_case(
            {"category": category, "color": "beige", "price": 89, "wardrobe_size": 8},
            {
                "inspect_wardrobe": {"wardrobe_size": 8, "duplicates": [{"similarity": 0.96, "category": category}],
                                     "outfits_unlocked": 2, "versatility": {"score": 0.4},
                                     "uniqueness": {"score": 0.05, "detail": "Ressemble à 96 %"},
                                     "style_fit": {"score": 0.7}},
                "search_tunisian_catalog": [{"name": "Modèle proche", "brand": "Barsha", "price": 65, "similarity": 0.78}],
                "compare_market_price": {"price": 89, "market_median": 70, "label": "cher", "percentile": 0.8},
                "rank_tunisian_brands": [{"name": "Barsha", "affinity": 0.68}],
                "estimate_cost_per_wear": {"wears_per_year": 8, "cost_per_wear": 11.1, "label": "eleve"},
            },
            f"Tu as déjà une pièce presque identique : garde ton budget. "
            f"À 89 TND tu es au-dessus du marché (médiane 70 TND) — Barsha a un modèle proche à 65 TND.",
        ))
        rows.append(_case(
            {"category": category, "color": "blanc", "price": 75, "wardrobe_size": 12},
            {
                "inspect_wardrobe": {"wardrobe_size": 12, "duplicates": [], "outfits_unlocked": 5,
                                     "versatility": {"score": 0.74, "detail": "5 tenues possibles"},
                                     "uniqueness": {"score": 0.9}, "style_fit": {"score": 0.7}},
                "search_tunisian_catalog": [{"name": "Linen shirt", "brand": "Chedly Sisters", "price": 79, "similarity": 0.74}],
                "compare_market_price": {"price": 75, "market_median": 80, "label": "prix_marche", "percentile": 0.35},
                "rank_tunisian_brands": [{"name": "Chedly Sisters", "affinity": 0.73}, {"name": "Lyoum", "affinity": 0.66}],
                "estimate_cost_per_wear": {"wears_per_year": 36, "cost_per_wear": 2.08, "label": "correct"},
            },
            f"Bon achat : {label} crée 5 tenues avec ce que tu as déjà et reste dans ton style. "
            f"Le prix (75 TND) est dans la norme du marché tunisien (médiane 80 TND).",
        ))
        rows.append(_case(
            {"category": category, "color": "rouge", "price": 95, "wardrobe_size": 6},
            {
                "inspect_wardrobe": {"wardrobe_size": 6, "duplicates": [], "outfits_unlocked": 0,
                                     "versatility": {"score": 0.2}, "uniqueness": {"score": 0.85},
                                     "style_fit": {"score": 0.28}},
                "search_tunisian_catalog": [{"name": "Pièce proche", "brand": "Noonclo", "price": 55, "similarity": 0.7}],
                "compare_market_price": {"price": 95, "market_median": 60, "label": "cher", "percentile": 0.7},
                "rank_tunisian_brands": [{"name": "Noonclo", "affinity": 0.64}],
                "estimate_cost_per_wear": {"wears_per_year": 12, "cost_per_wear": 7.9, "label": "eleve"},
            },
            f"À réfléchir : {label} ne s'associe bien à aucune pièce de ta garde-robe, "
            f"et 95 TND dépasse la médiane (60 TND). Noonclo a une option vers 55 TND.",
        ))
    return rows


def main() -> None:
    rows = examples()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    print(f"{len(rows)} tool-calling trajectories -> {OUT}")


if __name__ == "__main__":
    main()

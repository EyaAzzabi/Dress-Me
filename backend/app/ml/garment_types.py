"""Season and style read through the garment type.

FashionCLIP is weak on abstract prompts ("a lightweight summer garment", "a formal item
of clothing") but good on concrete ones ("a pair of shorts", "a knitted sweater"). So
the photo is first classified into ~40 garment types, and each type carries a learned
leaning toward a season and a usage (style):

    P(season | photo) = sum over types of P(type | photo) * leaning(type -> season)

The leanings come from the 44k labeled rows of Fashion Product Images, as likelihood
ratios (the dataset's own skew toward Summer/Casual is divided out) — see
ml/notebooks/12_garment_type_priors.py, which also records the measured gains and limits.
Artifact: artifacts/garment_type_priors.json. When it is missing, `available()` is False
and the Vision Agent falls back to its zero-shot prompts.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

# [Oral] EXEMPLE CONCRET de la formule P(saison | photo) = somme sur les types de P(type | photo) x tendance(type -> saison) :
#   photo d'un pull -> FashionCLIP dit "a knitted sweater" à 85 %.
#   La tendance apprise pour "Sweaters" est : été 5 %, hiver 11 %, mi-saison 85 %.
#   On fait la moyenne pondérée sur les ~40 types -> saison = mi_saison avec une forte probabilité.
# Pourquoi passer par le type ? Parce que FashionCLIP reconnaît très bien "un short" ou "un pull" mais mal
# "un vêtement d'été" (46 % de justesse avec cette phrase, moins que répondre toujours "été").
# Le fichier JSON (garment_type_priors.json) est fabriqué par ml/notebooks/12_garment_type_priors.py à partir
# de 44 000 produits étiquetés (Fashion Product Images). Il ne contient aucun poids de réseau, juste des tableaux.
PRIORS_PATH = Path(__file__).resolve().parent / "artifacts" / "garment_type_priors.json"
TYPE_PROMPT_TEMPLATE = "a photo of {}"


# [Oral] Vrai si le fichier de priors existe ; sinon vision_model retombe sur le zero-shot direct.
def available() -> bool:
    return PRIORS_PATH.exists()


@lru_cache
def _priors() -> dict:
    return json.loads(PRIORS_PATH.read_text(encoding="utf-8"))


@lru_cache
def _type_text_vectors() -> np.ndarray:
    from app.ml import vision_model

    return vision_model._embed_texts([TYPE_PROMPT_TEMPLATE.format(t["prompt"]) for t in _priors()["types"]])


# [Oral] ÉTAPE 1 : probabilité de chacun des ~40 types ("a t-shirt", "a pair of jeans", "high heels"...),
# par le même zero-shot que dans vision_model (similarité photo/phrase puis softmax).
def type_posterior(embedding: np.ndarray) -> np.ndarray:
    """Zero-shot probability of each garment type for one L2-normalized embedding."""
    from app.ml import vision_model

    model, _, _ = vision_model._load_fashionclip()
    scale = float(model.logit_scale.exp().item())
    logits = scale * embedding @ _type_text_vectors().T
    probs = np.exp(logits - logits.max())
    return probs / probs.sum()


# [Oral] ÉTAPE 2 : produit matriciel (probabilités des types) x (tendance de chaque type) = probabilité de
# chaque saison ou style. "key" choisit le tableau : "season" ou "usage".
def _mix(embedding: np.ndarray, key: str, classes_key: str) -> dict[str, float]:
    leaning = np.array([t[key] for t in _priors()["types"]])
    mixed = type_posterior(embedding) @ leaning
    return dict(zip(_priors()[classes_key], (float(p) for p in mixed)))


def season_posterior(embedding: np.ndarray) -> dict[str, float]:
    return _mix(embedding, "season", "seasons")


def usage_posterior(embedding: np.ndarray) -> dict[str, float]:
    """Casual / Sports / Ethnic / Formal — the only styles with enough labels to learn."""
    return _mix(embedding, "usage", "usages")

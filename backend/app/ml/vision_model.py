"""FashionCLIP-based inference for the Vision Agent.

Self-contained here (no import of the top-level ml/ folder) because the backend is
built as its own Docker image from backend/ alone (see infra/docker-compose.yml) — ml/
is a separate research/data-pipeline folder not included in that build context.

- `category`: two stages. (1) the 8-class linear probe (artifacts/category_classifier.joblib,
  ml/notebooks/08_category_classifier.py) says whether this is clothing at all
  (hors_perimetre); (2) a dedicated 7-class RBF-SVM on garments only
  (artifacts/garment_category_classifier.joblib, ml/notebooks/11_garment_category_head.py)
  names the category. On the held-out Tunisian garment photos the gate keeps, it is 87.0%
  accurate (macro-F1 0.871 over the 7 garment labels) vs 85.2% (0.851) for the 8-class probe:
  a modest gain (+1.8 points, paired-bootstrap 95% CI [-0.4, +4.2] — not statistically
  significant), clear on robes (F1 0.77 -> 0.86), slightly negative on vestes (0.76 -> 0.71).
  Falls back to the probe if the second artifact is missing.
- `season` / `style`: read through the garment type (app/ml/garment_types.py): FashionCLIP
  recognizes "a pair of shorts" far better than "a summer garment", and each type carries a
  learned leaning toward a season and a usage. Season is only *suggested* when confident
  (SEASON_MIN_CONFIDENCE); style is Casual / Sports / Ethnic / Formal — the only styles with
  enough labels to learn. Without the priors artifact, both fall back to zero-shot prompts.
- `color` / `pattern`: zero-shot classification (no labeled training data of the right kind
  exists). Prompt ensembling, synonyms and a probe trained on the Tunisian color labels were
  all tried and none beat the plain prompt reliably (ml/reports/vision_agent_evaluation.md).
- Every attribute comes with a confidence. `pattern`/`style`/`season` come back as None
  below their minimum confidence rather than storing a near-random guess; `colors` lists up
  to MAX_COLORS labels above COLOR_SECONDARY_MIN_PROB.
- The raw embedding is also returned for similarity search (Purchase Agent / Pinecone).
"""

# =====================================================================================
# [Oral] GUIDE DE LECTURE (français) — le cœur du Vision Agent
#
# IDÉE CENTRALE : on transforme la photo en une liste de 512 nombres (un "embedding") avec le modèle
# FashionCLIP. Deux photos de vêtements semblables donnent deux listes proches. Ensuite, chaque attribut
# est deviné à partir de cet embedding, SANS ré-analyser la photo :
#
#   photo --FashionCLIP--> embedding (512 nombres) --+--> catégorie   (2 classifieurs entraînés)
#                                                    +--> couleurs    (zero-shot : comparaison à des phrases)
#                                                    +--> motif       (zero-shot)
#                                                    +--> style/saison (via le TYPE de vêtement, garment_types.py)
#
# Ordre du fichier : constantes (phrases et seuils) -> chargement des modèles -> embed_image_bytes /
# _embed_texts -> _zero_shot_probs -> predict_category / colors / pattern / style / season ->
# analyze_image (assemble tout, c'est LA fonction appelée par le reste de l'application).
# =====================================================================================

from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.ml import garment_types, vision_llm

# [Oral] FashionCLIP = CLIP (OpenAI) réentraîné sur des photos de mode. Point clé : il place les IMAGES
# et les TEXTES dans le même espace de 512 nombres, donc on peut mesurer "cette photo ressemble-t-elle
# à la phrase 'a striped garment' ?". Rien n'est réentraîné ici : on utilise le modèle tel quel ("gelé").
FASHIONCLIP_REPO = "patrickjohncyh/fashion-clip"
# [Oral] Deux fichiers entraînés par nous (dossier artifacts/) : le "portier" (est-ce un vêtement ?)
# et la "tête garment" (quelle catégorie ?). Voir plus bas predict_category.
CATEGORY_CLASSIFIER_PATH = Path(__file__).resolve().parent / "artifacts" / "category_classifier.joblib"
GARMENT_CLASSIFIER_PATH = Path(__file__).resolve().parent / "artifacts" / "garment_category_classifier.joblib"

# [Oral] ZERO-SHOT : pour chaque valeur possible on écrit une phrase. La valeur retenue est celle dont la
# phrase ressemble le plus à la photo — sans aucune donnée d'entraînement. Clé = ce qu'on stocke en base
# (français) ; valeur = la phrase anglaise donnée au modèle (CLIP comprend mieux l'anglais).
COLOR_PROMPTS = {
    "noir": "black", "blanc": "white", "gris": "grey", "beige": "beige", "marron": "brown",
    "rouge": "red", "rose": "pink", "orange": "orange", "jaune": "yellow", "vert": "green",
    "bleu": "blue", "violet": "purple",
}
STYLE_PROMPTS = {
    "Casual": "casual", "Formal": "formal", "Sports": "sporty", "Ethnic": "traditional ethnic",
    "Party": "party", "Smart Casual": "smart casual", "Travel": "travel", "Home": "loungewear",
}
# Weak labels, not ground truth — no source labels pattern at all (see
# ml/data/DATA_DICTIONARY.md). Same prompts validated in ml/notebooks/07_pattern_weak_labels.py.
PATTERN_PROMPTS = {
    "uni": "a plain solid-color garment with no pattern",
    "rayures": "a striped garment",
    "a_pois": "a polka dot garment",
    "fleuri": "a floral print garment",
    "carreaux": "a checkered or plaid garment",
    "imprime_animal": "an animal print garment such as leopard or snake print",
    "brode": "an embroidered garment with decorative stitching",
    "geometrique": "a garment with a geometric or abstract print",
}


SEASON_PROMPTS = {
    "ete": "a lightweight summer garment",
    "hiver": "a warm heavy winter garment",
    "mi_saison": "a medium-weight spring or autumn garment",
}

# [Oral] SEUILS DE CONFIANCE — sous le seuil, on préfère répondre "je ne sais pas" (None) plutôt que
# d'enregistrer une valeur quasi au hasard. Ils ont été choisis en MESURANT sur des photos étiquetées
# (voir ml/reports/vision_agent_evaluation.md), pas au feeling.
# Below this the category is more guess than reading — typically a photo of several pieces
# at once (a full outfit), which the classifier wasn't trained on (it saw one item per photo).
# Measured end to end on the held-out Tunisian garment photos (735, catalog-style, one item each,
# ml/notebooks/13_vision_agent_evaluation.py): at 0.60 it asks the user to confirm 9.8% of
# garments — 4.6% of the correct predictions and 40.2% of the wrong ones; what gets through is
# 90.3% accurate. Users confirm a held-back category in one tap, so the false alarms are cheap.
# Real phone photos may score differently than catalog shots — revisit with real uploads.
CATEGORY_MIN_CONFIDENCE = 0.60
MAX_COLORS = 3
COLOR_SECONDARY_MIN_PROB = 0.25
PATTERN_MIN_CONFIDENCE = 0.30  # weak labels: below this, report no pattern
# Measured on the 300 labeled Kaggle photos with the type-based method (model in garment_types.py):
# season at >= 0.60 answers 21% of photos with 64% accuracy (the majority class gets 41% on that
# subset); below it, no better than always answering the majority — so no suggestion at all.
# Style at >= 0.70 answers 60% of photos with 0.90 balanced accuracy over the 4 learnable styles.
STYLE_MIN_CONFIDENCE = 0.70  # type-based. (Zero-shot fallback uses ZERO_SHOT_STYLE_MIN_CONFIDENCE.)
SEASON_MIN_CONFIDENCE = 0.60  # below this, don't suggest a season at all
ZERO_SHOT_STYLE_MIN_CONFIDENCE = 0.25
ZERO_SHOT_SEASON_MIN_CONFIDENCE = 0.50


# [Oral] Utilise la carte graphique si elle existe, sinon le processeur (notre machine : processeur).
def _get_device() -> str:
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


# [Oral] @lru_cache = "mémoriser le résultat" : le modèle (~600 Mo) est chargé UNE seule fois, à la première
# photo, puis réutilisé. Le recharger à chaque photo rendrait l'application inutilisable.
@lru_cache
def _load_fashionclip():
    from transformers import CLIPModel, CLIPProcessor

    device = _get_device()
    model = CLIPModel.from_pretrained(FASHIONCLIP_REPO).to(device).eval()
    processor = CLIPProcessor.from_pretrained(FASHIONCLIP_REPO)
    return model, processor, device


# [Oral] Charge le "portier" (régression logistique, 8 classes dont hors_perimetre), entraîné par
# ml/notebooks/08_category_classifier.py. Si le fichier manque, on lève une erreur explicite.
@lru_cache
def _load_category_classifier():
    import joblib

    if not CATEGORY_CLASSIFIER_PATH.exists():
        raise FileNotFoundError(
            f"{CATEGORY_CLASSIFIER_PATH} missing — run "
            "ml/notebooks/08_category_classifier.py and copy its output here."
        )
    return joblib.load(CATEGORY_CLASSIFIER_PATH)


@lru_cache
def _load_garment_classifier():
    """The 7-class garment head, or None when the artifact isn't there (older checkout)."""
    import joblib

    if not GARMENT_CLASSIFIER_PATH.exists():
        return None
    return joblib.load(GARMENT_CLASSIFIER_PATH)


# [Oral] Normalisation L2 : on ramène chaque vecteur à une longueur de 1. Conséquence utile : le produit
# scalaire de deux vecteurs normalisés = leur similarité cosinus (1 = identiques, 0 = sans rapport).
def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return vectors / np.clip(norms, 1e-12, None)


def embed_image_bytes(image_bytes: bytes) -> np.ndarray:
    """Returns a single L2-normalized 512-d FashionCLIP embedding for one image."""
    import torch
    from PIL import Image

    # [Oral] PHOTO -> EMBEDDING : on ouvre l'image, le processeur la redimensionne (224x224) et la
    # normalise, puis le "vision transformer" de FashionCLIP la transforme en 512 nombres.
    model, processor, device = _load_fashionclip()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    inputs = processor(images=[image], return_tensors="pt").to(device)
    with torch.no_grad():  # [Oral] pas d'apprentissage ici : on calcule seulement (plus rapide, moins de mémoire)
        pooled = model.vision_model(pixel_values=inputs["pixel_values"]).pooler_output
        projected = model.visual_projection(pooled)
    return _normalize(projected.float().cpu().numpy())[0]


# [Oral] Même chose pour du TEXTE : une phrase devient 512 nombres dans le MÊME espace que les images.
def _embed_texts(texts: list[str]) -> np.ndarray:
    import torch

    model, processor, device = _load_fashionclip()
    inputs = processor(text=texts, return_tensors="pt", padding=True, truncation=True).to(device)
    with torch.no_grad():
        pooled = model.text_model(
            input_ids=inputs["input_ids"], attention_mask=inputs["attention_mask"]
        ).pooler_output
        projected = model.text_projection(pooled)
    return _normalize(projected.float().cpu().numpy())


# [Oral] Les phrases (ex. les 12 couleurs) ne changent jamais : on les encode une fois et on garde le résultat.
@lru_cache
def _prompt_text_vectors(prompts: tuple[tuple[str, str], ...], template: str) -> np.ndarray:
    texts = [template.format(value) for _, value in prompts]
    return _embed_texts(texts)


# [Oral] LE ZERO-SHOT EN 4 LIGNES — c'est la fonction à savoir expliquer :
#   1. on encode les phrases candidates ("a photo of a red item of clothing", ...) ;
#   2. on calcule la similarité (produit scalaire) entre la photo et chaque phrase ;
#   3. on multiplie par logit_scale (appris par CLIP : rend les écarts plus nets) ;
#   4. softmax : on transforme ces scores en probabilités qui font 100 % au total.
# Résultat : {"rouge": 0.81, "rose": 0.09, ...}. La plus grande probabilité = la réponse ET la confiance.
def _zero_shot_probs(embedding: np.ndarray, prompts: dict[str, str], template: str) -> dict[str, float]:
    model, _, _ = _load_fashionclip()
    items = tuple(prompts.items())
    text_vectors = _prompt_text_vectors(items, template)  # étape 1
    scale = float(model.logit_scale.exp().item())
    logits = scale * embedding @ text_vectors.T  # étapes 2 et 3
    probs = np.exp(logits - logits.max())  # softmax (on retire le max pour éviter les dépassements numériques)
    probs /= probs.sum()  # étape 4
    return dict(zip(prompts, (float(p) for p in probs)))


# [Oral] Renvoie (meilleure valeur, sa probabilité) — la probabilité sert de "confiance".
def _top(probs: dict[str, float]) -> tuple[str, float]:
    label = max(probs, key=probs.get)
    return label, probs[label]


# [Oral] CATÉGORIE EN DEUX ÉTAPES (seule partie réellement ENTRAÎNÉE par nous, sur ~8 900 photos de boutiques
# tunisiennes, jeu découpé en entraînement / validation / test) :
#   étape 1, le "portier" : est-ce un vêtement ? (8 classes, dont hors_perimetre = produit non vestimentaire)
#   étape 2, la "tête garment" (SVM) : si oui, quelle catégorie parmi les 7 ? (haut, bas, robe, veste,
#            chaussures, sac, accessoire). Elle n'a jamais vu de non-vêtement, d'où la séparation.
# Gain mesuré de l'étape 2 : +1,8 point (85,2 % -> 87,0 %), pas statistiquement significatif — on le dit.
def predict_category(embedding: np.ndarray) -> tuple[str, float]:
    gate = _load_category_classifier()
    x = embedding.reshape(1, -1)
    label = gate.predict(x)[0]
    # A linear probe normally exposes predict_proba; if it doesn't, report full
    # confidence rather than inventing a number.
    confidence = float(gate.predict_proba(x).max()) if hasattr(gate, "predict_proba") else 1.0
    if label == "hors_perimetre":
        return label, confidence  # not clothing: the garment head never saw such photos

    # [Oral] Étape 2. Repli : si le fichier de la tête est absent, on garde la réponse du portier.
    head = _load_garment_classifier()
    if head is None:
        return label, confidence
    probabilities = head.predict_proba(x)[0]
    best = int(probabilities.argmax())
    return str(head.classes_[best]), float(probabilities[best])


def predict_colors(embedding: np.ndarray) -> tuple[list[str], float]:
    """Dominant color first, plus up to MAX_COLORS-1 more that are clearly present."""
    # [Oral] COULEURS : zero-shot sur 12 couleurs. On garde la meilleure, plus jusqu'à 2 autres si leur
    # probabilité dépasse 25 % (vêtement bicolore). Précision mesurée : ~70 % — c'est la limite du zero-shot.
    probs = _zero_shot_probs(embedding, COLOR_PROMPTS, template="a photo of a {} item of clothing")
    ranked = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)
    colors = [ranked[0][0]] + [
        label for label, p in ranked[1:MAX_COLORS] if p >= COLOR_SECONDARY_MIN_PROB
    ]
    return colors, ranked[0][1]


# [Oral] MOTIF : zero-shot sur 8 motifs (uni, rayures, fleuri...). Pas de vérité terrain pour mesurer la
# justesse (aucune base n'étiquette le motif) : on le signale, et on renvoie None sous 30 % de confiance.
def predict_pattern(embedding: np.ndarray) -> tuple[str | None, float]:
    label, confidence = _top(_zero_shot_probs(embedding, PATTERN_PROMPTS, template="{}"))
    return (label if confidence >= PATTERN_MIN_CONFIDENCE else None), confidence


# [Oral] STYLE : méthode principale = via le TYPE de vêtement (garment_types.py). Repli : zero-shot direct si
# le fichier de priors est absent. Sous le seuil de confiance -> None, et c'est alors le LLM (OpenAI, option
# désactivée par défaut) qui peut donner un avis, dans analyze_image ci-dessous.
def predict_style(embedding: np.ndarray) -> tuple[str | None, float]:
    if garment_types.available():
        label, confidence = _top(garment_types.usage_posterior(embedding))
        return (label if confidence >= STYLE_MIN_CONFIDENCE else None), confidence
    label, confidence = _top(
        _zero_shot_probs(embedding, STYLE_PROMPTS, template="a photo of a {} item of clothing")
    )
    return (label if confidence >= ZERO_SHOT_STYLE_MIN_CONFIDENCE else None), confidence


# [Oral] SAISON : même principe que le style. Limite honnête : la saison n'est pas vraiment "visible" sur
# une photo ; on ne la SUGGÈRE donc qu'avec ≥ 60 % de confiance, et l'utilisateur la confirme dans l'app
# (badge "À confirmer").
def predict_season(embedding: np.ndarray) -> tuple[str | None, float]:
    if garment_types.available():
        label, confidence = _top(garment_types.season_posterior(embedding))
        return (label if confidence >= SEASON_MIN_CONFIDENCE else None), confidence
    label, confidence = _top(_zero_shot_probs(embedding, SEASON_PROMPTS, template="{}"))
    return (label if confidence >= ZERO_SHOT_SEASON_MIN_CONFIDENCE else None), confidence


def analyze_image(image_bytes: bytes) -> dict:
    """Runs the full Vision Agent pipeline on one image: category, colors, pattern,
    style, a suggested season, per-attribute confidence, and the raw embedding (for
    similarity search / Pinecone storage)."""
    # [Oral] FONCTION PRINCIPALE — appelée par VisionAgent.run et par le WardrobeIngestionAgent.
    # 1) UNE seule fois : photo -> embedding. Tous les attributs ci-dessous réutilisent ce même embedding.
    embedding = embed_image_bytes(image_bytes)
    # 2) un prédicteur par attribut ; chacun renvoie (valeur, confiance).
    category, category_conf = predict_category(embedding)
    colors, color_conf = predict_colors(embedding)
    pattern, pattern_conf = predict_pattern(embedding)
    style, style_conf = predict_style(embedding)
    season, season_conf = predict_season(embedding)
    # 3) Avis optionnel d'OpenAI, SEULEMENT pour le style et SEULEMENT si FashionCLIP hésite (None).
    #    On a mesuré qu'il n'aide pas pour la catégorie, la couleur ni la saison, donc on ne le consulte pas.
    style_source = "fashionclip"  # traçabilité : d'où vient la valeur du style
    if style is None and vision_llm.available():
        # FashionCLIP isn't sure of the style: ask the OpenAI vision model (off by default; see
        # app/ml/vision_llm.py). Measured on the 76 labeled Kaggle photos FashionCLIP left empty:
        # 89.5% vs 39.5% (95% CI of the difference [+0.36, +0.65]) — but those photos are 80% Casual,
        # so against "always Casual" the real gain is ~9 points, concentrated on Sports.
        # Category, color and season are NOT delegated: it was no better there.
        opinion = vision_llm.describe_image(image_bytes)
        if opinion and opinion["style"]:
            style, style_source = opinion["style"], "openai"
    # 4) Résultat. "category_uncertain" = confiance < 60 % : la route demandera alors à l'utilisateur de
    #    CONFIRMER la catégorie (cas typique : photo de plusieurs vêtements). "confidence" est stocké en base,
    #    et "embedding" part dans Pinecone (recherche de similarité, recommandations, achat).
    return {
        "category": category,
        "colors": colors,
        "pattern": pattern,
        "style": style,
        "season": season,
        "style_source": style_source,
        "category_uncertain": category_conf < CATEGORY_MIN_CONFIDENCE,
        "confidence": {
            "category": round(category_conf, 3),
            "colors": round(color_conf, 3),
            "pattern": round(pattern_conf, 3),
            "style": round(style_conf, 3),
            "season": round(season_conf, 3),
        },
        "embedding": embedding,
    }

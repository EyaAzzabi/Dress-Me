"""Optional second opinion on a garment photo from an OpenAI vision model.

FashionCLIP (app/ml/vision_model.py) decides everything by default. This module is only
asked when it is unsure, and only if VISION_LLM_ENABLED=true. It sends the photo to OpenAI,
so it is off by default and every answer is validated against the project's own vocabularies:
anything outside them is dropped, and any failure returns None so the caller keeps
FashionCLIP's answer.

The prompt follows CRISPE:
  C — Capacity & Role   who the model is, what it is capable of
  R — Insight (Résumé)  the context and the facts it needs (the vocabularies, what a catalog
                        photo looks like, what the downstream app does with the answer)
  I — Statement         the exact task
  S — Personality       how to answer (terse, literal, honest about doubt)
  P — Experiment        what to do when unsure, and the output contract
(CRISPE = Capacity/Role, Insight, Statement, Personality, Experiment.)
"""

from __future__ import annotations

import base64
import io
import json
import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# [Oral] RÔLE — avis OPTIONNEL d'un LLM multimodal (GPT-4o-mini) quand FashionCLIP hésite sur le STYLE.
# Désactivé par défaut (VISION_LLM_ENABLED=false) : il envoie la photo à OpenAI. Le prompt suit la méthode
# CRISPE (5 sections : Capacity/Role, Insight, Statement, Personality, Experiment). Les prompts sont
# VERSIONNÉS (v1...v5) et GELÉS une fois mesurés ; un test vérifie qu'on ne les modifie pas par accident.
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
CATEGORIES = ["haut", "bas", "robe", "veste", "chaussures", "sac", "accessoire", "hors_perimetre"]
COLORS = ["noir", "blanc", "gris", "beige", "marron", "rouge", "rose", "orange", "jaune", "vert", "bleu", "violet"]
PATTERNS = ["uni", "rayures", "a_pois", "fleuri", "carreaux", "imprime_animal", "brode", "geometrique"]
STYLES = ["Casual", "Sports", "Ethnic", "Formal"]
SEASONS = ["ete", "hiver", "mi_saison"]
MAX_COLORS = 3
MAX_SIDE = 768  # pixels; the image is re-encoded below this before being sent (cost and privacy)

# [Oral] v1 = le prompt CRISPE de départ. Lire ses 5 sections : Rôle (qui est le modèle), Insight (le contexte
# et les listes de valeurs autorisées), Statement (la tâche), Personality (prudent et littéral), Experiment
# (format JSON exigé et que faire en cas de doute).
PROMPT_V1 = f"""\
# Capacity and role
You are the visual-recognition module of DressMe, a wardrobe app for people in Tunisia. You can
look at one photo and describe the clothing item in it with the app's fixed vocabulary.

# Insight
- The photo is usually a catalog-style picture of ONE item, but users also upload photos of a person
  wearing a full outfit, or of things that are not clothes.
- Your answer fills database fields, so every value must come from the lists below, spelled exactly:
  category: {", ".join(CATEGORIES)}  (hors_perimetre = not a garment, shoe, bag or accessory)
  colors: up to {MAX_COLORS} of {", ".join(COLORS)}, dominant color first
  pattern: {", ".join(PATTERNS)}
  style: {", ".join(STYLES)}
  season: {", ".join(SEASONS)}  (what it is suited to wear in, judged from fabric weight and cut)
- A "haut" is a top or shirt; a "veste" is an outer layer (jacket, coat, blazer, cardigan worn open).
  A skirt or trousers is "bas". A one-piece garment is "robe".

# Statement
Describe the main clothing item in the photo. If a person wears several pieces, describe the piece
that is most prominent and set "multiple_items" to true.

# Personality
Literal and conservative. Describe only what is visible. Never guess a brand, a price or a fabric you
cannot see. Prefer null to a doubtful value.

# Experiment
Reply with ONE JSON object and nothing else, with exactly these keys:
{{"category": <string>, "colors": [<string>], "pattern": <string or null>, "style": <string or null>,
  "season": <string or null>, "multiple_items": <true or false>, "confidence": <number 0 to 1>}}
"confidence" is how sure you are of "category". If the photo is blurry, cropped or ambiguous, lower it
and use null for the fields you cannot judge."""


# --------------------------------------------------------------------------------------------
# v2 — same CRISPE skeleton, with decision rules per attribute (what to look at, tie-breaks).
# v3 — v2 with two fixes found on the DEV half: "multiple_items" was sometimes written as the
#      category (the whole answer was then rejected), and "Sports" was over-called on everyday
#      sneakers (7 Casual items labeled Sports).
# v5 — v1 plus ONLY the "multiple_items is never a category" fix (is the long rule list worth it?).
# v4 — v3 plus a one-sentence visible-evidence "reasoning" written BEFORE the answer
#      (a light chain of thought: costs ~40 more output tokens per call).
# Versions are frozen once measured: never edit a published version, add a new one.
# ml/notebooks/15_vision_prompt_versions.py measures them all on the same photos.
# --------------------------------------------------------------------------------------------
_RULES_V2 = f"""\
# Capacity and role
You are the visual-recognition module of DressMe, a wardrobe app used in Tunisia (catalogs of
Tunisian shops: everyday wear, sportswear, formal wear and traditional pieces such as jebba, kaftan,
fouta or chechia). You look at ONE photo and describe the main clothing item with a fixed vocabulary.

# Insight
Your answer fills database fields, so every value must come from these lists, spelled exactly:
  category: {", ".join(CATEGORIES)}
  colors:   up to {MAX_COLORS} of {", ".join(COLORS)}
  pattern:  {", ".join(PATTERNS)}
  style:    {", ".join(STYLES)}
  season:   {", ".join(SEASONS)}

Decision rules — apply them in order, they settle the usual confusions:
1. Subject. The photo may show a product alone, or a person wearing an outfit. Describe the single most
   prominent garment (the one covering most of the picture). If several pieces are worn, set
   "multiple_items" to true and describe the largest one. Ignore the person, the hanger, the shelf and
   the background — never report their colors.
2. Category.
   - hors_perimetre: anything that is not a garment, shoe, bag or wearable accessory (cosmetics, perfume,
     boxes, home items, a landscape, a face close-up, a screenshot).
   - haut: shirt, t-shirt, blouse, sweater, hoodie, tank top, polo. veste: an outer layer worn over
     another garment (jacket, coat, blazer, open cardigan, gilet).
   - bas: trousers, jeans, shorts, skirt, leggings. robe: ONE piece covering torso and legs (dress,
     jumpsuit, kaftan, jebba as a long single garment).
   - chaussures: any shoe, boot, sandal, slipper. sac: bag, backpack, wallet, clutch.
   - accessoire: belt, scarf, hat/cap, sunglasses, jewelry, watch, tie, gloves.
3. Colors. List colors by the share of the GARMENT's surface, dominant first, at most {MAX_COLORS}; skip a
   color that covers under ~15%. Map to the nearest listed color: navy/denim -> bleu, cream/ivory -> blanc,
   khaki/camel/tan/nude -> beige, burgundy -> rouge, olive/mint -> vert, charcoal/silver -> gris,
   fuchsia/coral -> rose, lavender -> violet. Never output a color outside the list.
4. Pattern. "uni" only if the fabric is one flat color. Logos or a small chest print on a plain garment are
   still "uni"; a large all-over print is "geometrique" (abstract), "fleuri", "rayures"... "brode" means
   visible embroidery or decorative stitching.
5. Style (what occasion the piece is made for, not how it is worn).
   Sports: athletic wear, sneakers/running shoes, tracksuits, jerseys. Formal: suits, blazers, dress shirts,
   tailored trousers, leather dress shoes, evening dresses. Ethnic: traditional or regional garments
   (jebba, kaftan, fouta, saree, kurta, embroidered traditional wear). Casual: everything else.
   Use null only if you genuinely cannot tell.
6. Season (from fabric weight and cut that you can SEE). ete: thin or light fabric, short sleeves, sleeveless,
   shorts, sandals, linen. hiver: knit/wool, thick or padded, fleece, long coats, boots, hoods. mi_saison:
   medium weight, long sleeves in light fabric, light jackets, denim. Use null if the photo does not show
   enough (e.g. a plain bag or a belt).

# Statement
Describe the main clothing item in the photo with the rules above.

# Personality
Literal, conservative, consistent. Describe only what is visible; never guess brand, price or fabric you
cannot see. Prefer null to a doubtful value.
"""

PROMPT_V2 = _RULES_V2 + """
# Experiment
Reply with ONE JSON object and nothing else, with exactly these keys:
{"category": <string>, "colors": [<string>], "pattern": <string or null>, "style": <string or null>,
 "season": <string or null>, "multiple_items": <true or false>, "confidence": <number 0 to 1>}
"confidence" is how sure you are of "category". If the photo is blurry, cropped or ambiguous, lower it
and use null for the fields you cannot judge."""

_RULES_V3 = _RULES_V2.replace(
    "   - accessoire: belt, scarf, hat/cap, sunglasses, jewelry, watch, tie, gloves.\n",
    "   - accessoire: belt, scarf, hat/cap, sunglasses, jewelry, watch, tie, gloves.\n"
    "   \"category\" is ALWAYS exactly one of the category list. \"multiple_items\" is a separate true/false field\n"
    "   and is NEVER a category: even for a photo of a whole outfit, name the category of the largest piece.\n",
).replace(
    "   Sports: athletic wear, sneakers/running shoes, tracksuits, jerseys. Formal:",
    "   Sports: clearly athletic items only (sportswear, tracksuits, jerseys, training leggings, running or\n"
    "   football shoes). Everyday sneakers, trainers and casual shoes are Casual. Formal:",
)
assert _RULES_V3 != _RULES_V2 and _RULES_V3.count("NEVER a category") == 1 and "clearly athletic" in _RULES_V3

_EXPERIMENT_PLAIN = """
# Experiment
Reply with ONE JSON object and nothing else, with exactly these keys:
{"category": <string>, "colors": [<string>], "pattern": <string or null>, "style": <string or null>,
 "season": <string or null>, "multiple_items": <true or false>, "confidence": <number 0 to 1>}
"confidence" is how sure you are of "category". If the photo is blurry, cropped or ambiguous, lower it
and use null for the fields you cannot judge."""

PROMPT_V3 = _RULES_V3 + _EXPERIMENT_PLAIN

PROMPT_V4 = _RULES_V3 + """
# Experiment
Reply with ONE JSON object and nothing else, with exactly these keys, in this order:
{"reasoning": <one short sentence naming what you actually see: garment, main colors, fabric/cut clues>,
 "category": <string>, "colors": [<string>], "pattern": <string or null>, "style": <string or null>,
 "season": <string or null>, "multiple_items": <true or false>, "confidence": <number 0 to 1>}
Write "reasoning" first and base every other field on it. "confidence" is how sure you are of "category";
if the photo is blurry, cropped or ambiguous, lower it and use null for the fields you cannot judge."""

PROMPT_V5 = PROMPT_V1.replace(
    'A one-piece garment is "robe".',
    'A one-piece garment is "robe". "multiple_items" is a separate true/false field and is never a category.',
)
assert PROMPT_V5 != PROMPT_V1

# [Oral] Registre des versions. Résultat de la comparaison (ml/reports/vision_prompt_versions.md) : v1 reste la
# meilleure pour le style ; les versions plus longues n'ont PAS amélioré ce cas d'usage.
PROMPTS = {"v1": PROMPT_V1, "v2": PROMPT_V2, "v3": PROMPT_V3, "v4": PROMPT_V4, "v5": PROMPT_V5}
DEFAULT_VERSION = "v1"  # the measured baseline; change only after ml/notebooks/15 shows a better one


# [Oral] Vrai seulement si l'option est activée ET une clé OpenAI est configurée (jamais d'appel par accident).
def available() -> bool:
    s = get_settings()
    return bool(s.vision_llm_enabled and s.openai_api_key)


# [Oral] Avant l'envoi : la photo est réduite à 768 px max et ré-encodée en JPEG (moins cher, plus rapide, et
# moins de données personnelles transmises). exif_transpose redresse les photos de téléphone tournées.
def _shrink_to_jpeg(image_bytes: bytes) -> bytes:
    from PIL import Image, ImageOps

    image = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=85)
    return out.getvalue()


# [Oral] SÉCURITÉ — on ne fait jamais confiance à la réponse d'un LLM : chaque valeur doit appartenir aux listes
# du projet (catégories, couleurs, motifs, styles, saisons), sinon elle est remplacée par None. Cas réel
# découvert en mesurant : sur une photo de tenue complète le modèle écrit category="multiple_items" ; on
# garde alors le reste de la réponse au lieu de tout jeter (échecs passés de 2-9 % à 0).
def _validated(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Keep only values from the project's vocabularies.

    A category outside the list is not fatal: the model often answers category="multiple_items" for a
    photo of a whole outfit (even when told not to), but its colors, style and season are still
    usable. The category becomes None (and multiple_items True) instead of the whole answer being
    thrown away. Callers must treat category None as "unknown"."""
    category = raw.get("category")
    multiple = bool(raw.get("multiple_items")) or category == "multiple_items"
    if category not in CATEGORIES:
        category = None
    if category is None and not isinstance(raw.get("colors"), list) and not raw.get("style"):
        return None  # nothing usable at all
    colors = [c for c in (raw.get("colors") or []) if c in COLORS][:MAX_COLORS]
    confidence = raw.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        confidence = 0.0
    return {
        "category": category,
        "colors": colors,
        "pattern": raw.get("pattern") if raw.get("pattern") in PATTERNS else None,
        "style": raw.get("style") if raw.get("style") in STYLES else None,
        "season": raw.get("season") if raw.get("season") in SEASONS else None,
        "multiple_items": multiple,
        "confidence": max(0.0, min(1.0, float(confidence))),
    }


# [Oral] Codes HTTP "réessayez" : délai dépassé (408), trop de requêtes (429), erreur côté serveur (5xx).
_TRANSIENT = {408, 429, 500, 502, 503, 504}


# [Oral] Un seul nouvel essai après une courte pause (1,5 s) en cas d'erreur passagère ; sinon on abandonne.
def _post_with_retry(url: str, **kwargs):
    """POST once more after a short pause on a timeout, a rate limit or a server error."""
    import time

    for attempt in (1, 2):
        try:
            response = httpx.post(url, **kwargs)
            if response.status_code in _TRANSIENT and attempt == 1:
                time.sleep(1.5)
                continue
            return response
        except httpx.TransportError:
            if attempt == 2:
                raise
            time.sleep(1.5)


# [Oral] FONCTION PRINCIPALE du module : image -> JSON validé, ou None au moindre problème (réseau, quota,
# JSON invalide). None signifie "garde la réponse de FashionCLIP" : l'application ne plante jamais à cause du LLM.
# temperature=0 -> réponses reproductibles ; detail="low" -> image à faible résolution (coût minimal).
def describe_image(image_bytes: bytes, version: str | None = None) -> dict[str, Any] | None:
    """Ask the vision model about one photo. None when disabled, unconfigured or on any failure.
    `version` picks a prompt from PROMPTS (default: settings.vision_llm_prompt_version)."""
    settings = get_settings()
    version = version or settings.vision_llm_prompt_version
    if version not in PROMPTS:
        logger.warning("unknown vision_llm_prompt_version %r; using %s", version, DEFAULT_VERSION)
        version = DEFAULT_VERSION
    if not (settings.vision_llm_enabled and settings.openai_api_key):
        return None
    try:
        jpeg = _shrink_to_jpeg(image_bytes)
        data_url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
        response = _post_with_retry(
            OPENAI_URL,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": settings.vision_llm_model,
                "temperature": 0,
                "max_tokens": 300,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": PROMPTS[version]},
                    {"role": "user", "content": [
                        {"type": "text", "text": "Describe the clothing item in this photo."},
                        {"type": "image_url", "image_url": {"url": data_url, "detail": "low"}},
                    ]},
                ],
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return _validated(json.loads(response.json()["choices"][0]["message"]["content"]))
    except Exception:  # noqa: BLE001 — network, quota, malformed JSON: the caller keeps FashionCLIP's answer
        logger.warning("vision_llm.describe_image failed; keeping FashionCLIP's answer", exc_info=True)
        return None

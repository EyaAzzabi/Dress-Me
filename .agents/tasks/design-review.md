# Revue de design — RecommendationAgent (axes fine-tuning / RAG / LLM)

Revue « fraîche » de `e:/Documents/Dress-Me/.agents/tasks/design.md` (Révision 2),
sans le contexte qui l'a produite. Chaque affirmation vérifiable a été confrontée au
source (backend + ml/). La Révision 2 traite réellement les 14 findings précédents
(vérifié point par point ci-dessous), mais introduit ou laisse 4 problèmes MEDIUM
bloquants et 6 NIT.

**Verdict : CHANGES_REQUESTED** — 0 HIGH, 4 MEDIUM, 6 NIT. La mécanique du verdict
compte les HIGH+MEDIUM ; > 0 ⇒ CHANGES_REQUESTED.

---

## Findings

### 1. (MEDIUM) `ctx_vec` non calculé côté orchestrateur + `weather_band` passé à `run` qui ne le reçoit pas

**Localisation** : § Axe 3 / Fichiers (orchestrator) vs § Axe 3 / Fichiers
(recommendation_agent, résolution finding 3) vs signature `retrieve_references`.

**Problème** :
- `retrieve_references(db, user_id, context, ctx_vec, *, ...)` prend `ctx_vec` en
  paramètre (§ Axe 2 / Fichiers). L'orchestrateur l'appelle « AVANT la closure
  `generate` », donc l'orchestrateur **doit** disposer de `ctx_vec`. Or la seule
  endroit où le calcul de `ctx_vec` est spécifié est **à l'intérieur de
  `recommendation_agent.run`** (`weather_band = occasions.weather_band(temperature)`
  puis `ranking_model.context_vector(occasion_category, season, weather_band)`). Le
  design ne dit jamais comment l'orchestrateur obtient `ctx_vec` pour le RAG.
- Contradiction : l'orchestrateur « passe … le contexte enrichi (saison, température,
  `occasion_category`, `weather`, **`weather_band`**) » à `generate`, mais la liste
  des kwargs de `run` (résolution finding 3) **exclut explicitement `weather_band`**
  (« `weather_band` n'en fait pas partie ; `temperature` est le seul input »). On
  passe donc un kwarg que `run` refuse (ou on le passe pour rien).

**Fix** : trancher en un seul mécanisme. L'orchestrateur calcule `ctx_vec` **une fois**
et le réutilise :
```python
weather_band = occasions.weather_band(context.get("temperature"))
ctx_vec = ranking_model.context_vector(
    context.get("occasion_category"), context.get("season"), weather_band
)
if get_settings().contextual_rag_enabled:
    references = context_retrieval.retrieve_references(self.db, user_id, context, ctx_vec)
else:
    references = None
def generate(items):
    return self.recommendation_agent.run(
        wardrobe_items=items, occasion=context["occasion"],
        favorite_styles=style_profile["favorite_styles"], usage=usage,
        season=context.get("season"), temperature=context.get("temperature"),
        weather=context.get("weather"), occasion_category=context.get("occasion_category"),
        formality=context.get("formality"), references=references, ctx_vec=ctx_vec,
    )
```
C'est-à-dire : ajouter `ctx_vec` aux kwargs de `run` (au lieu de le recalculer dans
`run`), et **retirer `weather_band`** de l'appel `generate`. Évite le double calcul et
lève l'ambiguïté.

### 2. (MEDIUM) Mécanisme de surcharge des kill-switches dans le conftest non spécifié (lru_cache + imports directs)

**Localisation** : § Testabilité (axe 1), § Kill-switches, § Stratégie de test
(`backend/tests/conftest.py` nouveau) ; source vérifié
`backend/app/core/config.py` (`get_settings` est `@lru_cache`) et
`backend/tests/test_llm_agent.py` (pattern de patch existant).

**Problème** : Le design dit que le conftest « construit
`Settings(ranking_enabled=False, contextual_rag_enabled=False)` et le branche sur
`get_settings()` » — sans préciser **où** ni **comment**, sachant que :
- `get_settings` est `@lru_cache` ;
- chaque module fait `from app.core.config import get_settings` (lie le nom à
  l'import), donc `monkeypatch.setattr("app.core.config.get_settings", ...)` **ne
  propage pas** vers `ranking_model`/`orchestrator`/`recommendation_agent`/`llm_agent`
  qui ont déjà lié le nom.
- Le pattern existant (`test_llm_agent._agent_with_settings`) patche le nom lié **du
  module concerné** (`app.agents.llm_agent.get_settings`) — preuve qu'un patch global
  sur `app.core.config` ne suffit pas.

Si la surcharge échoue silencieusement, les tests existants tournent avec
`ranking_enabled=True` (défaut) **et** l'artefact committé (si ship-gate passant) →
ils empruntent le chemin « artefact-présent » au lieu du fallback heuristique → la
garantie « byte-pour-byte identique / tests existants inchangés » saute
(`test_favorite_style_bonus_breaks_a_tie`, `test_coherent_wardrobe_scores_higher_than_random`).

Second défaut : `Settings(**overrides)` hérite de `.env` (pydantic-settings). Si un
développeur a `LLM_PROVIDER=mistral` dans son `.env`, le conftest en hérite →
`ContextAgent`/`LLMAgent` émettent de vrais appels réseau dans
`test_context_agent`. `test_llm_agent` s'en protège via
`overrides.setdefault("llm_provider", "none")` ; le conftest proposé ne le fait pas.

**Fix** : spécifier le mécanisme concret. Option robuste (valide pour tous les
modules sans énumérer les call sites) :
```python
# backend/tests/conftest.py
import pytest
from app.core.config import get_settings

@pytest.fixture(autouse=True)
def isolate_flags(monkeypatch):
    monkeypatch.setenv("RANKING_ENABLED", "false")
    monkeypatch.setenv("CONTEXTUAL_RAG_ENABLED", "false")
    monkeypatch.setenv("LLM_PROVIDER", "none")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
```
`get_settings` étant `@lru_cache`, `cache_clear()` + vars d'env fait que le **prochain**
`get_settings()` (dans n'importe quel module) relit l'env. Au minimum, énumérer les
modules à patcher (`ranking_model`, `orchestrator`, `recommendation_agent`) si on
préfère `monkeypatch.setattr` par module. Et pinner `LLM_PROVIDER=none` pour isoler
les tests du `.env` du développeur.

### 3. (MEDIUM) `parse_occasion_rules` par sous-chaîne → faux positifs (`"mer"` dans `"commercial"`)

**Localisation** : § Vocabulaire contrôlé d'occasion (table de mapping, matching
« lowercase substring »).

**Problème** : Le matching est « lowercase substring ». La catégorie `plage` a le
mot-clé `mer`. Or `"commercial"` contient `"mer"` (c-o-m-`m-e-r`-c-i-a-l) — vérifié.
Donc `parse_occasion_rules("je vais au centre commercial")` matche `mer` →
`occasion_category = "plage"`. Faux positif réel et réaliste (« shopping au centre
commercial » → plage). Mots-clés courts (`mer`, `job`, `sortie`) sont exposés à ce
défaut. Cela indexe un mauvais `ctx_vec` → `context_fit` faux → classement contextuel
erroné, sur le chemin déterministe (LLM off), justement celui qui se veut « injectif
et déterministe ».

**Fix** : remplacer le matching par sous-chaîne par un matching **par token** (mots
entiers, frontières de mot). Ex. :
```python
import re
_TOKENS = re.compile(r"[^\wàâäéèêëïîôöùûüç]+")  # split sur tout ce qui n'est pas mot

def _keywords_hit(text, keywords):
    if text is None:
        return False
    tokens = set(t for t in _TOKENS.split(text.lower()) if t)
    return any(kw in tokens or kw.replace("_", " ") in text.lower().split()
               for kw in keywords)
```
(Évaluer chaque ligne du tableau par `_keywords_hit` plutôt que `kw in text.lower()`.)
Au minimum, retirer/qualifier les mots-clés courts ambigus (`mer` → exiger « à la
mer » / « plage » / « baignade »).

### 4. (MEDIUM) Règles de synthèse `composition dressme_category → occasion_category` non spécifiées (entraînement)

**Localisation** : § Axe 1 / Fichiers (`ml/notebooks/10_ranking_model.py`) —
« occasion_category déduite par règles sur la composition des dressme_category des
items (les seules métadonnées disponibles) ».

**Problème** : Le rangifieur est entraîné sur des paires (tenue, occasion) où
l'occasion est **synthétisée** depuis la composition des `dressme_category` des items
Polyvore. Mais les règles de cette composition → `occasion_category` ne sont **jamais
données**, alors que le design fournit une table complète pour
`parse_occasion_rules` (texte → occasion). Or :
- le vocabulaire `dressme_category` de Polyvore est `haut/bas/robe/veste/chaussures/
  sac/accessoire` — il ne contient ni maillot ni vêtement de plage/sport, donc les
  occasions `sport`/`plage`/`voyage` sont à peine dérivables d'une composition
  Polyvore ; le signal `context_fit` ne couvrira réellement que quelques occasions ;
- la qualité du signal (et donc le passage du ship-gate) dépend entièrement de ces
  règles, qui restent à inventer par l'implémenteur.

Le ship-gate est un filet de sécurité (pas de commit si pas de gain), mais le design
présente `context_fit` comme « un signal réel » sans spécifier les règles qui le
produisent.

**Fix** : fournir la table `composition → occasion_category` (miroir de la table
`parse_occasion_rules`), ex. :
- `{robe, chaussures, sac}` et robe « habillée » → `ceremonie`/`mariage` ;
- `{haut, bas, veste, chaussures}` → `travail` ;
- `{haut, bas}` → `casual_quotidien` ;
- compositions sans robe/veste → `casual_quotidien` ;
- documenter explicitement que `sport`/`plage`/`voyage` sont faiblement couvrables
  sur Polyvore (et donc que le signal contextuel zéro-shot se concentre sur
  `travail`/`ceremonie`/`mariage`/`soiree`/`casual_quotidien`), et que le ship-gate
  est l'arbitre final.

### 5. (NIT) `compute_features` prend 6 args mais le LR n'en utilise que 2

**Localisation** : § Axe 1 / Fichiers (`ranking_model.compute_features(visual,
context_fit, history_fit, season_compat, style_match, recent) -> np.ndarray`).

**Problème** : Le LR est entraîné sur **2** features (`visual_coherence`,
`context_fit`) ; `predict_proba` reçoit donc un vecteur de dimension 2. Une fonction
qui prend 6 args pour en retourner 2 est trompeuse (« ordré pour predict_proba »
suggère que les 6 alimentent le modèle).

**Fix** : soit réduire la signature à
`compute_features(visual, context_fit) -> np.ndarray` (les 4 autres sont la couche
déterministe additive, calculées/appliquées ailleurs), soit nommer explicitement
`compute_learned_features(visual, context_fit)` pour distinguer des features
déterministes.

### 6. (NIT) `retrieve_references` : `category=cat` (singulier) vs retour `{category: [...]}` (dict) — catégorie cherchée non spécifiée

**Localisation** : § Axe 2 / Fichiers — signature de retour
`{"catalog": {category: [CatalogMatch.to_dict(), ...]}}` vs implémentation
`CatalogIndex().search(ctx_vec, category=cat)`.

**Problème** : Le retour est un dict **indexé par `category`**, mais la requête
catalogue prend un `category=cat` **singulier** sans dire quel `cat` (ni s'il itère sur
plusieurs `dressme_category`). `occasion_category` (mariage/soirée/…) n'est pas une
`dressme_category` (haut/bas/…), donc le mapping occasion → catégorie catalogue n'est
défini nulle part.

**Fix** : soit `category=None` (recherche cross-modale sur tout le catalogue, tri par
`ctx_vec`, top_k global) et grouper le retour par `dressme_category` côté
`RecommendationAgent` ; soit itérer explicitement sur un sous-ensemble de
`dressme_category` (ex. celles des items du wardrobe) et documenter lequel. Impact
limité (le catalogue n'alimente que l'explication LLM, pas le classement).

### 7. (NIT) `Outfit.explanation` (String 2048) non protégé contre un retour LLM long

**Localisation** : § Axe 3 (explication + ajustements repliés dans `explanation`) ;
source `app/models/outfit.py` (`explanation: String(2048)`).

**Problème** : L'explication LLM (1–2 phrases) + 1–2 suggestions d'ajustement est
repliée dans `explanation`. Un LLM peut renvoyer un texte plus long que prévu ;
l'orchestrateur fait `Outfit(..., explanation=candidate["explanation"])` sans
troncature. Risque d'`SQLAlchemy`/DB error sur dépassement 2048 (ou silencieux selon le
backend).

**Fix** : tronquer explicitement `explanation[:2048]` (ou `[:2040]` avec ellipse)
avant l'insertion `Outfit`, ou imposer une longueur max dans le prompt/system.

### 8. (NIT) `dress_code` du LLM non validé

**Localisation** : § Axe 3 / Fichiers (`llm_agent.parse_occasion`) — « valide
`occasion_category ∈ OCCASION_CATEGORIES`, `formality` 1–5 ».

**Problème** : `dress_code` (chaîne libre du LLM) n'est pas validé/normalisé, alors
qu'il est ajouté au contexte et peut finir dans l'explication. `formality` hors [1,5]
→ `None` (récupération), mais `dress_code` quelconque passe.

**Fix** : soit valider `dress_code` contre un petit vocabulaire (tenue de cérémonie /
chic / business casual / sportwear / décontracté / confortable / null), soit le
sanitiser (longueur max, strip) et documenter qu'il est libre.

### 9. (NIT) `ContextAgent.run` : ordre du `parse_occasion` vs lookup ville / contenu des `context_hints` non spécifié

**Localisation** : § Axe 3 / Fichiers (`context_agent.run`) ;
`occasion_parse_prompt(raw_occasion, context_hints)`.

**Problème** : Le design dit que `parse_occasion` reçoit « indices (saison/météo déjà
connus) », mais `run` calcule la météo via lookup ville **à l'intérieur** de `run`. On
ne sait pas si `context_hints` = valeurs d'entrée (avant lookup) ou post-lookup, ni si
`parse_occasion` est appelé avant ou après le lookup (donc si le LLM « voit » la
météo relevée).

**Fix** : spécifier l'ordre : (1) lookup ville → weather/temperature ; (2)
`normalize_season` / `season_from_temperature` ; (3) `parse_occasion(raw_occasion,
hints={"season": season, "weather": weather})` ; (4) ajout `temperature`,
`weather_band`. Préciser que `hints` reflète le résultat du lookup.

### 10. (NIT) Outfits historiques `WearLog` peuvent référencer des items supprimés (absents de Pinecone)

**Localisation** : § Axe 2 / Sources de retrieval (regroupement `WearLog` par date).

**Problème** : `metadata_agent.remove_item` appelle `vector_store.delete_item_embedding`
(source vérifié), donc un item supprimé disparaît de Pinecone. Un « outfit »
reconstruit depuis un `WearLog` peut donc inclure des `item_id` absents de
`fetch_embeddings` ; la moyenne se fait alors sur moins d'items (dégradation implicite,
non spécifiée).

**Fix** : documenter le comportement (moyenne sur les items présents) ou filtrer les
groupes historiques dont trop d'items manquent (ex. skip si <2 embeddings
disponibles).

---

## Findings précédents (Révision 1) — vérification du traitement

Tous traités de façon réelle (vérifié contre le source) :
- **F1 (HIGH)** voie (A) : 2 features apprises + couche déterministe additive. Polyvore
  `season=pd.NA`/`style=pd.NA` vérifié dans `ml/src/catalog.py` (`load_polyvore_official`).
- **F2** `getattr(item,"season",None)` + conftest `ranking_enabled=False` ; `_FakeItem`
  sans `season` vérifié dans `test_recommendation_agent.py`. (Mécanisme conftest →
  finding 2 ci-dessus.)
- **F3** `weather_band` dérivé de `temperature`. (Contradiction résiduelle → finding 1
  ci-dessus.)
- **F4** `vec` ajouté au retour `historical`.
- **F5** ship-gate δ=+0.02 AUC.
- **F6** assertions sous-ensemble ; `test_no_city_leaves_weather_none` asserte bien
  `result == {"occasion": "wedding", "weather": None, "season": None}` (vérifié).
- **F7** mapping injectif + table complète.
- **F8** `ScheduledOutfit.date`+`item_ids`, `WearLog` groupé par date, `Outfit` exclu.
  `WearLog` est bien 1 ligne/(item, jour) (`UniqueConstraint("item_id","date")`,
  vérifié).
- **F9/F10** 96 vecteurs (72+24), chaîne fallback reformulée (déclencheur = `season=None`).
- **F11** garde `provider=="none"` en tête de `run`/`parse_occasion`/`explain_outfit`
  (vérifié : `run` l'a déjà en tête).
- **F12** formule fallback exacte vérifiée conforme au code :
  `min(1.0, visual + (STYLE_MATCH_BONUS if style_match else 0.0))` puis
  `max(0.0, score - RECENT_WEAR_PENALTY * recent)`, `recent` = compte entier.
- **F13** `references` calculées 1× avant la closure (vérifié : `generate` appelée
  jusqu'à 2× dans `orchestrator.recommend_outfits`).
- **F14** kill-switches câblés. (Mécanisme de surcharge → finding 2 ci-dessus.)

---

## Verified Assumptions (confrontées au source)

- `compatibility_model.py` : `MODEL_PATH=…/artifacts/compatibility_model.joblib`,
  `@lru_cache` sur `_load_model`, `pair_compatibility` + fallback cosine. ✓
- `vector_store.fetch_embeddings → {}` hors config ; `is_configured()`. ✓
- `catalog_index.search(embedding, *, category, limit)`, `is_available()`,
  `dressme_category`, `CatalogMatch.to_dict()`, `_vectors`. ✓
- `LLMAgent.run(context, instruction) → {"explanation"}`, garde `provider=="none"` en
  tête, `httpx.post …/chat/completions`, `timeout=20.0`, client OpenAI-compatible. ✓
- `StyleProfileAgent` consomme `run(...)["explanation"]` (donc `run` doit rester
  `{"explanation": …}`). ✓
- `ContextAgent.run` retourne `{occasion, weather, season}` ; `temperature` calculé
  seulement dans la branche lookup ville. ✓
- `orchestrator.recommend_outfits` + closure `generate` (≤2 appels) + bloc
  dédup/insertion `Outfit`. ✓
- `config` : `llm_provider="none"` défaut, `get_settings` `@lru_cache`. ✓
- `seasons` : `COLD_BELOW_C=14`, `HOT_FROM_C=24`, `season_for_date`,
  `season_compatible`. ✓
- Modèles : `Outfit.explanation String(2048)` + `created_at` uniquement (pas de date
  de port) ; `ScheduledOutfit.date`+`item_ids` ; `WearLog` 1 ligne/(item, jour) ;
  `ClothingItem.season`/`style`/`colors` (`JSONList` TypeDecorator). ✓
- `OutfitRecommendationResult.context: dict` non typé (absorbe les nouvelles clés). ✓
- Route `/recommendations/outfits` : `OutfitRequest(occasion,weather,season,city)`
  inchangée ; `temperature` vient du `ContextAgent`. ✓
- `recommendation_agent` : `STYLE_MATCH_BONUS=0.1`, `RECENT_WEAR_PENALTY=0.05`,
  `RECENT_WEAR_DAYS=3`, `**kwargs: Any` présent, `recent` = compte entier,
  `style_match` booléen, `_explain` template. ✓
- Tests : `_FakeItem` sans `season` ; assertion `-1 ≤ score ≤ 1` ;
  `test_favorite_style_bonus_breaks_a_tie` ;
  `test_no_city_leaves_weather_none` (égalité dict exacte) ;
  `test_no_provider_returns_none_without_a_network_call` ; pattern patch
  `app.agents.llm_agent.get_settings` ; SQLite `StaticPool`. ✓
- `ml/notebooks/09` : `LogisticRegression(max_iter=2000, class_weight="balanced")`,
  cache `compatibility_embeddings.npz`, `polyvore_official.load_outfit_structure`,
  `features.embed_image_bytes`, schéma « save puis copie vers
  `backend/app/ml/artifacts/` ». ✓
- `ml/src/features.py` + `backend/app/ml/vision_model.py` : **même
  `FASHIONCLIP_REPO = "patrickjohncyh/fashion-clip"`**, embeddings image L2-normalisés
  512-d (ceux de Pinecone viennent de `vision_model.embed_image_bytes`). → Le claim
  central « `mean(outfit_vecs) · ctx_vec` est une similarité image–texte zéro-shot
  légitime, espaces compatibles par construction » est **techniquement fondé** : à
  l'inférence les vecteurs items (Pinecone, image FashionCLIP) et `ctx_vec` (texte
  FashionCLIP, précalculé hors-ligne) sont dans le même espace de projection CLIP.
  ✓
- `requirements.txt` : `httpx`, `scikit-learn>=1.5`, `joblib`, `numpy`, `torch`,
  `transformers` présents. Le chemin de recommandation peut rester torch-free à
  l'import (seuls sklearn/numpy chargés) ; torch reste installé pour le Vision Agent. ✓

## Unverified / Wrong Assumptions

- **Mistral free tier supporte `response_format={"type":"json_object"}`** : non
  vérifiable sans appeler l'API. Non bloquant : tout échec (HTTP/JSON) → `None` → règles
  (récupération spécifiée).
- **« tests existants byte-pour-byte identiques »** : conditionnel au mécanisme de
  surcharge du conftest, qui n'est pas spécifié (finding 2). Si la surcharge échoue,
  l'affirmation ne tient plus.
- **« `parse_occasion_rules` injectif et correct »** : l'injectivité (1 catégorie) tient,
  mais la « correction » est affaiblie par le matching sous-chaîne (finding 3 :
  faux positifs comme `"commercial"` → `plage`).
- **« `context_fit` est un signal réel »** : suppose des règles
  `composition → occasion` raisonnables, non spécifiées et limitées par le vocabulaire
  de catégories Polyvore (finding 4).
- **L'orchestrateur « passe `weather_band` à `generate` »** : contredit la signature de
  `run` (finding 1).
- **Coût LLM « 1 parsing + 1 explication par recommandation »** : le parsing est bien
  1 fois (dans `ContextAgent.run`, 1 appel/request) ; l'explication est par **outfit**
  (top_k), et `generate` peut être appelé 2× (mais la 2e seulement si la 1re est vide).
  L'ordre de grandeur tient, mais la formulation est imprécise.

---

## Verdict

**CHANGES_REQUESTED** (0 HIGH, 4 MEDIUM, 6 NIT). Les 4 MEDIUM (findings 1–4) doivent
être résolus avant implémentation : ils touchent le câblage orchestrateur/`ctx_vec`
(finding 1), la fiabilité de la garantie de non-régression des tests (finding 2), la
justesse du parseur déterministe (finding 3) et la définition du signal d'entraînement
(finding 4). Le socle technique (FashionCLIP cross-modal, fallbacks, réutilisation de
l'infra, traitement des 14 findings précédents) est solide.

# Design technique — Amélioration du RecommendationAgent de DressMe

> Cible : `backend/app/agents/recommendation_agent.py` et son écosystème. Racine du
> projet = `e:/Documents/Dress-Me`. Ce document valide l'approche pour les **3 axes**
> (fine-tuning du classement, RAG contextuel, prompt engineering + LLM) **avant**
> implémentation, en réutilisant l'infra existante (Pinecone, LLMAgent, ContextAgent,
> modèle de compatibilité Polyvore, catalogue tunisien) — enrichir, pas réécrire.
>
> **Révision 2** — intègre les 14 findings de la revue `design-review.json`
> (1 HIGH, 7 MEDIUM, 6 NIT). Les réponses point par point figurent en fin de document
> (§ « Réponses aux findings de revue »).

## Vue d'ensemble

Le `RecommendationAgent` actuel génère des tenues (bases haut+bas ou robe, slots
optionnels remplis gloutonnement) et les score par cohérence visuelle (modèle de
compatibilité Polyvore `app/ml/compatibility_model.py`), un bonus de style (style favori
#1) et une pénalité de fraîcheur (pièces portées récemment). Trois lacunes avérées : (1)
l'`occasion`/`weather`/`season` n'influencent **pas** le classement — ils n'apparaissent
que dans le texte d'explication ; (2) le vector store Pinecone ne sert qu'à la similarité
visuelle d'items, pas à un retrieval contextuel d'outfits ; (3) le `LLMAgent` est
désactivé par défaut (`LLM_PROVIDER=none`) et les explications sont des templates Python.

Le design ajoute, sans casser l'existant, trois mécanismes qui partagent **une seule
représentation du contexte** : un vecteur de contexte `ctx_vec` obtenu par plongée
FashionCLIP **texte** d'un prompt construit à partir de l'occasion structurée + saison +
bande de température. Ce vecteur est précalculé hors-ligne (entraînement, torch) et mis
en cache dans un artefact ; à l'inférence, aucun chargement de FashionCLIP/torch n'est
requis (sklearn + numpy uniquement). Concrètement : le `context_fit` (produit
scalaire moyenne-image-outfit · `ctx_vec`) devient le signal de classement contextuel
**appris** (axe 1), les références récupérées par RAG (axe 2) se réutilisent dans le
classement (couche déterministe additive) et l'explication LLM (axe 3), et le parsing
d'occasion (axe 3) fournit l'occasion structurée qui indexe le bon `ctx_vec`. Le LLM
reste strictement optionnel : toute défaillance (provider `none`, erreur réseau, JSON
invalide) retombe sur des règles déterministes, sans interrompre la recommandation.

## Stack technologique (verrouillée)

- **Backend runtime** : FastAPI + SQLAlchemy 2.x + Pydantic v2 (existants). Chemin de
  recommandation **sans torch** : sklearn (déjà en dépendance via `scikit-learn>=1.5`),
  numpy, joblib (déjà présents).
- **Vector store** : Pinecone via `app/db/vector_store.py` (existant) ; dégradation
  gracieuse quand non configuré (`is_configured() → False`, `fetch_embeddings → {}`).
- **Catalogue tunisien** : `app/services/catalog_index.py` + `app/data/catalog_embeddings.npz`
  (existants) — recherche cross-modale (image catalogue · `ctx_vec` texte),
  `search(embedding, *, category=..., limit=...)`, filtre sur `dressme_category`.
- **LLM** : Mistral free tier (endpoint OpenAI-compatible `/chat/completions`, déjà
  géré par `LLMAgent`) via `httpx` ; Llama/Ollama local en alternative. Optionnel.
- **Entraînement (hors-ligne, dossier `ml/`)** : torch + transformers (FashionCLIP),
  pandas, sklearn — identiques au notebook `09_compatibility_model.py`. Les artefacts
  produits sont **copiés** dans `backend/app/ml/artifacts/` (même schéma que
  `compatibility_model.joblib` / `purchase_calibration.json`). Le runtime ne
  ré-entraîne jamais.
- **Tests** : pytest, SQLite en mémoire (`create_engine("sqlite://", poolclass=StaticPool)`
  + `Base.metadata.create_all`), pattern déjà utilisé par `test_purchase_history_route.py`.

## Décision d'architecture clé : une seule représentation du contexte

`ctx_vec` (512-dim, L2-normalisé) = plongée FashionCLIP **texte** d'un prompt anglais
décrivant la situation, ex. `"an outfit suitable for a summer wedding in hot weather"`.
FashionCLIP est un modèle CLIP : image et texte partagent le même espace, donc
`moyenne-image-outfit · ctx_vec` est une **correspondance image–texte** zéro-shot
légitime — c'est précisément le signal « cette tenue convient-elle à ce contexte » qui
manque. Ce vecteur est précalculé pour les combinaisons `(occasion, season, band)` à
l'entraînement et caché dans `context_vectors.npz`. À l'inférence, on l'indexe par clé.

Cette décision unifie les 3 axes : RAG et classement partagent `ctx_vec` (et les vecteurs
des références récupérées), le parsing d'occasion produit la `occasion_category` qui
indexe `ctx_vec`, et l'explication LLM reçoit les scores et références comme faits.

## Axe 1 — Fine-tuning du classement (modèle de ranking appris)

### Approche choisie : rangifieur logistique sur 2 features calculables + couche déterministe additive

Deux options étaient possibles pour le rangifieur contextuel :
- **(A) Learning-to-rank sur faibles labels synthétiques, features limitées au calculable
  sur Polyvore** : `LogisticRegression` sur `visual_coherence` + `context_fit` (les seules
  features calculables sur les données d'entraînement Polyvore), puis `season_compat`,
  `style_match`, `freshness`, `history_fit` appliquées comme **couche déterministe
  additive** par-dessus le score appris (poids fixes/calibrés, non appris).
- **(B) Entraîner les features contextuelles sur les vraies données app**
  (`Outfit`/`ScheduledOutfit`/`WearLog` + `ClothingItem.season/style` réels) avec
  « porté/planifié » comme signal positif faible.

**Choix : (A)**. Justification vérifiée contre le code (`ml/src/catalog.py`) : les items
Polyvore ont `season = pd.NA` et `style = pd.NA` (aucun label de saison/style par item),
et il n'existe **aucun historique d'usage utilisateur** pour Polyvore. Donc 4 des 6
features du design précédent (`season_compat`, `style_match`, `history_fit`,
`freshness`) **ne sont pas calculables à l'entraînement** sur Polyvore. Si on les
forçait à 0/constantes à l'entraînement, leurs poids appris seraient non informatifs, et
à l'inférence — où les `ClothingItem` réels ont une vraie `season`/`style` et un vrai
`usage` (`ClothingItem.season`, `ClothingItem.style`, `MetadataAgent.usage_history`) — la
régression appliquerait des poids non calibrés à des features qui varient réellement.
Pire : `freshness` perdrait sa pénalité (poids ≈0) et `history_fit` ne transmettrait
jamais le signal RAG au classement, contredisant l'exigence « utiliser ces récupérations
pour filtrer/ranker ».

L'option (B) est rejetée pour cette itération : les données app réelles n'ont **pas de
labels de pertinence** — « porté/planifié » signifie seulement que l'utilisateur a
porté/planifié la tenue, pas qu'elle convenait à l'occasion ; il n'y a pas de signal
négatif et l'échelle est minuscule (garde-robe d'un seul utilisateur). Documentée en
backlog (§ Hypothèses). La voie (A) respecte l'exigence « un modèle de ranking appris »
tout en évitant d'apprendre des poids sur du bruit : le modèle **apprend** la partie qui
a du signal sur Polyvore (visual + contexte), la couche déterministe **applique** les
signaux utilisateur (style/freshness/history/season) avec des poids explicites calibrés.

**Modèle** : régression logistique `sklearn` (`class_weight="balanced"`,
`max_iter=2000`, comme le notebook 09), entraînée sur **2 features apprises**, toutes
calculables à l'inférence sans torch :

| Caractéristique | Type | Calcul | Origine |
|---|---|---|---|
| `visual_coherence` | **apprise** (input du LR) | moyenne `compatibility_model.pair_compatibility` sur paires (existant) | réutilise `compatibility_model.joblib` |
| `context_fit` | **apprise** (input du LR) | `mean(outfit_vecs) · ctx_vec` | **nouveau**, zéro-shot image–texte |
| `season_compat` | **déterministe additive** | fraction d'items avec `seasons.season_compatible(getattr(item,"season",None), ctx.season)` | règle, réutilise `seasons.py` |
| `style_match` | **déterministe additive** | `1.0` si tous les items partagent le style favori #1, sinon `0.0` | règle existante (conservée) |
| `freshness` | **déterministe additive** | nombre entier d'items portés dans les `RECENT_WEAR_DAYS` derniers jours (`recent`) | règle existante (conservée) |
| `history_fit` | **déterministe additive** | `max_ref (mean(outfit_vecs) · ref_vec)` sur top références RAG | **nouveau**, lien RAG→classement |

**Formule de scoring** (`ranking_model.score_outfit`), avec constantes existantes
`STYLE_MATCH_BONUS=0.1`, `RECENT_WEAR_PENALTY=0.05` et nouvelles `SEASON_COMPAT_BONUS=0.1`,
`HISTORY_FIT_WEIGHT=0.1` (calibrées, non apprises — voir § Calibration) :

- **Chemin artefact présent** (`ranking_model.joblib` existe ET
  `RANKING_ENABLED=True`) :
  ```
  learned = model.predict_proba([[visual_coherence, context_fit]])[0, 1]   # ∈ [0,1]
  base = learned + SEASON_COMPAT_BONUS * season_compat \
               + (STYLE_MATCH_BONUS if style_match else 0.0) \
               + HISTORY_FIT_WEIGHT * history_fit
  score = max(0.0, min(1.0, base - RECENT_WEAR_PENALTY * recent))
  ```
  où `recent` est le **nombre entier** d'items portés récemment, `style_match` est un
  booléen, `season_compat` ∈ [0,1], `history_fit` ∈ [0,1].
- **Chemin fallback** (artefact absent **OU** `RANKING_ENABLED=False`) : **réplication
  exacte de l'heuristique existante** (cf. `recommendation_agent.py` actuel, finding 12) :
  ```
  score = min(1.0, visual + (STYLE_MATCH_BONUS if style_match else 0.0))
  score = max(0.0, score - RECENT_WEAR_PENALTY * recent)
  ```
  Aucune feature contextuelle (`context_fit`, `season_compat`, `history_fit`) n'est
  calculée ni appliquée — comportement byte-pour-byte identique à l'existant sur un
  checkout neuf. C'est la garantie « ne pas casser l'existant ».

L'ordre de génération des candidats (bases haut+bas / robe, slots optionnels
gloutons) est **inchangé**. Seul le scoring final change — et seulement sur le chemin
artefact-présent.

### Calibration des poids déterministes (voie (A))

`SEASON_COMPAT_BONUS` et `HISTORY_FIT_WEIGHT` sont des constantes **fixées**
(défaut `0.1` chacune, même ordre de grandeur que `STYLE_MATCH_BONUS` existant), non
apprises. Justification : elles ne peuvent pas être apprises sur Polyvore (finding 1) et
les données app n'ont pas de labels de pertinence (voie B rejetée). Elles restent
**tunables** via constantes de module ; une calibration plus fine sur la distribution
catalogue (façon `purchase_calibration.json`) est laissée en backlog. Ce choix est
documenté explicitement pour ne pas laisser croire que ces poids sont optimisés.

### Fichiers (axe 1)

- **Créer** `backend/app/ml/ranking_model.py` — chargeur + inférence :
  - `MODEL_PATH = Path(__file__).resolve().parent / "artifacts" / "ranking_model.joblib"`,
    `VECTORS_PATH = ... / "context_vectors.npz"` (même pattern que
    `compatibility_model.py`, `@lru_cache` sur `_load_model`/`_load_vectors`).
  - `context_vector(occasion_category, season, weather_band) -> np.ndarray` :
    chaîne de fallback (cf. § Fallback ctx_vec ci-dessous).
  - `compute_features(visual, context_fit, history_fit, season_compat, style_match,
    recent) -> np.ndarray` (ordré pour `predict_proba`).
  - `score_outfit(*, visual, context_fit=0.0, history_fit=0.0, season_compat=0.0,
    style_match=False, recent=0, ranking_enabled=True) -> float` :
    lit `ranking_enabled` (passé par l'appelant, qui le tire de `get_settings()`) ; si
    `False` **ou** `MODEL_PATH` absent → **heuristique existante exacte** (chemin
    fallback ci-dessus) — **sans toucher l'artefact**. Sinon chemin artefact-présent.
    Clamp explicite → invariant `relevance_score ∈ [0,1]` détenu par cette fonction.
- **Créer** `ml/notebooks/10_ranking_model.py` — entraînement (mirrors notebook 09) :
  - Réutilise `polyvore_official.load_outfit_structure()` + `features.embed_image_bytes`
    + cache `compatibility_embeddings.npz` (déjà produit par le notebook 09) pour les
    vecteurs items ; `compatibility_model.pair_compatibility` pour `visual_coherence`.
  - Synthétise le contexte d'un vrai outfit : `occasion_category` déduite par règles sur
    la **composition des `dressme_category`** des items (les seules métadonnées
    disponibles — Polyvore n'a **pas** de `style`, finding vérifié), `season` déduite,
    `weather_band` aléatoire plausible. Négatifs : (i) même outfit + contexte
    incohérent, (ii) assemblage aléatoire + contexte quelconque.
  - Précalcule `context_vectors.npz` (cf. § Fallback ctx_vec pour le décompte exact).
  - Entraîne `LogisticRegression(max_iter=2000, class_weight="balanced")` sur
    **`(visual_coherence, context_fit)`** uniquement, split train/test honnête (outfits
    `test` jamais vus), imprime AUC/accuracy du rangifieur **vs. baseline heuristique**
    (sur Polyvore, `style_match=False` et `recent=0` toujours, donc la baseline =
    `min(1, visual)` = `visual_coherence` seule).
  - **Ship-gate** (cf. § Ship-gate) : ne copie `ranking_model.joblib` vers
    `backend/app/ml/artifacts/` que si le rangifieur bat la baseline. Sinon l'artefact
    reste absent → le runtime retombe sur l'heuristique.
  - Section « Findings » à remplir après exécution (honnêteté, comme le notebook 09).
- **Artefacts produits** (commités **seulement si ship-gate passant**) :
  `backend/app/ml/artifacts/ranking_model.joblib` (~Ko) et
  `backend/app/ml/artifacts/context_vectors.npz` (~197 Ko : 96 vecteurs × 512 × 4 o,
  cf. § Fallback ctx_vec).

### Fallback `ctx_vec` (chaîne corrigée — finding 10)

`parse_occasion_rules` renvoie **toujours** une catégorie du vocabulaire (défaut
`casual_quotidien`) et `LLMAgent.parse_occasion` valide « catégorie ∈ vocab », donc
`occasion_category` n'est **jamais** `None` ni hors-vocab à l'exécution. Le vrai
déclencheur du vecteur nul est l'**absence de saison** (`season=None`, qui implique
aucune température pour inférer). Chaîne réelle :

1. `season` non None **et** `weather_band` non None → clé `f"{occasion}|{season}|{band}"`
   (vecteur spécifique, 8×3×3 = 72 vecteurs).
2. `season` non None **mais** `weather_band` None (saison explicite, pas de température)
   → clé `f"{occasion}|{season}|_any"` (vecteur band-agnostic, 8×3 = 24 vecteurs).
3. `season` None (ni saison ni température) → `zeros(512)` (calculé à la volée, non
   stocké) → `context_fit = 0`, `history_fit` scoré sans `ctx_vec` (saison seule, voir
   axe 2) → dégradation vers `visual + season_compat + style + freshness`.

**Décompte exact** (finding 9) : 72 spécifiques + 24 band-agnostiques = **96 vecteurs
stockés** (+ le vecteur nul calculé à la volée). Taille ≈ 96 × 512 × 4 o ≈ **197 Ko**.
Aucune combinaison `occasion=None` n'est stockée (l'occasion est toujours une catégorie
du vocabulaire).

### Ship-gate (critère de publication — finding 5)

Le kill-switch `RANKING_ENABLED` existe mais n'est pas un critère de publication : si le
rangifieur ne bat pas l'heuristique, commiter l'artefact l'utiliserait par défaut et
dégraderait le classement existant. **Critère explicite** : ne copier
`ranking_model.joblib` vers `backend/app/ml/artifacts/` que si, sur les outfits `test`
jamais vus à l'entraînement, l'**AUC** du rangifieur bat la baseline heuristique
(`visual_coherence` seule) d'**au moins δ = +0.02 AUC**. Sinon, **laisser l'artefact
absent** du repo : le runtime retombe sur l'heuristique exacte (chemin fallback), et le
signal contextuel zéro-shot (`context_fit`) reste disponible pour une future itération
calibrée. Ce seuil est imprimé et documenté dans la section « Findings » du notebook,
lié à la décision de commit.

### Gestion d'erreurs (axe 1)

- `ranking_model.joblib` absent (checkout neuf, ou ship-gate échoué) : **récupérable** ;
  `score_outfit` retourne l'heuristique existante sans toucher l'artefact. Loggué `INFO`
  une fois (`logging.getLogger(__name__)`).
- `context_vectors.npz` absent mais modèle présent : `ctx_vec = zeros(512)` →
  `context_fit = 0` ; le rangifieur dégrade vers `visual + season_compat + style +
  freshness + history_fit` (history_fit scoré sans ctx_vec). Récupérable, loggué `INFO`.
- Erreur pendant le calcul des features d'un outfit (ex. shape mismatch) : `try/except`
  par candidat → score heuristique pour cet outfit, `WARNING` par outfit. Non fatal ;
  les autres candidats sont normalement scorés.
- L'**invariant** `relevance_score ∈ [0,1]` est détenu par `ranking_model.score_outfit`
  (clamp explicite `max(0, min(1, ...))`), car le rangifieur sort une probabilité et le
  fallback heuristique clamp déjà [0,1].

### Testabilité (axe 1)

- **Conftest par défaut** (finding 2) : `backend/tests/conftest.py` expose un fixture
  **autouse** qui construit `Settings(ranking_enabled=False, contextual_rag_enabled=False)`
  et le branche sur `get_settings()` pour la suite. Ainsi **tous les tests existants de
  `test_recommendation_agent.py` exécutent le chemin fallback (heuristique exacte)** —
  comportement inchangé, sans dépendre de la présence/absence de l'artefact committé.
  Les nouveaux tests de ranking **réactivent** `ranking_enabled=True` localement.
- **Défensivité `_FakeItem`** (finding 2a) : le calcul de `season_compat` utilise
  `getattr(item, "season", None)` (les `_FakeItem` actuels n'ont pas d'attribut
  `season`) — aucun `AttributeError` même sur le chemin artefact-présent.
- **Tests d'ordonnancement appris réservés à de nouveaux cas** (finding 2b) :
  `test_favorite_style_bonus_breaks_a_tie` reste vert sur le chemin fallback (le bonus
  de style est déterministe, `+0.1` au outfit casual — inchangé). Les nouveaux tests de
  ranking (`RANKING_ENABLED=True` + **faux modèle sklearn** injecté via
  `monkeypatch` de `ranking_model.MODEL_PATH` vers un `tmp_path` joblib + purge du
  `@lru_cache` `_load_model`) vérifient : `context_fit` plus haut → score plus haut à
  visuel constant ; indexation `ctx_vec` + fallbacks ; absence `context_vectors` →
  `context_fit=0` sans crash.
- **Unitaire** (`tests/test_ranking_model.py`, nouveau) : `context_vector` retourne le
  bon vecteur indexé et les 3 branches de fallback ; `score_outfit` sans artefact =
  heuristique exacte ; avec faux modèle sklearn = formule artefact attendue ;
  monotonicité (`visual_coherence` plus haut → score plus haut, à contexte constant).
- **Intégration** : couvert via `tests/test_recommendation_agent.py` étendu (cf. Axe 3).

## Axe 2 — RAG contextuel

### Approche choisie : étendre l'usage de `vector_store` + `catalog_index` via un module de retrieval (pas de nouvelle collection Pinecone)

Deux options : (a) créer une **nouvelle collection Pinecone** d'embeddings d'outfits
avec métadonnées (occasion, saison) ; (b) **réutiliser l'index items existant** en
définissant les vecteurs d'outfits à la volée (moyenne des vecteurs items, déjà
fetchés) + requêter le catalogue via `catalog_index` cross-modal.

**Choix : (b)**. Justification : les outfits ne sont pas une nouvelle entité à indexer —
un outfit = moyenne de ses items, dont les embeddings sont **déjà** dans Pinecone (via
`vector_store.upsert_item_embedding` à l'upload). Créer une collection dupliquerait des
données dérivables, ajouterait de la sync à maintenir (un item supprimé → l'outfit
orphelin), et compliquerait les tests (Pinecone mocké). Le module de retrieval fetch les
embeddings items existants (`vector_store.fetch_embeddings`, déjà utilisé par
`recommendation_agent`) et les moyenne. Le catalogue se réutilise tel quel :
`catalog_index.search(ctx_vec, category=...)` est une similarité cross-modale
(texte·image) légitime (mêmes 512-dim FashionCLIP).

### Sources de retrieval (spécifiées par source — finding 8)

La tâche liste explicitement l'historique d'usage = `WearLog` + `ScheduledOutfit`. Le
modèle `Outfit` (tenues générées) est **exclu** du retrieval historique : il n'a que
`created_at`/`occasion`, **pas de date de port** — dériver une saison de `created_at`
serait sémantiquement faux (c'est la date de génération, pas de port). Précision par
source :

- **`ScheduledOutfit`** (tenues planifiées au calendrier) : `item_ids` (liste) + `date`
  (champ natif). Saison déduite via `seasons.season_for_date(date)`. Signal = tenue que
  l'utilisateur a explicitement planifiée pour un jour.
- **`WearLog`** (journal de port, **une ligne par (item, jour)** — finding 8) : on
  **regroupe par `date`** les items portés ce jour pour **reconstruire l'ensemble**
  porté (`{date: [item_id, ...]}`). `item_ids` = items du groupe, `date` = la date du
  groupe, saison via `season_for_date(date)`. Un jour avec un seul item porté donne un
  « outfit » à 1 item (vecteur = celui de l'item) — acceptable, le signal reste « cet
  item a été porté un jour de cette saison ».
- **`Outfit`** : **exclu** (pas de date de port ; `created_at` = date de génération,
  sémantiquement incorrect comme « date de port »). Documenté explicitement.

Pour chaque outfit passé reconstruit : `mean(item_vecs) · ctx_vec` + bonus
`season_compat(outfit_season, ctx.season)` (saison déduite de la date). Top-N retournés.

### Fichiers (axe 2)

- **Créer** `backend/app/rag/__init__.py` et `backend/app/rag/context_retrieval.py` :
  - `retrieve_references(db: Session, user_id, context: dict, ctx_vec: np.ndarray, *,
    top_n_history=3, top_k_catalog=3) -> dict`
    retourne `{"historical": [{"item_ids", "score", "date", "season", "vec"}, ...],
    "catalog": {category: [CatalogMatch.to_dict(), ...]}}`.
  - **`vec` ajouté au retour** (finding 4) : chaque entrée `historical` contient
    `"vec": np.ndarray` = **vecteur moyen de l'outfit de référence** (déjà calculé pour
    scorer, retourné pour éviter un re-fetch Pinecone côté `RecommendationAgent`).
  - Implémente `historical` : requête `ScheduledOutfit` (owner=user_id) + regroupement
    `WearLog` par date (owner=user_id), fetch embeddings via
    `vector_store.fetch_embeddings` (tous les `item_ids`), calcule les vecteurs moyens,
    score, top-N. **Pinecone non configuré → `fetch_embeddings` renvoie `{}` →
    `historical=[]`** (dégradation gracieuse, aucun crash).
  - Implémente `catalog` : `CatalogIndex().search(ctx_vec, category=cat)` ;
    `catalog_index.is_available() == False` → `catalog={}`.
  - Aucun accès DB dans `vector_store` (garde sa responsabilité bas-niveau) ; le module
    RAG est la couche d'intégration qui orchestre `vector_store` + `catalog_index` +
    DB. C'est l'« extension de l'usage du vector store » demandée, sans modifier son API.

### Intégration RAG → classement et explication

- `history_fit` (feature **déterministe additive** du rangifieur, axe 1) = `max` sur
  les top références historiques de `mean(outfit_vecs) · ref["vec"]` — « cette tenue
  ressemble-t-elle à ce que vous avez porté dans un contexte similaire ? ». Comme le
  rangifieur retourne `vec`, **aucun re-fetch Pinecone** côté `RecommendationAgent`
  (finding 4). Concrétise l'exigence « utiliser ces récupérations pour filtrer/ranker ».
- Les références (historique + catalogue) sont passées comme **faits** au prompt
  d'explication LLM (axe 3) : « pour ce mariage d'été, vous aviez porté des tenues
  similaires (réf. …) ; le catalogue propose … ». Le LLM ne les invente pas.

### Gestion d'erreurs (axe 2)

- Pinecone non configuré : `fetch_embeddings → {}` → `historical=[]`, `history_fit=0` —
  récupérable, non fatal.
- `catalog_embeddings.npz` absent : `catalog={}` — récupérable.
- Aucun outfit passé pour l'utilisateur : `historical=[]` — récupérable.
- Erreur DB lors de la requête historique : `try/except` → `historical=[]`, `WARNING`,
  non fatal (la recommandation n'en dépend pas pour exister).

### Testabilité (axe 2)

- **Unitaire** (`tests/test_context_retrieval.py`, nouveau) : SQLite en mémoire +
  `ScheduledOutfit` seedés + `WearLog` seedés (groupés par date) + `monkeypatch` de
  `vector_store.fetch_embeddings` (vecteurs fixes) → `historical` ordonné par
  `ctx_vec` ; `ctx_vec` hiver ramène les outfits hiver en tête ; chaque entrée contient
  bien `vec`.
- Pinecone off (`fetch_embeddings → {}`) → `historical=[]` sans crash.
- Catalogue : `monkeypatch` `CatalogIndex._vectors` → `catalog` non vide par catégorie.

## Axe 3 — Prompt engineering + activation LLM

### Provider choisi : Mistral free tier (défaut recommandé)

`LLMAgent` est déjà compatible OpenAI/Mistral/Llama via un seul client
`/chat/completions`. On active avec `LLM_PROVIDER=mistral` + `LLM_API_KEY` (free tier).
Aucune nouvelle dépendance (httpx déjà présent). `llama`/Ollama local reste une
alternative (déjà supportée via `LLM_BASE_URL`/`LLM_MODEL` explicites). Le LLM reste
**optionnel** : `LLM_PROVIDER=none` (défaut) garde tous les comportements de fallback.

### Vocabulaire contrôlé d'occasion (nouveau) — mapping injectif (finding 7)

`backend/app/services/occasions.py` (nouveau) :
- `OCCASION_CATEGORIES = ["mariage", "soiree", "travail", "casual_quotidien", "sport",
  "plage", "voyage", "ceremonie"]` (8 catégories — assez pour indexer `ctx_vec`, assez
  restreint pour précalculer toutes les combos).
- `parse_occasion_rules(text: str | None) -> dict` : mappeur **injectif** mots-clés
  FR/EN → **exactement une** catégorie (pour indexer `ctx_vec`), formalité, dress_code.
  **Table complète** (finding 7 — fin de l'ambiguïté « un texte → deux catégories ») :

  | Mots-clés (FR/EN, lowercase substring) | `occasion_category` | `formality` | `dress_code` |
  |---|---|---|---|
  | `mariage`, `wedding` | `mariage` | 5 | `tenue de cérémonie` |
  | `church`, `funeral`, `baptême`, `bapteme`, `ceremonie`, `cérémonie`, `communion` | `ceremonie` | 5 | `tenue de cérémonie` |
  | `soirée`, `soiree`, `party`, `sortie`, `disco`, `boîte`, `boite`, `club` | `soiree` | 3 | `chic` |
  | `travail`, `bureau`, `meeting`, `réunion`, `reunion`, `entretien`, `interview`, `job` | `travail` | 4 | `business casual` |
  | `sport`, `gym`, `fitness`, `running`, `footing`, `entraînement`, `entrainement` | `sport` | 1 | `sportwear` |
  | `plage`, `beach`, `mer`, `baignade`, `pool`, `piscine` | `plage` | 1 | `décontracté` |
  | `voyage`, `trip`, `vacances`, `airport`, `aéroport`, `avion`, `train` | `voyage` | 2 | `confortable` |
  | (aucun match, ou `text` est None) | `casual_quotidien` | 2 | `null` |

  Premier match dans l'ordre du tableau gagne (la table est évaluée en cascade, pas en
  union). Fallback déterministe quand le LLM est off/échoue.
- `WEATHER_BANDS` : `froid` (<14°C), `modere` (14–24°C), `chaud` (≥24°C) — cohérents avec
  `seasons.COLD_BELOW_C=14`/`HOT_FROM_C=24`. `weather_band(temperature: float|None) ->
  str|None` (retourne `None` si `temperature` est `None`).

### Prompts structurés (3 capacités)

**Créer** `backend/app/agents/prompts.py` (pures fonctions de construction de prompts,
testables sans réseau) :

1. **(a) Parsing d'occasion** — `occasion_parse_prompt(raw_occasion, context_hints) -> list[message]`.
   System : « Tu es l'assistant stylistique DressMe. À partir du texte libre, renvoie
   **uniquement** un JSON `{"occasion_category": <une des 8 catégories>,
   "formality": <1-5>, "dress_code": <str|null>, "notes": <str|null>}`. Si incertain,
   choisis `casual_quotidien`. N'invente rien d'autre. » User : le texte brut + indices
   (saison/météo déjà connus). `response_format={"type":"json_object"}` activé
   (Mistral/OpenAI le supportent).
2. **(b)+(c) Explication + ajustements** — `explain_outfit_prompt(facts) -> list[message]`.
   System : « Tu es l'assistant stylistique DressMe. En 1–2 phrases, explique pourquoi
   cette tenue convient à l'occasion/météo, **en n'utilisant que les faits fournis**
   (items, scores, contexte, références historiques/catalogue). N'invente jamais de
   pièces, scores ou comptes non fournis. Si le contexte le justifie, ajoute 1–2
   suggestions d'ajustement concrètes (ex. « remplace le pantalon par un short, il fera
   30°C ») avec leur raison. » User : facts structurés (JSON sérialisé). On regroupe
   (b) et (c) en **un seul appel LLM** pour limiter latence/coût (1 appel parsing + 1
   appel explication par recommandation), tout en exposant les deux capacités comme des
   sections distinctes du prompt.

### Fichiers (axe 3)

- **Modifier** `backend/app/agents/llm_agent.py` :
  - Refactoriser : extraire `_chat(messages, *, json_mode=False, timeout=20.0) -> str`
    (POST + `raise_for_status` + extraction `choices[0].message.content`). Garder
    `run(context, instruction)` (consommé par `StyleProfileAgent`) qui appelle `_chat`
    — sa signature/retour (`{"explanation": ...}`) et son test
    `test_no_provider_returns_none_without_a_network_call` **inchangés**.
  - Ajouter `parse_occasion(raw_occasion, context_hints) -> dict|None` :
    **`provider=="none"` → `return None` AVANT tout appel à `_chat`** (finding 11) —
    donc aucun `httpx.post` émis, test `test_no_provider_returns_none_without_a_network_call`
    reste vert. Sinon `_chat(occasion_parse_prompt(...), json_mode=True)` puis
    `json.loads` ; valide `occasion_category ∈ OCCASION_CATEGORIES`, `formality` 1–5.
    **Toute erreur** (HTTP non 2xx, timeout, JSON invalide, champ inattendu/catégorie
    hors-vocab) → log `WARNING` + `return None` (l'appelant retombe sur les règles).
  - Ajouter `explain_outfit(facts) -> str|None` : **`provider=="none"` → `return None`
    AVANT tout appel à `_chat`** (finding 11). Sinon `_chat(explain_outfit_prompt(facts))` ;
    erreur → `WARNING` + `None`.
  - **Localisation du garde-fou `provider=="none"`** (finding 11) : la garde
    `if self.settings.llm_provider == "none": return None` vit **en tête de
    `parse_occasion` et `explain_outfit` (et reste en tête de `run`)**, avant toute
    résolution de provider ou appel à `_chat` — donc avant tout `httpx.post`.
- **Modifier** `backend/app/agents/context_agent.py` :
  - `run` accepte un `LLMAgent` injecté (défaut `LLMAgent()`) pour testabilité. Conserve
    le complément règles existant (météo→saison via `WeatherService`) — **inchangé**.
  - Ajoute : `occasion_category`, `formality`, `dress_code` via `LLMAgent.parse_occasion`
    si dispo (renvoie non-`None`), sinon `occasions.parse_occasion_rules`. Ajoute
    `temperature` (déjà calculé en interne) et `weather_band =
    occasions.weather_band(temperature)` au dict retourné. Clés existantes (`occasion`,
    `weather`, `season`) **conservées** pour compatibilité.
- **Modifier** `backend/app/agents/recommendation_agent.py` :
  - `run` gagne des kwargs optionnels `season`, `temperature`, `weather`,
    `occasion_category`, `formality`, `references` (default `None`) — signature
    **rétro-compatible** (les tests actuels n'en passent aucun ; `**kwargs` déjà présent).
  - **`weather_band` est dérivé, pas reçu** (finding 3) : au début de `run`,
    `weather_band = occasions.weather_band(temperature)` avant l'appel à
    `ranking_model.context_vector(occasion_category, season, weather_band)`. `temperature`
    est le seul input ; `weather_band` n'est **pas** un kwarg.
  - Calcule le score via `ranking_model.score_outfit(...)` (le `ranking_enabled` est lu
    depuis `get_settings()` par l'appelant et passé à `score_outfit`, ou lu dedans — cf.
    § Kill-switches). Le calcul de `visual_coherence` (mean pairwise) et la génération
    de candidats sont **inchangés**. `history_fit` utilise `references["historical"][i]["vec"]`
    (pas de re-fetch — finding 4).
  - Explication : si un `LLMAgent` est injecté et `explain_outfit(facts)` renvoie une
    chaîne → l'utiliser ; sinon `_explain(...)` (template existant, **conservé**),
    enrichi d'une note d'ajustement déterministe (règle simple : si
    `weather_band=="chaud"` et un item `bas` a `season=="hiver"`, suggérer une pièce
    plus légère). Les suggestions d'ajustement sont **repliées dans le texte
    `explanation`** (pas de nouvelle colonne — cf. Schéma de données).
- **Modifier** `backend/app/agents/orchestrator.py` :
  - `recommend_outfits` : calcule `references = context_retrieval.retrieve_references(...)`
    **une seule fois, AVANT la closure `generate`** (finding 13 — la closure est
    appelée jusqu'à 2×, mais `references` ne dépend que du contexte/DB, pas des items ;
    on évite de dupliquer les appels RAG/Pinecone). Passe `references=references` aux
    deux appels `generate(...)`, ainsi que le `context` enrichi (saison, température,
    `occasion_category`, `weather`, `weather_band`). Le bloc de dédup/insertion `Outfit`
    est **inchangé**.

### Gestion d'erreurs (axe 3)

- `LLMAgent.parse_occasion` : `provider=="none"` → `None` **sans appel réseau** (garde
  en tête de la méthode, avant `_chat`) — test
  `test_no_provider_returns_none_without_a_network_call` reste vert. Erreur
  HTTP/timeout/JSON → `WARNING` + `None` → `ContextAgent` retombe sur
  `parse_occasion_rules`. Récupérable, non fatal.
- `LLMAgent.explain_outfit` : échec → `None` → `RecommendationAgent` retombe sur
  `_explain` (template). Récupérable, non fatal.
- **Invariant** « le LLM n'invente jamais de faits » : détenu par les **prompts**
  (system instructions) + par le fait que les faits (scores, items, références) viennent
  d'agrégations réelles (rangifieur, RAG, `StyleProfileAgent`). Aucun score/compte n'est
  demandé au LLM. Couche propriétaire : la couche agent (qui assemble les facts), pas le
  LLM — car le LLM ne peut pas être de confiance pour compter.

### Testabilité (axe 3)

- **Unitaire** `tests/test_llm_agent.py` étendu : `parse_occasion` avec `provider=none` →
  `None` sans appel (`httpx.post` mocké en `fail_if_called`) ; `provider=mistral` +
  `monkeypatch httpx.post` (fake JSON) → dict validé ; JSON invalide/catégorie
  hors-vocab → `None` (récupération). `explain_outfit` similaire. `run` (existant) reste
  vert.
- **Unitaire** `tests/test_context_agent.py` étendu (finding 6) : occasion libre texte →
  `occasion_category` via règles (LLM off) ; `temperature`/`weather_band` présents ;
  **l'assertion exacte `result == {"occasion", "weather", "season"}` de
  `test_no_city_leaves_weather_none` est remplacée par des vérifications de
  sous-ensemble** : `assert result["occasion"] == "wedding" and result["weather"] is
  None and result["season"] is None`, plus des assertions sur les nouvelles clés
  (`result["occasion_category"] == "mariage"`, `result["weather_band"] is None`,
  `result["formality"] == 5`). Comportements existants (météo explicite non écrasée,
  ville sans clé météo → None) **inchangés** — seules les assertions d'égalité exacte
  sont relâchées en sous-ensemble.
- `backend/app/agents/prompts.py` testé isolément (sortie = messages attendus, sans
  réseau).

## Schéma de données — pas de migration (décision explicite)

Pour ne pas casser l'existant et rester purement additif, **aucune colonne n'est
ajoutée** à `Outfit`. Les ajustements suggérés (axe 3c) sont **repliés dans le texte
`explanation`** (String(2048) existant). Motivé par : (1) les suggestions d'ajustement
sont liées à la météo du moment (éphémères) ; (2) éviter une migration Alembic réduit le
blast radius et le risque de casser Postgres/SQLite ; (3) le frontend affiche déjà
`explanation`. Revers : les ajustements ne sont pas structurés côté API. Si le design
review souhaite un champ `adjustments` structuré, l'alternative additive sûre serait une
colonne nullable `adjustments` (JSONList, TypeDecorator déjà utilisé sur
`clothing_items.colors`) via une migration `add_outfit_adjustments.py` — laissé en
backlog, non implémenté par défaut.

`ContextAgent.run` retourne un dict enrichi (clés ajoutées : `temperature`,
`weather_band`, `occasion_category`, `formality`, `dress_code`) ; l'API
`OutfitRecommendationResult.context: dict` (non typé) absorbe ces ajouts sans changement
de schéma Pydantic.

## Kill-switches — câblage précis (finding 14)

Deux booléens dans `config.py` (défaut `True`), point de lecture et effet spécifiés :

- **`ranking_enabled: bool = True`** — lu dans `ranking_model.score_outfit` (via
  `get_settings()` ou passé par l'appelant). Effet : `False` → **court-circuit avant
  tout chargement d'artefact**, retourne l'heuristique exacte (chemin fallback).
  Jamais `joblib.load`.
- **`contextual_rag_enabled: bool = True`** — lu dans
  `orchestrator.recommend_outfits` (via `get_settings()`). Effet : `False` →
  `references = None` **et l'appel `retrieve_references` est skipppé** (aucun appel
  Pinecone/DB historique). `recommendation_agent.run` reçoit `references=None` →
  `history_fit=0`, pas de faits catalogue dans l'explication.

Le `conftest.py` de test (finding 2) force ces deux flags à `False` par défaut pour la
suite — les tests existants exercent donc l'heuristique + pas de RAG, comportement
inchangé.

## Fallback gracieux — matrice complète

| Condition | Axe 1 (classement) | Axe 2 (RAG) | Axe 3 (LLM) |
|---|---|---|---|
| `LLM_PROVIDER=none` | rangifieur actif (sklearn+cache, pas de LLM) | actif | parsing→règles ; explication→template ; ajustements→règle |
| LLM configuré mais échec réseau/JSON | inchangé | inchangé | parsing→règles ; explication→template (`WARNING`) |
| Pinecone non configuré | `fetch_embeddings→{}` → pas d'outfits (comportement **existant** inchangé) | `historical=[]`, `history_fit=0` | inchangé |
| `ranking_model.joblib` absent (checkout neuf / ship-gate échoué) | heuristique existante exacte | inchangé | inchangé |
| `context_vectors.npz` absent | `ctx_vec=0` → dégrade vers `visual + season_compat + style + freshness` | `historical` scoré sans `ctx_vec` (saison seule) | inchangé |
| `catalog_embeddings.npz` absent | inchangé | `catalog={}` | explication sans réf. catalogue |
| `RANKING_ENABLED=False` | heuristique exacte (artefact non chargé) | inchangé | inchangé |
| `CONTEXTUAL_RAG_ENABLED=False` | `history_fit=0` | `retrieve_references` skipppé, `references=None` | explication sans réf. |

Dans **tous** les cas, `RecommendationAgent.run` renvoie `{"outfits": [...]}` (éventuellement
vide si pas d'embeddings — comportement existant). Aucune exception non gérée ne remonte
à l'orchestrateur.

## Stratégie de test

**Principe** : le chemin de recommandation reste testable sans Postgres, sans Pinecone,
sans torch, sans LLM (tout est mockable ou fallback). Vérification :
`cd backend ; python -m pytest tests -q`.

- `backend/tests/conftest.py` (nouveau, finding 2) — fixture autouse :
  `ranking_enabled=False`, `contextual_rag_enabled=False` pour la suite par défaut.
- `tests/test_ranking_model.py` (nouveau) — axe 1 : indexation `ctx_vec` + 3 branches de
  fallback ; fallback artefact absent = heuristique exacte ; faux modèle sklearn =
  formule artefact ; fallback vecteurs absents = `context_fit=0` ; monotonicité.
- `tests/test_context_retrieval.py` (nouveau) — axe 2 : historique ordonné par contexte
  (SQLite + `ScheduledOutfit`/`WearLog` seedés + `fetch_embeddings` mocké),
  regroupement `WearLog` par date, `vec` présent dans chaque entrée ; Pinecone off →
  `[]` ; catalogue mocké → non vide.
- `tests/test_recommendation_agent.py` (étendu, **pas cassé** — finding 2) — sur le
  chemin fallback par défaut (conftest) : les tests existants (bases haut+bas/robe,
  cohérent>aléatoire, bonus style rompt l'égalité, pas d'embeddings → vide) restent
  **verts et inchangés** (l'assertion `-1 ≤ score ≤ 1` reste vraie). Nouveaux cas avec
  `ranking_enabled=True` + faux modèle sklearn : ordre respecte `context_fit` (un
  outfit cohérent avec le contexte bat un outfit visuellement équivalent mais
  hors-contexte) ; LLM off → explication template ; LLM mocké → explication LLM injectée.
- `tests/test_llm_agent.py` (étendu) — axe 3 : `parse_occasion`/`explain_outfit`
  `provider=none` → `None` sans appel réseau + récup d'erreur JSON/catégorie hors-vocab.
- `tests/test_context_agent.py` (étendu, finding 6) — axe 3 : occasion structurée
  (règles, mapping injectif), `temperature`/`weather_band` ; assertions relâchées en
  sous-ensemble (cf. Testabilité axe 3).

Les tests live/Postgres (`test_live_integration.py`) se skippent déjà sans Postgres ;
l'activation LLM/Pinecone réelle s'y exerce optionnellement.

## Risques et prévention de la régression

1. **Changement d'ordre des recommandations existantes** : mitigré par (i) le fallback
   heuristique exact quand l'artefact est absent **ou** `RANKING_ENABLED=False` (conftest
   en test, kill-switch en prod), (ii) le **ship-gate** (commit seulement si AUC ≥
   baseline + 0.02), (iii) des tests d'**intention** (ordonnancement) plutôt que de
   valeurs exactes, (iv) flags config comme kill-switch sans redéployer le modèle.
2. **Coût/latence LLM** : 1 appel parsing + 1 appel explication par recommandation
   (regroupement (b)+(c)). `httpx` timeout 20s. Dégradation immédiate si échec.
3. **Surapprentissage du rangifieur sur faibles labels** : mitigé par la limitation à 2
   features calculables (finding 1) + ship-gate (commit seulement si bat baseline).
   Honnêtement documenté dans « Findings » du notebook (comme le notebook 09). Le
   signal utile — `context_fit` zéro-shot — ne dépend pas des poids appris ; le
   rangifieur calibre juste.
4. **Poids déterministes non optimisés** (`SEASON_COMPAT_BONUS`, `HISTORY_FIT_WEIGHT`) :
   documentés comme fixes/calibrés, non appris (voie A). Tunables ; calibration fine en
   backlog. Pas cachés.
5. **`ctx_vec` incohérent avec la vraie plongée** : précalculé avec le **même** modèle
   FashionCLIP que les embeddings items/`vision_model` (`patrickjohncyh/fashion-clip`) —
   espaces compatibles par construction.
6. **Compatibilité Windows/PowerShell** : entraînement lancé via
   `python ml/notebooks/10_ranking_model.py`. Artefacts copiés avec `Copy-Item`. Tests
   via `python -m pytest tests -q` dans `backend/`.

## Fichiers — synthèse

**À créer** :
- `backend/app/ml/ranking_model.py`
- `backend/app/rag/__init__.py`, `backend/app/rag/context_retrieval.py`
- `backend/app/agents/prompts.py`
- `backend/app/services/occasions.py`
- `backend/tests/conftest.py` (fixture autouse — findings 2 + 14)
- `ml/notebooks/10_ranking_model.py` (+ artefacts copiés vers
  `backend/app/ml/artifacts/ranking_model.joblib`, `.../context_vectors.npz` —
  **seulement si ship-gate passant**)
- `backend/tests/test_ranking_model.py`, `backend/tests/test_context_retrieval.py`

**À modifier** (enrichir, pas réécrire) :
- `backend/app/agents/llm_agent.py` (`_chat`, `parse_occasion`, `explain_outfit` ; garde
  `provider=="none"` en tête de chaque méthode — finding 11)
- `backend/app/agents/context_agent.py` (contexte enrichi, `temperature`, `weather_band`,
  parsing occasion LLM+règles)
- `backend/app/agents/recommendation_agent.py` (features rangifieur, score via
  `ranking_model`, `weather_band` dérivé de `temperature` — finding 3, explication
  LLM+règles, kwargs optionnels rétro-compatibles)
- `backend/app/agents/orchestrator.py` (`references` calculées 1× avant la closure
  `generate` — finding 13 ; passage du contexte enrichi + références RAG)
- `backend/app/core/config.py` (+ `ranking_enabled`, `contextual_rag_enabled` ; défauts
  `True` — finding 14)
- `backend/.env.example` (doc `LLM_PROVIDER=mistral`/`LLM_API_KEY` + flags)
- `backend/tests/test_recommendation_agent.py`, `test_llm_agent.py`,
  `test_context_agent.py` (extension ; assertions relâchées en sous-ensemble où
  nécessaire — findings 2 + 6)

**Inchangés** : `vector_store.py` (API conservée, réutilisée), `catalog_index.py`,
`compatibility_model.py`, `seasons.py`, `metadata_agent.py`, modèles DB, routes
`recommendations.py` (signature de requête inchangée), `StyleProfileAgent`.

## Hypothèses explicites

- Pas de jeu réellement étiqueté (outfit, occasion, pertinence) → faibles labels
  synthétiques (signal relatif match/non-match) pour le rangifieur, **sur 2 features
  calculables** (visual + context). Documenté honnêtement dans le notebook, à la manière
  du notebook 09. (voie A choisie, voie B backlog).
- Polyvore n'a ni `season` ni `style` par item (`pd.NA`, vérifié dans `catalog.py`) ;
  aucun historique d'usage utilisateur → 4/6 features non calculables à l'entraînement →
  couche déterministe additive pour ces 4 (finding 1).
- Poids déterministes (`SEASON_COMPAT_BONUS`, `HISTORY_FIT_WEIGHT`) fixes à `0.1`,
  calibrés à la main (non appris, non optimisés sur labels — il n'y en a pas). Tunables ;
  calibration fine en backlog.
- Le vocabulaire d'occasion (8 catégories, mapping injectif — finding 7) suffit à indexer
  `ctx_vec` et couvre les cas nommés par l'utilisateur. Extensible sans casser l'existant
  (ajout d'une catégorie = une entrée de plus dans `context_vectors.npz` via
  ré-entraînement).
- Le repli des ajustements dans `explanation` (pas de colonne) est acceptable ; une
  colonne structurée est en backlog si le review le demande.
- `n8n` non nécessaire (décision déjà entérinée) — tout reste dans le backend Python.

---

## Réponses aux findings de revue

Verdict de la revue : **CHANGES_REQUESTED** (1 HIGH, 7 MEDIUM, 6 NIT). Chaque finding est
traité ci-dessous. Conventions : **traité** = modification intégrée au design ci-dessus ;
**backlog** = reporté avec raison ; **ignoré** = justifié.

### Finding 1 (HIGH) — Features contextuelles non calculables sur Polyvore → TRAITÉ
Voie **(A)** choisie et spécifiée. Le rangifieur `LogisticRegression` est entraîné sur
**2 features apprises** (`visual_coherence`, `context_fit`), les seules calculables sur
Polyvore. `season_compat`, `style_match`, `freshness`, `history_fit` sont appliquées
comme **couche déterministe additive** par-dessus le score appris (formule explicite dans
§ Axe 1, tableau marquant « apprise » vs « déterministe additive »). La voie (B)
(entraîner sur données app réelles) est rejetée et documentée en backlog (pas de labels
de pertinence, pas de signal négatif, échelle minuscule). Poids déterministes
`SEASON_COMPAT_BONUS`/`HISTORY_FIT_WEIGHT` fixés à `0.1`, calibrés à la main, documentés
comme non optimisés. `freshness` conserve sa pénalité, `history_fit` transmet le signal
RAG au classement (couche additive, pas poids appris).

### Finding 2 (MEDIUM) — « tests existants restent verts » non tenu → TRAITÉ
(a) `season_compat` utilise `getattr(item, "season", None)` (les `_FakeItem` sans
`season` ne lèvent plus `AttributeError`). (b) `backend/tests/conftest.py` (nouveau,
fixture autouse) force `ranking_enabled=False` pour la suite → les tests existants de
`test_recommendation_agent.py` exercent le **chemin fallback (heuristique exacte)**,
comportement inchangé, indépendant de la présence de l'artefact committé. Les tests
d'ordonnancement appris sont réservés à de **nouveaux cas** (`ranking_enabled=True` +
faux modèle sklearn injecté via `monkeypatch` de `MODEL_PATH` + purge du `@lru_cache`).
`test_favorite_style_bonus_breaks_a_tie` reste vert (le bonus de style est déterministe,
non appris). Spécifié en § Testabilité (axe 1) et § Kill-switches.

### Finding 3 (MEDIUM) — Incohérence `weather_band` → TRAITÉ
Tranché : `weather_band` est **dérivé, pas reçu**. Au début de
`recommendation_agent.run` : `weather_band = occasions.weather_band(temperature)` avant
l'appel à `ranking_model.context_vector(occasion_category, season, weather_band)`. Les
kwargs sont `season, temperature, weather, occasion_category, formality, references` ;
`weather_band` n'en fait pas partie (`temperature` est le seul input). Spécifié en §
Axe 3 / Fichiers (recommendation_agent).

### Finding 4 (MEDIUM) — `retrieve_references` ne retourne pas les vecteurs → TRAITÉ
Le schéma de retour inclut désormais `"vec": np.ndarray` (vecteur moyen de l'outfit de
référence) dans chaque entrée `historical`. `history_fit = max_ref(mean(outfit_vecs) ·
ref["vec"])` — **aucun re-fetch Pinecone** côté `RecommendationAgent`. Spécifié en §
Axe 2 / Fichiers et § Intégration RAG → classement.

### Finding 5 (MEDIUM) — Pas de ship-gate → TRAITÉ
Critère de publication explicite ajouté (§ Ship-gate) : `ranking_model.joblib` n'est
copié vers `backend/app/ml/artifacts/` que si l'AUC held-out du rangifieur bat la
baseline heuristique (`visual_coherence` seule) d'au moins **δ = +0.02 AUC**. Sinon
l'artefact reste absent → le runtime retombe sur l'heuristique exacte. Lien à la
section « Findings » du notebook. Le kill-switch reste en complément, mais le ship-gate
est désormais le critère de publication.

### Finding 6 (MEDIUM) — `test_context_agent.py` égalité exacte casse → TRAITÉ
L'assertion exacte `result == {"occasion", "weather", "season"}` est remplacée par des
vérifications de sous-ensemble : `result["occasion"] == "wedding"`, `result["weather"]
is None`, `result["season"] is None`, + assertions sur les nouvelles clés. Mentionné
explicitement en § Testabilité (axe 3).

### Finding 7 (MEDIUM) — Mapping `parse_occasion_rules` ambigu → TRAITÉ
Mapping **injectif** (un texte → exactement une catégorie), table complète des 8
catégories fournie (mots-clés FR/EN → catégorie/formality/dress_code), évaluation en
cascade (premier match gagne), fallback `casual_quotidien`. Spécifié en § Vocabulaire
contrôlé d'occasion.

### Finding 8 (MEDIUM) — Sources outfits de l'historique RAG → TRAITÉ
Précisé par source (§ Sources de retrieval) : `ScheduledOutfit` → `item_ids` + `date`
(natif, saison via `season_for_date`) ; `WearLog` → **regroupé par `date`** pour
reconstruire l'ensemble porté ce jour ; `Outfit` → **exclu** (pas de date de port ;
`created_at` = date de génération, sémantiquement incorrect). Aligné avec la liste
explicite de la tâche (`WearLog` + `ScheduledOutfit`).

### Finding 9 (NIT) — Comptage vecteurs incohérent → TRAITÉ
Décompte exact corrigé (§ Fallback ctx_vec) : 72 spécifiques (8×3×3) + 24
band-agnostiques (8×3) = **96 vecteurs stockés** (+ vecteur nul calculé à la volée).
Aucune combinaison `occasion=None` stockée. Taille ≈ 96 × 512 × 4 o ≈ **197 Ko**.

### Finding 10 (NIT) — Branche fallback « occasion hors-vocab » morte → TRAITÉ
Chaîne de fallback reformulée (§ Fallback ctx_vec) pour refléter le cas réel : le vrai
déclencheur du vecteur nul est `season=None` (pas d'occasion hors-vocab, puisque
`parse_occasion_rules` renvoie toujours une catégorie du vocabulaire). 3 branches :
spécifique → band-agnostic → nul.

### Finding 11 (NIT) — Localisation garde-fou `provider=="none"` → TRAITÉ
Précisé (§ Fichiers axe 3, llm_agent + Gestion d'erreurs axe 3) : la garde
`if self.settings.llm_provider == "none": return None` vit **en tête de `parse_occasion`,
`explain_outfit` et `run`**, avant toute résolution de provider ou appel à `_chat` —
donc avant tout `httpx.post`. `test_no_provider_returns_none_without_a_network_call`
reste vert.

### Finding 12 (NIT) — Formule fallback heuristique à répliquer exactement → TRAITÉ
Réplication exacte spécifiée (§ Axe 1, chemin fallback) :
`score = min(1.0, visual + (STYLE_MATCH_BONUS if style_match else 0.0))` puis
`score = max(0.0, score - RECENT_WEAR_PENALTY * recent)` où `recent` est le **nombre
entier** d'items portés récemment et `style_match` un booléen — conforme au code
`recommendation_agent.py` actuel vérifié.

### Finding 13 (NIT) — Comptage appels RAG dans l'orchestrateur → TRAITÉ
`references = retrieve_references(...)` est calculé **une seule fois, avant la closure
`generate`**, et passé aux deux appels `generate(...)` (§ Fichiers axe 3, orchestrator).
Évite de dupliquer les appels RAG/Pinecone (la closure est appelée jusqu'à 2× mais
`references` ne dépend que du contexte/DB, pas des items).

### Finding 14 (NIT) — Câblage kill-switches non spécifié → TRAITÉ
Section dédiée (§ Kill-switches) précise le point de lecture et l'effet de chaque flag :
`ranking_enabled` lu dans `ranking_model.score_outfit` (court-circuit avant
chargement d'artefact → heuristique) ; `contextual_rag_enabled` lu dans
`orchestrator.recommend_outfits` (skip de `retrieve_references`, `references=None`).
Le `conftest.py` force les deux à `False` en test par défaut.

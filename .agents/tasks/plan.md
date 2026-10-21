# Plan d'implémentation — Enrichissement du RecommendationAgent (3 axes)

> Source de vérité : `e:/Documents/Dress-Me/.agents/tasks/design.md` (APPROVED, Révision 2).
> Revue prise en compte : `design-review.md` — 4 MEDIUM (findings 1–4) + 6 NIT (5–10)
> sont intégrés ci-dessous comme corrections concrètes (chacune notée « review-F<n> »).
> Principe directeur : enrichir, pas réécrire ; fallbacks gracieux ; compatibilité
> arrière (kwargs optionnels) ; tests existants restent verts.

## Contexte vérifié dans le code (grounding)

- Build/test : `cd backend ; python -m pytest tests -q`. Python 3.12, sklearn 1.9.1
  runtime (les artefacts joblib existants ont été picklés en 1.5.0 → `InconsistentVersionWarning`
  non bloquante ; le nouveau `ranking_model.joblib` devrait idéalement être entraîné
  avec le sklearn du runtime pour l'éviter, mais le chargement reste fonctionnel).
- `get_settings()` est `@lru_cache` (`app/core/config.py`) → la surcharge en test se fait
  par `monkeypatch.setenv(...)` + `get_settings.cache_clear()` (review-F2). Patcher
  uniquement `app.core.config.get_settings` ne propage pas (les modules lient le nom
  à l'import), d'où l'approche env+cache.
- `recommendation_agent.run(self, *, wardrobe_items, occasion=None, favorite_styles=None,
  top_k=3, usage=None, today=None, **kwargs)` — `**kwargs` déjà présent. Constantes
  `STYLE_MATCH_BONUS=0.1`, `RECENT_WEAR_PENALTY=0.05`, `RECENT_WEAR_DAYS=3`. `_explain`
  est un template. `recent` = compte entier d'items portés récemment.
- `_FakeItem` de test n'a **pas** d'attribut `season` → utiliser `getattr(item,"season",None)`
  partout (review-F2a) pour éviter `AttributeError` sur le chemin artefact-présent.
- `LLMAgent.run(context, instruction) -> {"explanation": ...}` avec garde
  `provider=="none"` en tête ; `httpx.post(.../chat/completions, timeout=20.0)`.
  `StyleProfileAgent` consomme `run(...)["explanation"]` → `run` inchangé.
- `ContextAgent.run(occasion, weather, season, city) -> {occasion, weather, season}` ;
  `temperature` calculé seulement dans la branche lookup ville.
- `orchestrator.recommend_outfits` : closure `generate` appelée jusqu'à 2× → calculer
  `references` ET `ctx_vec` **une fois avant la closure** (review-F13, review-F1).
- `vector_store.fetch_embeddings(item_ids) -> dict[str, list[float]]` ; `is_configured()`.
  `delete_item_embedding` retire les items supprimés de Pinecone (review-F10).
- `catalog_index.CatalogIndex().search(embedding, *, category=None, limit)` ;
  `is_available()` ; `_load_index` `@lru_cache` ; `dressme_category` ∈
  `haut/bas/robe/veste/chaussures/sac/accessoire/hors_perimetre`.
- Modèles DB : `Outfit.explanation String(2048)` (pas de date de port) ;
  `ScheduledOutfit.date`+`item_ids` ; `WearLog` 1 ligne/(item, jour) (`UniqueConstraint(item_id,date)`) ;
  `ClothingItem.season/style/category/colors`.
- `seasons.py` : `season_for_date`, `season_compatible`, `COLD_BELOW_C=14`, `HOT_FROM_C=24`.
- ML entraînement : `ml/src/features.py` (`FASHIONCLIP_REPO="patrickjohncyh/fashion-clip"`,
  `embed_texts`, `load_fashionclip`, `embed_image_bytes` — **même modèle** que
  `backend/app/ml/vision_model.py` → espaces image/texte compatibles par construction) ;
  `ml/src/polyvore_official.py` (`load_outfit_structure`, `extract_image_bytes_batch`) ;
  `ml/src/catalog.py` `load_polyvore()` a `season=pd.NA`/`style=pd.NA` (vérifié →
  4/6 features non calculables à l'entraînement → couche déterministe additive, review-F1).
- Schéma API : `OutfitRecommendationResult.context: dict` (non typé) absorbe les nouvelles
  clés ; `OutfitRequest(occasion,weather,season,city)` inchangé → routes inchangées.
- Décision de non-casse « tests existants » : un `conftest.py` force
  `RANKING_ENABLED=False`/`CONTEXTUAL_RAG_ENABLED=False`/`LLM_PROVIDER=none` par défaut
  → les tests existants exercent le chemin fallback (heuristique exacte, pas de RAG,
  pas de LLM), indépendamment de la présence d'artefacts committés (review-F2).
- Résolution de la tension design/review sur `ctx_vec` (review-F1) : `run` accepte un
  kwarg optionnel `ctx_vec`. S'il est fourni (chemin orchestrateur), `run` l'utilise tel
  quel (évite le double calcul). S'il est `None` (appel direct / tests existants), `run`
  dérive `weather_band = occasions.weather_band(temperature)` puis
  `ctx_vec = ranking_model.context_vector(occasion_category, season, weather_band)`.
  `weather_band` n'est **jamais** un kwarg (toujours dérivé de `temperature` dans `run`).
  L'orchestrateur calcule `ctx_vec` une fois et le passe à `run` + `retrieve_references`.

## Décisions de review intégrées (résumé)

- review-F1 (MEDIUM) : `ctx_vec` calculé une fois dans l'orchestrateur, passé à `run`
  (kwarg `ctx_vec`) et à `retrieve_references` ; `weather_band` retiré de l'appel `generate`.
- review-F2 (MEDIUM) : `conftest.py` via `setenv` + `get_settings.cache_clear()` ; pinne
  `LLM_PROVIDER=none` pour isoler du `.env` dev.
- review-F3 (MEDIUM) : `parse_occasion_rules` par **token** (mots entiers), pas
  sous-chaîne (évite `"mer"` dans `"commercial"`).
- review-F4 (MEDIUM) : table `composition dressme_category → occasion_category`
  fournie dans le notebook 10 ; `sport`/`plage`/`voyage` faiblement couvrables sur Polyvore
  documentés ; ship-gate arbitre.
- review-F5 (NIT) : `compute_learned_features(visual, context_fit)` (2 args) ; les 4
  autres features sont la couche déterministe additive.
- review-F6 (NIT) : catalogue `category=None` (recherche cross-modale globale, retour
  groupé par `dressme_category` côté `RecommendationAgent`).
- review-F7 (NIT) : `explanation[:2048]` tronqué avant insertion `Outfit`.
- review-F8 (NIT) : `dress_code` validé contre un petit vocabulaire (sinon `None`).
- review-F9 (NIT) : ordre dans `ContextAgent.run` : lookup ville → saison →
  `parse_occasion(raw, hints={season,weather})` → ajout `temperature`/`weather_band`.
- review-F10 (NIT) : `WearLog` reconstruit en moyennant les items **présents** dans
  Pinecone (items supprimés ignorés ; groupe skip si <2 embeddings disponibles).
- review-F11 (NIT) : garde `provider=="none"` en tête de `parse_occasion`/`explain_outfit`
  avant `_chat` (aucun `httpx.post`).
- review-F12 (NIT) : formule fallback = heuristique existante **exacte**.
- review-F13 (NIT) : `references` calculées 1× avant la closure `generate`.
- review-F14 (NIT) : kill-switches `RANKING_ENABLED`/`CONTEXTUAL_RAG_ENABLED` câblés
  (défaut `True`), forcés `False` en test par le conftest.

---

# Plan ordonné (dépendances : 1→2→3→4→5→6…)

Chaque item laisse le dépôt buildable et les tests verts. Vérification de référence :
`cd backend ; python -m pytest tests -q` (suite complète). Les commandes ciblées
exécutent un sous-ensemble pour un feedback rapide.

## Axe 0 — Socle partagé (config, occasions, conftest, package rag)

- [ ] 1. Ajouter les kill-switches dans `backend/app/core/config.py` : `ranking_enabled:
  bool = True` et `contextual_rag_enabled: bool = True` (défaut `True`, review-F14).
      Files: backend/app/core/config.py
      Verify: `cd backend ; python -m pytest tests/test_health.py -q` — import OK,
      Settings charge les deux booléens.

- [ ] 2. Créer `backend/app/services/occasions.py` : `OCCASION_CATEGORIES` (8 catégories
  du design), `WEATHER_BANDS` (`froid`/`modere`/`chaud` cohérents avec seasons 14/24),
  `weather_band(temperature) -> str|None`, et `parse_occasion_rules(text) -> dict`
  avec matching **par token** (mots entiers, review-F3), table FR/EN → catégorie/formality/
  dress_code du design, évaluation en cascade (premier match gagne), fallback
  `casual_quotidien` quand `text` est `None` ou sans match. Toujours renvoyer une
  catégorie du vocabulaire (jamais `None` ni hors-vocab).
      Files: backend/app/services/occasions.py
      Verify: `cd backend ; python -m pytest tests/test_occasions.py -q` (créé item 7).

- [ ] 3. Créer `backend/tests/conftest.py` avec une fixture **autouse** qui
  `monkeypatch.setenv("RANKING_ENABLED","false")`, `setenv("CONTEXTUAL_RAG_ENABLED","false")`,
  `setenv("LLM_PROVIDER","none")`, `get_settings.cache_clear()` au setup, puis
  `get_settings.cache_clear()` au teardown (review-F2). Isole la suite du `.env` dev.
      Files: backend/tests/conftest.py
      Verify: `cd backend ; python -m pytest tests/test_recommendation_agent.py tests/test_context_agent.py tests/test_llm_agent.py -q` —
      17 tests existants toujours verts (chemin fallback actif par défaut).

- [ ] 4. Créer le package `backend/app/rag/__init__.py` (vide) pour `context_retrieval`.
      Files: backend/app/rag/__init__.py
      Verify: `cd backend ; python -c "import app.rag"` — import OK.

## Axe 1 — Fine-tuning du classement (modèle de ranking appris)

- [ ] 5. Créer `backend/app/ml/ranking_model.py` (runtime torch-free : sklearn+numpy) :
  `MODEL_PATH = .../artifacts/ranking_model.joblib`, `VECTORS_PATH = .../artifacts/context_vectors.npz`
  (même pattern que `compatibility_model.py`), `@lru_cache` sur `_load_model`/`_load_vectors` ;
  `context_vector(occasion_category, season, weather_band) -> np.ndarray` avec les 3
  branches de fallback du design (spécifique `occ|season|band` → band-agnostic
  `occ|season|_any` → `zeros(512)` quand `season=None`) ; `compute_learned_features(visual,
  context_fit) -> np.ndarray` (2 features, review-F5) ; `score_outfit(*, visual,
  context_fit=0.0, history_fit=0.0, season_compat=0.0, style_match=False, recent=0,
  ranking_enabled=True) -> float` : si `ranking_enabled` False OU `MODEL_PATH` absent →
  **heuristique existante exacte** (`min(1.0, visual + (STYLE_MATCH_BONUS if style_match
  else 0.0))` puis `max(0.0, score - RECENT_WEAR_PENALTY*recent)`, review-F12) sans toucher
  l'artefact ; sinon chemin artefact-présent (`learned = predict_proba(...) ; base =
  learned + SEASON_COMPAT_BONUS*season_compat + (STYLE_MATCH_BONUS if style_match else 0)
  + HISTORY_FIT_WEIGHT*history_fit ; score = clamp(0,1, base - RECENT_WEAR_PENALTY*recent)`).
  Clamp explicite → invariant `score ∈ [0,1]`. Log INFO une fois sur l'absence d'artefact.
  Dépend de l'item 2 (occasions.weather_band/OCCASION_CATEGORIES) et seasons existant.
      Files: backend/app/ml/ranking_model.py
      Verify: `cd backend ; python -m pytest tests/test_ranking_model.py -q` (créé item 8).

- [ ] 6. Créer `ml/notebooks/10_ranking_model.py` (mirrors notebook 09) : réutilise
  `polyvore_official.load_outfit_structure` + `features.embed_image_bytes` + cache
  `compatibility_embeddings.npz` pour les vecteurs items ; `compatibility_model.pair_compatibility`
  pour `visual_coherence`. **Table `composition dressme_category → occasion_category`**
  (review-F4) : `{robe, chaussures, sac}` → `ceremonie`/`mariage` ; `{haut, bas, veste,
  chaussures}` → `travail` ; `{haut, bas}` → `casual_quotidien` ; compositions sans
  robe/veste → `casual_quotidien` ; documenter `sport`/`plage`/`voyage` faiblement
  couvrables sur Polyvore. Saison déduite, `weather_band` plausible aléatoire. Négatifs :
  (i) même outfit + contexte incohérent, (ii) assemblage aléatoire + contexte quelconque.
  Précalcule `context_vectors.npz` via `features.embed_texts` (96 vecteurs : 72 spécifiques
  + 24 band-agnostiques). Entraîne `LogisticRegression(max_iter=2000, class_weight="balanced")`
  sur **(visual_coherence, context_fit)**. **Ship-gate** : copie `ranking_model.joblib`
  vers `backend/app/ml/artifacts/` uniquement si AUC held-out bat la baseline
  (`visual_coherence` seule) d'≥ +0.02 AUC ; sinon laisse l'artefact absent. Section
  « Findings » à remplir après exécution (honnêteté comme le notebook 09).
      Files: ml/notebooks/10_ranking_model.py
      Verify: `cd ml ; python notebooks\10_ranking_model.py` (requiert env ml/ + dataset
      Polyvore téléchargé ; si le ship-gate passe, copie les artefacts ; sinon les laisse
      absents → runtime fallback). Si l'env/données ml/ sont indisponibles, l'artefact
      reste absent et `cd backend ; python -m pytest tests/test_ranking_model.py -q`
      confirme le fallback heuristique (aucun artefact requis).

## Axe 2 — RAG contextuel

- [ ] 7. Créer `backend/app/rag/context_retrieval.py` : `retrieve_references(db, user_id,
  context, ctx_vec, *, top_n_history=3, top_k_catalog=3) -> dict` retournant
  `{"historical": [{"item_ids","score","date","season","vec"}, ...], "catalog":
  {category: [CatalogMatch.to_dict(), ...]}}`.
  - `historical` : `ScheduledOutfit` (owner=user_id) + regroupement `WearLog` par `date`
    (review-F8) ; `vec` = vecteur moyen de l'outfit de référence (review-F4, évite un
    re-fetch) ; fetch via `vector_store.fetch_embeddings` ; moyenne sur les items
    **présents** dans Pinecone, skip du groupe si <2 embeddings disponibles (review-F10) ;
    score = `mean(item_vecs)·ctx_vec + bonus season_compat(season_for_date(date),
    context["season"])` ; top-N. Pinecone non configuré → `fetch_embeddings` renvoie `{}`
    → `historical=[]` (dégradation gracieuse). Erreur DB → `historical=[]` + WARNING.
  - `catalog` : `CatalogIndex().search(ctx_vec, category=None, limit=top_k_catalog)`
    (review-F6 : recherche cross-modale globale, pas de mapping occasion→catégorie) ;
    `is_available()==False` → `catalog={}`. Regroupement par `dressme_category` côté
    `RecommendationAgent`.
  Aucun accès DB dans `vector_store` (garde sa responsabilité bas-niveau). Dépend de
  seasons existant, models existants, items 1 (contextual_rag_enabled) et 4 (package rag).
      Files: backend/app/rag/context_retrieval.py
      Verify: `cd backend ; python -m pytest tests/test_context_retrieval.py -q` (créé item 9).

## Axe 3 — Prompt engineering + activation LLM (partie agents)

- [ ] 8. Créer `backend/app/agents/prompts.py` : fonctions pures `occasion_parse_prompt(
  raw_occasion, context_hints) -> list[message]` (system JSON-only + `response_format
  json_object`) et `explain_outfit_prompt(facts) -> list[message]` (system « n'invente
  jamais de faits, 1–2 phrases + 1–2 suggestions d'ajustement avec raison »). Testables
  sans réseau.
      Files: backend/app/agents/prompts.py
      Verify: `cd backend ; python -m pytest tests/test_prompts.py -q` (créé item 10).

- [ ] 9. Modifier `backend/app/agents/llm_agent.py` : extraire `_chat(messages, *,
  json_mode=False, timeout=20.0) -> str` (POST + `raise_for_status` + extraction
  `choices[0].message.content`). Garder `run(context, instruction)` inchangé (appelle
  `_chat`, retour `{"explanation":...}`). Ajouter `parse_occasion(raw_occasion,
  context_hints) -> dict|None` (garde `provider=="none"` → `None` **en tête avant _chat**,
  review-F11 ; `_chat(occasion_parse_prompt(...), json_mode=True)` ; valide
  `occasion_category ∈ OCCASION_CATEGORIES`, `formality` 1–5, `dress_code` contre le
  vocabulaire du design (review-F8) ; toute erreur → WARNING + `None`). Ajouter
  `explain_outfit(facts) -> str|None` (même garde `provider=="none"` en tête ; erreur →
  WARNING + `None`). Aucune nouvelle dépendance (httpx déjà présent).
      Files: backend/app/agents/llm_agent.py
      Verify: `cd backend ; python -m pytest tests/test_llm_agent.py -q` — tests existants
      verts + nouveaux (parse/explain provider=none sans réseau, récupération erreurs).

- [ ] 10. Modifier `backend/app/agents/context_agent.py` : `run` accepte un `LLMAgent`
  injecté (défaut `LLMAgent()`) pour testabilité. Ordre (review-F9) : (1) lookup ville →
  weather/temperature ; (2) `normalize_season`/`season_from_temperature` ; (3)
  `parse_occasion(raw_occasion, hints={"season":season,"weather":weather})` si LLM dispo
  (non-None), sinon `occasions.parse_occasion_rules` ; (4) ajout `temperature`,
  `weather_band=occasions.weather_band(temperature)`, `occasion_category`, `formality`,
  `dress_code`. Clés existantes (`occasion`,`weather`,`season`) **conservées**.
      Files: backend/app/agents/context_agent.py
      Verify: `cd backend ; python -m pytest tests/test_context_agent.py -q` —
      `test_no_city_leaves_weather_none` relâché en assertions de sous-ensemble
      (review-F6) + nouvelles clés vérifiées.

## Axe 3 — Intégration (capstone : lie les 3 axes)

- [ ] 11. Modifier `backend/app/agents/recommendation_agent.py` : `run` gagne les kwargs
  optionnels **rétro-compatibles** `season, temperature, weather, occasion_category,
  formality, references, ctx_vec` (tous défaut `None` ; `**kwargs` déjà présent). Début de
  `run` : si `ctx_vec` est None → `weather_band = occasions.weather_band(temperature)` puis
  `ctx_vec = ranking_model.context_vector(occasion_category, season, weather_band)`
  (résolution review-F1/F3) ; sinon utiliser le `ctx_vec` fourni. Calcul de `visual_coherence`
  (mean pairwise) et génération de candidats **inchangés**. Calculer `context_fit =
  mean(outfit_vecs)·ctx_vec`, `season_compat` (fraction d'items avec
  `seasons.season_compatible(getattr(item,"season",None), season)` — review-F2a),
  `history_fit = max(ref["vec"]·mean(outfit_vecs) for ref in references["historical"])`
  (utilise `vec` retourné, pas de re-fetch — review-F4) si `references` fourni sinon 0.
  Score via `ranking_model.score_outfit(..., ranking_enabled=get_settings().ranking_enabled)`.
  Explication : si un `LLMAgent` est injecté et `explain_outfit(facts)` renvoie une
  chaîne → l'utiliser (tronquée `[:2048]` — review-F7) ; sinon `_explain` (template
  **conservé**) enrichi d'une note d'ajustement déterministe (ex. `weather_band=="chaud"`
  et un item `bas` d'`season=="hiver"` → suggérer une pièce plus légère), repliée dans
  `explanation`. Ajustements repliés dans `explanation` (pas de nouvelle colonne —
  décision schéma du design).
      Files: backend/app/agents/recommendation_agent.py
      Verify: `cd backend ; python -m pytest tests/test_recommendation_agent.py -q` —
      tests existants verts sur le chemin fallback (conftest) + nouveaux cas
      (`ranking_enabled=True` + faux modèle sklearn via monkeypatch MODEL_PATH +
      cache_clear : ordre respecte `context_fit` ; LLM off → template ; LLM mocké →
      explication injectée).

- [ ] 12. Modifier `backend/app/agents/orchestrator.py` `recommend_outfits` : après
  `context = context_agent.run(...)` (maintenant enrichi), calculer **une fois avant la
  closure `generate`** (review-F1, review-F13) : `weather_band =
  occasions.weather_band(context.get("temperature"))`, `ctx_vec =
  ranking_model.context_vector(context.get("occasion_category"), context.get("season"),
  weather_band)` ; si `get_settings().contextual_rag_enabled` →
  `references = context_retrieval.retrieve_references(self.db, user_id, context, ctx_vec)`
  sinon `references = None`. La closure `generate` passe à `run` : `occasion, favorite_styles,
  usage, season, temperature, weather, occasion_category, formality, references, ctx_vec`
  (PAS `weather_band` — review-F1). Bloc dédup/insertion `Outfit` **inchangé** (mais
  `explanation` déjà tronqué côté `run`).
      Files: backend/app/agents/orchestrator.py
      Verify: `cd backend ; python -m pytest tests/test_recommendation_agent.py -q` —
      les tests d'intégration (orchestrateur mocké/exercé) passent.

- [ ] 13. Mettre à jour `backend/.env.example` : documenter `LLM_PROVIDER=mistral` +
  `LLM_API_KEY` (free tier) et les kill-switches `RANKING_ENABLED`/`CONTEXTUAL_RAG_ENABLED`
  (commentés, défaut `true`).
      Files: backend/.env.example
      Verify: inspection visuelle (pas de test automatisé) + `cd backend ; python -m pytest tests -q` vert.

## Tests (nouveaux fichiers — créés avec leur axe)

- [ ] 14. Créer `backend/tests/test_occasions.py` : `parse_occasion_rules` mapping injectif
  (un texte → une catégorie), table FR/EN, fallback `casual_quotidien`, **pas de faux
  positif** (`"centre commercial"` → `casual_quotidien`, pas `plage` — review-F3) ;
  `weather_band` bornes 14/24 et `None`.
      Files: backend/tests/test_occasions.py
      Verify: `cd backend ; python -m pytest tests/test_occasions.py -q`.

- [ ] 15. Créer `backend/tests/test_ranking_model.py` : `context_vector` indexation + 3
  branches de fallback ; `score_outfit` sans artefact = heuristique exacte ; avec faux
  modèle sklearn (monkeypatch MODEL_PATH vers tmp_path joblib + `_load_model.cache_clear`)
  = formule artefact ; absence `context_vectors` → `context_fit=0` sans crash ;
  monotonicité (`visual_coherence` plus haut → score plus haut à contexte constant).
      Files: backend/tests/test_ranking_model.py
      Verify: `cd backend ; python -m pytest tests/test_ranking_model.py -q`.

- [ ] 16. Créer `backend/tests/test_context_retrieval.py` : SQLite en mémoire
  (`create_engine("sqlite://", poolclass=StaticPool)` + `Base.metadata.create_all`) +
  `ScheduledOutfit`/`WearLog` seedés (WearLog groupé par date) + `monkeypatch` de
  `vector_store.fetch_embeddings` (vecteurs fixes) → `historical` ordonné par `ctx_vec` ;
  `ctx_vec` hiver ramène les outfits hiver en tête ; chaque entrée contient `vec` ;
  Pinecone off (`fetch_embeddings→{}`) → `historical=[]` ; catalogue mocké
  (`catalog_index._load_index`) → non vide.
      Files: backend/tests/test_context_retrieval.py
      Verify: `cd backend ; python -m pytest tests/test_context_retrieval.py -q`.

- [ ] 17. Créer `backend/tests/test_prompts.py` : `occasion_parse_prompt`/`explain_outfit_prompt`
  retournent les messages attendus (rôles system/user, contenu sans réseau).
      Files: backend/tests/test_prompts.py
      Verify: `cd backend ; python -m pytest tests/test_prompts.py -q`.

- [ ] 18. Étendre `backend/tests/test_llm_agent.py` : `parse_occasion`/`explain_outfit`
  `provider=none` → `None` sans appel (`httpx.post` mocké en `fail_if_called`) ;
  `provider=mistral` + `monkeypatch httpx.post` (faux JSON) → dict validé ; JSON
  invalide/catégorie hors-vocab/formality hors [1,5] → `None` (récupération). `run`
  existant reste vert.
      Files: backend/tests/test_llm_agent.py
      Verify: `cd backend ; python -m pytest tests/test_llm_agent.py -q`.

- [ ] 19. Étendre `backend/tests/test_context_agent.py` : occasion libre texte →
  `occasion_category` via règles (LLM off) ; `temperature`/`weather_band` présents ;
  assertions exactes `== {...}` remplacées par sous-ensemble (review-F6) ;
  comportements existants (météo explicite non écrasée, ville sans clé météo → None)
  inchangés.
      Files: backend/tests/test_context_agent.py
      Verify: `cd backend ; python -m pytest tests/test_context_agent.py -q`.

- [ ] 20. Étendre `backend/tests/test_recommendation_agent.py` : sur le chemin fallback
  par défaut (conftest), tests existants **inchangés et verts** (assertion
  `-1 ≤ score ≤ 1` reste vraie). Nouveaux cas `ranking_enabled=True` + faux modèle
  sklearn : ordre respecte `context_fit` (un outfit cohérent avec le contexte bat un
  outfit visuellement équivalent mais hors-contexte) ; LLM off → explication template ;
  LLM mocké → explication LLM injectée.
      Files: backend/tests/test_recommendation_agent.py
      Verify: `cd backend ; python -m pytest tests/test_recommendation_agent.py -q`.

## Vérification finale

- [ ] 21. Suite complète + aucun test existant cassé.
      Files: (aucun)
      Verify: `cd backend ; python -m pytest tests -q` — tous les tests passent (existants
      + nouveaux). Vérifier que le chemin fallback (conftest flags False) reste actif par
      défaut et que les nouveaux tests réactivent les flags localement.

## Notes de risque / backlog (documentés, non implémentés)

- Le rangifieur est entraîné sur faibles labels synthétiques (match/non-match) — signal
  relatif, pas de pertinence réelle. Ship-gate = filet de sécurité (commit seulement si
  gain AUC ≥ +0.02). Honnêtement documenté dans le notebook (comme le 09).
- Poids déterministes `SEASON_COMPAT_BONUS`/`HISTORY_FIT_WEIGHT` fixés à `0.1`,
  calibrés à la main (non appris, non optimisés) — tunables ; calibration fine en backlog.
- Colonne structurée `adjustments` (JSONList) en backlog si le review le demande ;
  par défaut les ajustements sont repliés dans `explanation`.
- `n8n` non nécessaire — tout reste dans le backend Python (décision déjà entérinée).

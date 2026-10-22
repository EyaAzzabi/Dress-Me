# DressMe — Analyse de l'état d'avancement des objectifs

> Rapport d'analyse read-only du projet `e:\Documents\Dress-Me`. Chaque statut est
> justifié par du code réellement lu (fichiers/agents/routes/migrations/frontend).

## Résumé (TL;DR)

DressMe est un assistant de mode personnel (IA) permettant de construire un dressing
numérique depuis des photos, obtenir des recommandations de tenues, planifier des
outfits sur un calendrier (avec rendu d'avatar), préparer une valise, et évaluer un
achat. La **partie backend (FastAPI + agents IA + ML + données tunisiennes) est
largement complète et mature** : tous les agents décrits dans le README existent et
contiennent une vraie logique (aucun stub, aucun `TODO`/`NotImplementedError` dans le
code applicatif). Le pipeline ML/data-understanding (notebooks, scraping de 9 marques
tunisiennes, catalogue unifié de 418 686 articles, modèles entraînés) est terminé.

Les **frontends sont complets sur la plupart des écrans**, mais avec une asymétrie
marquée : l'**app mobile (Expo/React Native) est la plus complète** (notamment toute
l'expérience achat : wishlist, prix live, marques tunisiennes, panier), tandis que
l'**app web (React+Vite) reste partielle sur la fonctionnalité « J'achète ou pas ? »**
(vérification basique uniquement, pas de wishlist ni de prix live ni de facteurs
détaillés).

Les **limites fonctionnelles connues** (documentées par l'équipe elle-même dans le
README, section « Where we are / what's next ») sont surtout : le `RecommendationAgent`
n'utilise pas réellement l'occasion/la météo pour filtrer ou classer les tenues ; le
`ContextAgent` ne fait que le complément règles (pas d'analyse LLM du texte libre) ;
le `LLMAgent` est éteint par défaut (`LLM_PROVIDER=none`) ; il n'y a pas d'agent
calendrier dédié (les routes calendrier appellent directement le `TryOnAgent`, pas
l'orchestrateur).

**Évaluation globale : ~85 % réalisé**. Le cœur produit est solide et utilisable ;
le travail restant est de l'enrichissement (qualité des recommandations, calibration,
parité web/mobile sur l'achat) plutôt que du squelette à combler.

## Objectif du projet

D'après le README et `docs/IDEATION_RATIONALE.md`, DressMe vise (personas : Lina, Maha,
Ahmed, Iskander) :

- **Objectifs business** : 01 — maximiser la valeur du dressing existant ; 02 —
  expérience de mode personnalisée ; 03 — favoriser des achats intentionnels ;
  05 — valoriser l'écosystème mode tunisien.
- **Objectifs data science** : 01 extraction d'attributs, 02 représentation vectorielle,
  03 modélisation dynamique du profil utilisateur, 04 modélisation contextuelle,
  05 classement personnalisé d'outfits, 06 détection de manques dans le dressing.

Idées/features dérivées : Smart Wardrobe, Smart Outfit, Context-Aware Styling, Style
Learning, « Should I Buy This? », Wardrobe Gap Detection, Local Fashion Matching,
Virtual Try-On (initialement « future exploration », finalement implémenté).

## Tableau de synthèse — état par feature

| # | Feature / Objectif | Composants | Statut |
|---|---|---|---|
| 1 | **Smart Wardrobe** (dressing numérique) | VisionAgent, MetadataAgent, routes `/wardrobe` | ✅ Réalisé (complet) |
| 2 | **Smart Outfit** (recommandation de tenues) | RecommendationAgent, routes `/recommendations` | ⚠️ En cours (partiel) |
| 3 | **Context-Aware Styling** (contexte occasion/météo/saison) | ContextAgent, WeatherService | ⚠️ En cours (partiel) |
| 4 | **Style Learning** (profil de style) | StyleProfileAgent, route `/style-profile` | ✅ Réalisé (complet, narratif LLM optionnel) |
| 5 | **« Should I Buy This? »** (achat intelligent) | PurchaseAgent, routes `/purchase` | ✅ Réalisé (complet backend) |
| 6 | **Wardrobe Gap Detection** (détection de manques) | — (implicitement via PurchaseAgent) | ⚠️ En cours (partiel) |
| 7 | **Local Fashion Matching** (matching mode tunisien) | CatalogIndex, `tunisian_brands`, `store_checkout`, scraping | ✅ Réalisé backend / ⚠️ partiel web |
| 8 | **Virtual Try-On** (essayage virtuel + avatar calendrier) | TryOnAgent, routes `/tryon`, `/calendar/{day}/render` | ✅ Réalisé (complet) |
| 9 | **Calendrier / planning d'outfits** | routes `/calendar`, modèle `ScheduledOutfit` | ✅ Réalisé (mais hors-orchestrateur) |
| 10 | **Valise intelligente** (packing) | PackingAgent, routes `/packing` | ✅ Réalisé (complet) |
| 11 | **Authentification** (JWT) | routes `/auth`, `core/security` | ✅ Réalisé (complet) |
| 12 | **LLMAgent** (explications en langage naturel) | LLMAgent | ⚠️ Réalisé mais désactivé par défaut |
| 13 | **Pipeline ML / Data Understanding** | `ml/notebooks/*`, `ml/scraping/*`, `ml/src/*` | ✅ Réalisé (complet) |
| 14 | **Frontend mobile** | `frontend/mobile/src/screens/*` | ✅ Réalisé (complet, le plus riche) |
| 15 | **Frontend web** | `frontend/web/src/App.tsx` | ✅ Réalisé / ⚠️ partiel sur l'achat |

Légende : ✅ Réalisé (complet) · ⚠️ En cours (partiel) · ❌ Non commencé / Stub.

## Détail et preuves par feature

### 1. Smart Wardrobe — ✅ Réalisé (complet)
- `VisionAgent` (`backend/app/agents/vision_agent.py`) : embeddings FashionCLIP,
  catégorie via classifieur linéaire entraîné (81–84 %), zéro-shot couleur/motif/style/
  saison, dictionnaire de confiance par attribut. Logique réelle, pas de stub.
- `MetadataAgent` (`backend/app/agents/metadata_agent.py`) : ajout/correction/suppression,
  recherche multi-filtres (catégorie/saison/style/couleur/texte libre), historique
  d'usage dérivé du calendrier + `WearLog`. Toutes les méthodes implémentées.
- Routes `/wardrobe` (`backend/app/api/routes/wardrobe.py`) : upload, list, usage,
  POST (avec gestion 422 `low_category_confidence`), PATCH, POST `/{id}/worn`, DELETE.
- Seuil de confiance catégorie `CATEGORY_MIN_CONFIDENCE` = 0.50, calibré sur photos
  catalogue (noté « à revoir avec de vraies photos téléphone »).

### 2. Smart Outfit — ⚠️ En cours (partiel)
- `RecommendationAgent` (`backend/app/agents/recommendation_agent.py`) : génère des
  combinaisons compatibles, score de cohérence visuelle (modèle Polyvore 68 306 outfits,
  `app/ml/compatibility_model.py`), bonus de style (style favori #1), pénalité de
  fraîcheur (pièces portées récemment). Fonctionne réellement.
- **Limite documentée** : `occasion` et `weather` n'apparaissent que dans le texte
  d'explication (`_explain`) et **n'influencent pas le choix/classement**. Le README
  le liste en tête des « Suggested next work ». Aucune règle d'harmonie des couleurs ni
  variété entre tenues proposées n'est encore implémentée.

### 3. Context-Aware Styling — ⚠️ En cours (partiel)
- `ContextAgent` (`backend/app/agents/context_agent.py`) : normalise la saison, et
  quand on donne une `city` sans `weather`, remplit la météo via `WeatherService`
  (OpenWeather) et infère la saison depuis la température. Logique réelle.
- **Limite documentée** dans la docstring de l'agent : l'approche prévue (LLM + règles)
  parse le texte libre (« je vais a un mariage ce soir ») en champs structurés via le
  `LLMAgent`. Ce côté « parsing LLM » **n'est pas implémenté** — seul le complément
  règle-based est fait. Sans clé API OpenWeather, la météo reste vide (optionnel).

### 4. Style Learning — ✅ Réalisé (complet, narratif optionnel)
- `StyleProfileAgent` (`backend/app/agents/style_profile_agent.py`) : calcule les
  faits (comptes catégorie/couleur/style) directement depuis le dressing, top-3 styles/
  couleurs préférés. Le narratif est confié au `LLMAgent` (optionnel, `none` par défaut →
  `narrative: null`, mais le profil reste complet). « Frequent occasions » et historique
  de feedback ne sont pas tracés (aucune table) — l'agent le dit explicitement plutôt que
  de fabriquer.

### 5. « Should I Buy This? » — ✅ Réalisé (complet backend)
- `PurchaseAgent` (`backend/app/agents/purchase_agent.py`, ~18 Ko) : verdict 0–100 sur
  4 facteurs explicables (polyvalence, originalité, cohérence de style, prix), modèle
  de compatibilité Polyvore + calibration, détection de doublons, tenues débloquées,
  coût par port estimé, alternatives catalogue (liens marque), marques tunisiennes
  (affinité visuelle). Gestion `hors_perimetre` et garde-robe vide. Implémentation
  riche et complète.
- Routes `/purchase` (`backend/app/api/routes/purchase.py`) : `/extract` (découpe
  multi-vêtements), `/check`, `/history` (liste/suppr/vider), `/products/{key}/live`
  (prix/tailles/stock + checkout), `/wishlist` (add/remove + prix live + baisse de prix).
- `ExtractionAgent` (`backend/app/agents/extraction_agent.py`) : segmentation des
  vêtements sur photo de personne, découpe sur fond blanc, classification par morceau.
  Implémenté.

### 6. Wardrobe Gap Detection — ⚠️ En cours (partiel)
- Aucun agent/route dédié à la « détection de manques » proactive. La capacité est
  **implicitement** présente via le `PurchaseAgent` (originalité = 1 - redondance avec
  l'article le plus proche de la même catégorie ; polyvalence = tenues débloquées), qui
  répond à « cette pièce comble-t-elle un manque ? » mais seulement sur un candidat
  proposé par l'utilisateur, pas en suggérant ce qui manque. Objectif DS 06 partiellement
  couvert.

### 7. Local Fashion Matching — ✅ Réalisé backend / ⚠️ partiel web
- `CatalogIndex` (`backend/app/services/catalog_index.py`) : recherche visuelle sur le
  catalogue tunisien (embeddings pré-calculés `app/data/catalog_embeddings.npz`),
  affinité de marque, produit par `item_key`. Implémenté.
- `tunisian_brands.py`, `store_checkout.py`, `ecommerce.py` : liens d'achat, prix live
  (tailles/stock/checkout vers le site de la marque). Implémentés.
- Scraping (`ml/scraping/`) : 9 marques tunisiennes scrapées (Hamadi Abid, Barsha,
  Chedly Sisters, Noonclo, Kontakt, Lyoum, Rooh, MyJebba, Ileycom) + respect
  `robots.txt` documenté. Terminé.
- **Asymétrie frontend** : la **mobile** expose tout (wishlist, prix live, marques,
  checkout — `src/components/purchase/*`, `src/api/purchase.ts`). Le **web** expose
  seulement une version simplifiée de `/purchase/check` (voir §Frontend web).

### 8. Virtual Try-On — ✅ Réalisé (complet)
- `TryOnAgent` (`backend/app/agents/tryon_agent.py`) : deux fournisseurs (Replicate payant
  ou Hugging Face Space gratuit OOTDiffusion), chaînage multi-vêtements (`run_outfit`),
  ordre de superposition, persistance du résultat. Implémenté.
- Routes `/tryon` (set avatar, try-on simple) et `/calendar/{day}/render` (avatar
  habillé de l'outfit du jour, avec cache par signature de rendu). Implémentées.
- Dépend de clés/config externes (`TRYON_PROVIDER`, `HF_TOKEN` ou Replicate) ;
  `is_configured()` renvoie 503 clair si manquant.

### 9. Calendrier / planning — ✅ Réalisé (mais hors-orchestrateur)
- Routes `/calendar` (`backend/app/api/routes/calendar.py`) : PUT planifier,
  POST render, GET (jour + plage), DELETE. Modèle `ScheduledOutfit` avec cache de
  rendu (`render_signature`). Implémenté.
- **Note structurelle** : pas de `CalendarAgent` ; les routes calendrier appellent
  directement le `TryOnAgent`, pas via l'`AgentOrchestrator`. Le README le liste comme
  travail suivant (« Route the calendar endpoints through the orchestrator »).

### 10. Valise intelligente (packing) — ✅ Réalisé (complet)
- `PackingAgent` (`backend/app/agents/packing_agent.py`) : quantités par catégorie selon
  durée, saison (date/météo destination), style selon type de voyage, historique
  d'usage, inclusion prioritaire des pièces déjà planifiées dans le calendrier pour les
  jours du voyage. Heuristique explicable, implémentée.
- Routes `/packing` : create, list, get, patch (cocher/décocher), delete. Implémentées.
- L'orchestrateur (`plan_trip`) chaîne ContextAgent (saison depuis météo) + MetadataAgent
  + PackingAgent. Cohérent.

### 11. Authentification — ✅ Réalisé (complet)
- Routes `/auth` (`backend/app/api/routes/auth.py`) : register, login (JWT), me.
  `core/security.py` (hash/verify). Implémentées.

### 12. LLMAgent — ⚠️ Réalisé mais désactivé par défaut
- `LLMAgent` (`backend/app/agents/llm_agent.py`) : client OpenAI-compatible (OpenAI/
  Mistral/Llama), renvoie `{explanation: None}` si `LLM_PROVIDER=none` (défaut).
  Seul consommateur actuel : `StyleProfileAgent` (narratif). Implémenté, mais off par
  défaut — le README suggère de l'activer avec un fournisseur gratuit.

### 13. Pipeline ML / Data Understanding — ✅ Réalisé (complet)
- `ml/notebooks/01..09` : data understanding, réconciliation taxonomie, catalogue unifié,
  FashionCLIP, weak-labels motif, classifieur catégorie, modèle de compatibilité.
- `ml/src/catalog.py` : catalogue unifié de **418 686 articles** (Polyvore 365 054 +
  Kaggle 44 424 + ~9 200 tunisiens), schéma commun, split stratifié.
- Artefacts entraînés embarqués dans `backend/app/ml/artifacts/` (le runtime ne
  ré-entraîne pas). Tests ML dédiés (`tests/test_*_model.py`, `test_catalog_index.py`).

### 14. Frontend mobile — ✅ Réalisé (complet)
- `frontend/mobile/src/screens/` : Wardrobe, OutfitRecommendations, Calendar, StyleProfile,
  Packing, PurchaseCheck, TryOn, Login, Onboarding — tous présents avec composants
  riches (`components/purchase/*` : ShoppingSpace, CheckoutSheet, TunisianBrands,
  CatalogAlternatives, CostPerWearCard, PriceInsightCard, ScoreVerdictCard, etc.).
- API complète (`src/api/purchase.ts`) : extract, check (résultat complet avec
  facteurs/doublons/prix/cost-per-wear/marques), historique, **prix live**, **wishlist**
  (add/remove + baisse de prix). C'est le frontend de référence pour l'achat.

### 15. Frontend web — ✅ Réalisé / ⚠️ partiel sur l'achat
- `frontend/web/src/App.tsx` (un seul fichier, ~68 Ko) : 8 écrans (accueil, dressing,
  idées de looks, calendrier, mon style, valise, j'achète ou pas ?, essayage). Écrans
  wardrobe/outfits/calendar/profile/packing/tryon complets.
- **Achat partiel** : `frontend/web/src/api.ts` ne type `PurchaseResult` qu'avec
  `verdict, compatibility_score, similar_item_ids, catalog_alternatives, explanation`.
  Aucun type wishlist, prix live, marques tunisiennes, facteurs, cost-per-wear, historique.
  Les « favoris » web sont uniquement locaux (localStorage) sur les pièces du dressing,
  pas la wishlist catalogue. → L'expérience shopping complète n'existe que sur mobile.

## Points incomplets / limites clés (récapitulatif)

1. **RecommendationAgent** : occasion/météo non utilisés pour filtrer/classer (texte
   d'explication seulement) ; pas d'harmonie de couleurs ni de variété entre tenues ;
   pas de jeu étiqueté main pour mesurer la qualité. *(README « next work » #1)*
2. **ContextAgent** : seul le complément règle-based (météo→saison) est fait ; le
   parsing LLM du texte libre d'occasion n'est pas implémenté. *(docstring de l'agent)*
3. **LLMAgent** : implémenté mais `none` par défaut → narratif de style désactivé par
   défaut. *(README « next work » #2)*
4. **PurchaseAgent / StyleProfileAgent** : « pas encore revus/améliorés » selon le
   README (#3). Le profil de style ne trace ni les occasions fréquentes ni l'historique
   de feedback (aucune table).
5. **Calendrier hors-orchestrateur** : pas de `CalendarAgent` ; routes calendrier
   appellent `TryOnAgent` directement. *(README « next work » #5)*
6. **Calibration sur vraies photos** : seuils de confiance (catégorie/style/saison)
   calibrés sur photos catalogue, à revoir avec de vraies photos téléphone. *(README #4)*
7. **Parité web/mobile sur l'achat** : le web n'a que la vérification basique ; wishlist,
   prix live, marques, facteurs détaillés et historique d'achat absents côté web.
8. **Gap detection** : aucun endpoint/agent proactif suggérant les manques du dressing
   (seul le PurchaseAgent y répond indirectement, sur candidat fourni).
9. **Dépendances externes optionnelles** : sans `PINECONE_API_KEY`, les recommandations
   ne renvoient rien ; sans `LOCAL_STORAGE_DIR`, l'upload photo renvoie 503 ; sans config
   try-on, l'essayage/avatar renvoie 503 ; sans `OPENWEATHER_API_KEY`, météo vide. Ce ne
   sont pas des bugs mais des capacités conditionnées à la configuration.

## Absence notable de dette technique visible

Recherche `TODO|FIXME|XXX|HACK|NotImplementedError|not implemented|stub` dans tout le
backend Python : **aucun match**. Dans le frontend TS/TSX, les seuls matchs sont des
`placeholder` d'UI (champs de saisie) et un commentaire explicatif sur le polyfill
FormData RN — aucun code stub. Le projet est propre et mature.

## Évaluation globale et recommandations (priorité suggérée)

**État global : ~85 % réalisé.** Le backend, le pipeline ML/données et l'app mobile sont
essentiellement complets et utilisables. Le restant est de l'enrichissement.

Recommandations (sans rien implémenter ici) :

1. **Qualité des recommandations** (plus grosse valeur produit) : brancher
   `occasion`/`weather` sur le filtre et le score dans `RecommendationAgent.run`,
   ajouter des règles d'harmonie de couleurs et de la variété entre tenues, puis un
   petit jeu étiqueté main pour mesurer.
2. **Parité web sur l'achat** : porter la wishlist + prix live + marques + facteurs
   détaillés du mobile vers le web (les endpoints backend existent déjà).
3. **Activer le LLM** : `LLM_PROVIDER=mistral` (free tier) ou Llama/Ollama local, pour
   le narratif de style et le parsing d'occasion (ContextAgent).
4. **Agent calendrier** : introduire un `CalendarAgent` et faire passer les routes
   `/calendar` par l'orchestrateur (cohérence d'architecture).
5. **Gap detection proactif** : un endpoint « pièces manquantes » calculant les
   catégories sous-représentées / manquantes pour compléter des tenues (objectif DS 06).
6. **Calibration** : revoir les seuils de confiance (catégorie/style/saison) sur de
   vraies photos téléphone, et tracer les occasions fréquentes + feedback pour le
   `StyleProfileAgent` (nouvelle table).

---

*Note méthode : analyse statique read-only. Les commandes de vérification du projet
sont `cd backend && python -m pytest tests -q` (tests, SQLite en mémoire ; certains
tests live/vision se skip sans Postgres/données) et `npx tsc --noEmit` dans
`frontend/web` et `frontend/mobile`. Aucune de ces commandes n'a été exécutée dans le
cadre de cette analyse read-only.*

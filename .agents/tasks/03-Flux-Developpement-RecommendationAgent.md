# 📋 Flux de Développement - RecommendationAgent avec Validation

## 🎯 Vue d'ensemble

Votre agent de recommandation traverse **6 étapes** de développement avec validation à chaque niveau.

```
┌─────────────────────────────────────────────────────────────────┐
│         FLUX DE DÉVELOPPEMENT COMPLET                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ÉTAPE 1 : Input Validation                                    │
│    User Input → Context Enrichment                             │
│         ↓                                                        │
│  ÉTAPE 2 : Context Agent                                       │
│    Parse Occasion + Weather + Season                           │
│         ↓                                                        │
│  ÉTAPE 3 : Data Gathering                                      │
│    Fetch Wardrobe + Style + Usage History                      │
│         ↓                                                        │
│  ÉTAPE 4 : Recommendation Agent (CORE)                         │
│    Generate + Score + Filter + Explain                         │
│         ↓                                                        │
│  ÉTAPE 5 : Hard Constraints Filtering ← NOUVEAU ✨             │
│    Valider occasion appropriateness                            │
│         ↓                                                        │
│  ÉTAPE 6 : Output Validation + Storage                         │
│    Save to DB + Return to User                                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📍 ÉTAPE 1 : Input Validation

### Responsabilité
Valider que l'utilisateur a fourni des inputs cohérents

### Inputs
```python
{
    "user_id": UUID,           # ✓ Required, unique
    "occasion": str | None,    # Optional : "mariage", "travail", etc.
    "weather": str | None,     # Optional : "ensoleillé", "pluvieux"
    "season": str | None,      # Optional : "ete", "hiver", "mi_saison"
    "city": str | None,        # Optional : pour lookup météo
}
```

### Validations
- ✓ `user_id` exists dans DB (FK check)
- ✓ `occasion` ∈ OCCASION_CATEGORIES ou None
- ✓ `season` ∈ VALID_SEASONS ou None
- ✓ `city` length < 100 si present
- ✓ Si `weather` fourni, cohérent avec `season`

---

## 🌤️ ÉTAPE 2 : Context Agent

### Responsabilité
Enrichir le contexte avec données du monde réel

### Input
```python
{
    "occasion": "mariage",
    "weather": None,
    "season": None,
    "city": "Tunis"
}
```

### Processus
```
1. Parse occasion → occasion_category
   "mariage" → {
     "occasion_category": "mariage",
     "formality": 5,
     "dress_code": "tenue de cérémonie"
   }

2. Lookup city → weather + temperature
   "Tunis" → {
     "weather": "ensoleillé",
     "temperature": 28°C
   }

3. Derive season from temperature
   28°C → "ete"

4. Calculate weather_band
   28°C → "chaud"

5. Create context_vector
   (mariage, ete, chaud) → 512-d vector
```

---

## 👔 ÉTAPE 3 : Data Gathering

### Responsabilité
Récupérer toutes les données nécessaires pour les recommandations

### Sous-agents appelés

**A) StyleProfileAgent** : Retourne favourite_styles, colors, occasions_history
**B) MetadataAgent** : Retourne wardrobe items avec filtrage saisonnier
**C) UsageHistory** : Pour chaque item → last_worn, wear_count, days_since_worn
**D) ContextRetrieval (RAG)** : References historiques et catalogue

---

## 👗 ÉTAPE 4 : Recommendation Agent (CORE)

### Responsabilité
**Générer, scorer, et classer les tenues**

### Processus Principal

```
FOR EACH base (haut+bas OR robe):
    ├─ 1. Build outfit (add accessories greedily)
    ├─ 2. Calculate visual_coherence
    │   └─ mean pairwise compatibility scores
    ├─ 3. Calculate context_fit
    │   └─ cosine_sim(outfit_vec, ctx_vec)
    ├─ 4. Calculate season_compatibility
    │   └─ % items compatible with season
    ├─ 5. Calculate history_fit
    │   └─ max similarity with historical outfits
    ├─ 6. Calculate style_match
    │   └─ all items match favorite style ?
    ├─ 7. Calculate recent_wear_penalty
    │   └─ count items worn in last 3 days
    └─ 8. SCORE = ranking_model.score_outfit(...)

SORT by score DESC
```

---

## ✅ ÉTAPE 5 : Hard Constraints Filtering ← NOUVEAU ✨

### Responsabilité
**Filtrer les tenues inappropriées par occasion**

### Processus
```
FOR EACH outfit in candidates:
    ├─ Check formality range
    │   └─ formality ∈ [min, max] ?
    ├─ Check base type
    │   └─ robe vs haut+bas allowed ?
    ├─ Check forbidden categories
    │   └─ no forbidden items ?
    └─ Check allowed categories
        └─ all items in whitelist ?

IF all checks pass:
    KEEP outfit
ELSE:
    REJECT outfit
```

### Impact
- **Travail** : Rejette robe_soiree ❌ → Accepte haut+bas ✅
- **Sport** : Rejette talons ❌ → Accepte leggings_sport ✅
- **Plage** : Rejette jeans ❌ → Accepte maillot ✅

---

## 💾 ÉTAPE 6 : Output Validation + Storage

### Responsabilité
Valider et persister les recommandations

### Output
```python
{
    "context": {
        "occasion": "mariage",
        "weather": "ensoleillé",
        "season": "ete",
        "formality": 5,
    },
    "outfits": [
        {
            "id": UUID,
            "item_ids": [uuid1, uuid2, uuid3],
            "occasion": "mariage",
            "relevance_score": 0.87,
            "explanation": "...",
            "created_at": datetime
        },
        ...
    ],
    "metadata": {
        "total_candidates": 120,
        "after_constraints": 45,
        "returned_outfits": 5,
        "generation_time_ms": 234
    }
}
```

---

## 🔍 Checklist de Validation Complète

### Avant chaque PR

- [ ] **Étape 1** : Input valides
  - [ ] user_id exists
  - [ ] occasion ∈ OCCASIONS
  - [ ] season ∈ SEASONS

- [ ] **Étape 2** : Context enrichi
  - [ ] occasion_category défini
  - [ ] temperature calculée
  - [ ] ctx_vec shape (512,)

- [ ] **Étape 3** : Données complètes
  - [ ] wardrobe.items > 0
  - [ ] usage history complète
  - [ ] references format OK

- [ ] **Étape 4** : Scores valides
  - [ ] scores ∈ [0, 1] pour chaque tenue
  - [ ] sorted DESC
  - [ ] no duplicates

- [ ] **Étape 5** : Constraints respectées
  - [ ] formality range OK
  - [ ] base type OK
  - [ ] no forbidden items

- [ ] **Étape 6** : Persistance OK
  - [ ] DB transactions
  - [ ] Outfit IDs valides
  - [ ] Explanations < 2048 chars

---

## 📊 Flux Visuel Complet

```
USER REQUEST
    ↓
    ├─→ ÉTAPE 1: Input Validation
    │      ├─ user_id exists ?
    │      ├─ occasion valide ?
    │      └─ city format OK ?
    │           ↓ [VALID]
    │
    ├─→ ÉTAPE 2: Context Agent
    │      ├─ Parse occasion
    │      ├─ Lookup weather
    │      └─ Calculate context_vector
    │           ↓ [VALID]
    │
    ├─→ ÉTAPE 3: Data Gathering
    │      ├─ Fetch wardrobe
    │      ├─ Get style profile
    │      ├─ Get usage history
    │      └─ Retrieve references
    │           ↓ [VALID]
    │
    ├─→ ÉTAPE 4: Recommendation Agent (CORE)
    │      ├─ Generate candidates (120)
    │      ├─ Score each outfit
    │      └─ Sort by score
    │           ↓ [VALID]
    │
    ├─→ ÉTAPE 5: Hard Constraints Filter ✨
    │      ├─ Check formality
    │      ├─ Check base type
    │      ├─ Check forbidden items
    │      └─ Filter out invalid (120 → 45)
    │           ↓ [VALID]
    │
    ├─→ ÉTAPE 6: Output Validation + Storage
    │      ├─ Create Outfit objects
    │      ├─ Generate LLM explanations
    │      ├─ Insert to DB
    │      └─ Return top-5 to user
    │           ↓
    │
    USER RECEIVES
    │
    ├─ Context enrichi
    ├─ 5 tenues appropriées
    ├─ Explanations pertinentes
    └─ Scores transparents
```

---

## 📝 Notes Importantes

1. **Fail-Fast** : Valider tôt, rejeter rapidement
2. **Logging** : Logger chaque rejet pour debug
3. **Tests** : 100% coverage pour chaque étape
4. **Performance** : < 2 secondes end-to-end
5. **Idempotency** : Même input = même output

---

**Vous êtes prêt pour déployer avec confiance !** 🚀

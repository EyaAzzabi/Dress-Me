# 🤖 Modèles ML Utilisés par RecommendationAgent

## 📊 Vue d'ensemble

Le `RecommendationAgent` utilise **6 modèles ML** pour générer, scorer et valider les recommandations de tenues.

```
USER REQUEST
    ↓
    ├─→ 1️⃣ FashionCLIP (Vision Model)
    │       Generate item embeddings (512-d)
    │           ↓
    ├─→ 2️⃣ Category Classifier (SVM)
    │       Classify clothing category (~87% accuracy)
    │           ↓
    ├─→ 3️⃣ Compatibility Model (LogisticRegression)
    │       Score pairwise compatibility (AUC 0.67)
    │           ↓
    ├─→ 4️⃣ Ranking Model (LogisticRegression + Additive Layer)
    │       Final outfit scoring with context
    │           ↓
    ├─→ 5️⃣ Context Vectors (Pre-computed)
    │       96 FashionCLIP text vectors
    │           ↓
    └─→ 6️⃣ Clothing Gate (Classifier)
            Filter non-clothing images
            ↓
    RECOMMENDATIONS ✅
```

---

## 🔍 Modèle 1 : FashionCLIP (Vision Model)

### 📋 Description
- **Type** : Vision + Text encoder (contrastive learning)
- **Source** : Hugging Face - `patrickjohncyh/fashion-clip`
- **Dimension** : 512-d embeddings
- **Entrée** : Image RGB (vêtement)
- **Sortie** : Vecteur L2-normalisé (512,)

### 🎯 Utilisation dans RecommendationAgent
```python
# Dans vision_model.py
from app.ml.vision_model import embed_image_bytes

# Chaque vêtement obtient un embedding
item_embedding = embed_image_bytes(image_data)  # Shape: (512,)

# Stocké dans Pinecone pour recherche vectorielle
vector_store.save_embedding(item_id, item_embedding)
```

### 📊 Caractéristiques
- **Entraîné sur** : Données de mode large-scale
- **Advantage** : Comprend la mode mieux que CLIP standard
- **Permet** : Similarité image-texte cross-modal
- **Used for** :
  - Embeddings items du wardrobe
  - Comparaison items compatibilité
  - Lookup contextuel (occasion/season)

---

## 🏷️ Modèle 2 : Category Classifier (SVM)

### 📋 Description
  - **Type** : Support Vector Machine (SVM)
  - **File** : `artifacts/category_classifier.joblib`
  - **Input** : FashionCLIP embedding (512-d)
  - **Output** : Catégorie de vêtement (7 classes)
  - **Accuracy** : ~87% sur photos tunisiennes

### 🎯 Utilisation dans RecommendationAgent
```python
# Dans vision_model.py
from app.ml.garment_types import type_posterior

# Classifier le vêtement
embedding = embed_image_bytes(image)
probabilities = type_posterior(embedding)

# Output: 
# {
#     "haut": 0.92,
#     "bas": 0.05,
#     "robe": 0.02,
#     ...
# }

category = max(probabilities, key=probabilities.get)  # "haut"
```

### 🏷️ Classes
```python
CATEGORIES = [
    "haut",           # Top, chemise, etc.
    "bas",            # Pantalon, jupe, etc.
    "robe",           # Dress
    "veste",          # Jacket, blazer
    "chaussures",     # Shoes
    "sac",            # Bag
    "accessoire"      # Accessories
]
```

### 📊 Performance
- **Accuracy** : 87% on Tunisian wardrobe photos
- **Training data** : 2,000+ labeled photos
- **Evaluation** : `ml/reports/vision_agent_evaluation.md`

---

## 🤝 Modèle 3 : Compatibility Model (LogisticRegression)

### 📋 Description
- **Type** : Logistic Regression (trained on Polyvore)
- **File** : `artifacts/compatibility_model.joblib`
- **Input** : 2 FashionCLIP embeddings (512-d each)
- **Output** : Probability ∈ [0, 1] (compatible ?)
- **Training data** : 68,306 real outfits from Polyvore
- **Metric** : AUC 0.674 vs 0.609 (raw cosine)

### 🎯 Utilisation dans RecommendationAgent
```python
# Dans recommendation_agent.py
from app.ml.compatibility_model import pair_compatibility

# Score pairwise compatibility
score = pair_compatibility(
    vec_item1,      # 512-d
    vec_item2,      # 512-d
    item_a=item1,   # ClothingItem
    item_b=item2,   # ClothingItem
    season="ete",
    occasion="soiree"
)
# Output: 0.85 (85% compatible)
```

### 🧮 Features
```python
# Input to model
feature = (vec_a * vec_b).reshape(1, -1)  # Element-wise product

# Model training (in ml/notebooks/09)
model = LogisticRegression(max_iter=2000)
model.fit(X_train, y_train)  # y = 1 (worn together) or 0 (random pair)
```

### 🎁 Contextual Boosts
```python
# Enhanced compatibility with context

1. Season Boost (+15% / +5% / -5%)
   ├─ Both items match season → +15%
   ├─ One matches → +5%
   └─ None match → -5%

2. Color Harmony (+10% / +5% / -15%)
   ├─ Shared colors → +10%
   ├─ Neutral colors (noir/blanc/gris) → +5%
   └─ Clashing colors (red + pink) → -15%

3. Style Coherence (+12% / +6% / -12%)
   ├─ Matching styles → +12%
   ├─ Compatible styles → +6%
   └─ Incompatible styles → -12%

4. Pattern Clash (-20% / +2% / -8%)
   ├─ Bold patterns clash → -20%
   ├─ One solid + one pattern → +2%
   └─ Two different patterns → -8%
```

### 📊 Performance
- **AUC** : 0.674 (vs 0.609 raw cosine)
- **Accuracy** : 62.3% (vs 58.3% raw)
- **Training** : 68,306 Polyvore outfits
- **Evaluation** : `ml/notebooks/09_compatibility_model.py`

---

## 🎯 Modèle 4 : Ranking Model (Learned + Additive Layer)

### 📋 Description
- **Type** : LogisticRegression + Deterministic Additive Layer
- **File** : `artifacts/ranking_model.joblib`
- **Input** : 2 learned features + 4 deterministic signals
- **Output** : Final score ∈ [0, 1]

### 🎯 Utilisation dans RecommendationAgent
```python
# Dans recommendation_agent.py
from app.ml import ranking_model

score = ranking_model.score_outfit(
    visual=0.85,              # Visual coherence
    context_fit=0.92,         # Occasion/season/weather fit
    history_fit=0.78,         # Similar to past worn outfits
    season_compat=1.0,        # % items in season
    style_match=True,         # All items favorite style?
    recent=1,                 # Count of recently worn items
    ranking_enabled=True
)
# Output: 0.87 (87% ranking score)
```

### 🧮 Formula
```python
# Learned part (LogisticRegression on 2 features)
learned = model.predict_proba([[visual, context_fit]])[0, 1]

# Additive layer (deterministic)
base = (
    learned
    + SEASON_COMPAT_BONUS * season_compat      # +0.1 max
    + (STYLE_MATCH_BONUS if style_match else 0)  # +0.1 max
    + HISTORY_FIT_WEIGHT * history_fit         # +0.1 max
)

# Apply penalty + clamp
final_score = max(0.0, min(1.0, base - RECENT_WEAR_PENALTY * recent))
```

### ⚖️ Weights
```python
STYLE_MATCH_BONUS = 0.1        # Favorite style bonus
RECENT_WEAR_PENALTY = 0.05     # Per recently worn item
SEASON_COMPAT_BONUS = 0.1      # Season compatibility
HISTORY_FIT_WEIGHT = 0.1       # Historical outfit similarity
```

---

## 📐 Modèle 5 : Context Vectors (Pre-computed)

### 📋 Description
- **Type** : Pre-computed FashionCLIP text embeddings
- **File** : `artifacts/context_vectors.npz`
- **Dimension** : 96 vectors × 512-d each
- **Format** : NPZ (NumPy compressed archive)

### 🎯 Utilisation dans RecommendationAgent
```python
# Dans ranking_model.py
ctx_vec = context_vector(
    occasion_category="mariage",
    season="ete",
    weather_band="chaud"
)
# Output: (512,) normalized vector

# Puis utilisé pour context_fit
context_fit = float(mean_outfit_vec @ ctx_vec)  # Dot product
```

### 📦 Contenu
```python
# 96 vecteurs pré-calculés :

# 72 spécifiques : occasion × season × weather_band
#   8 occasions × 3 seasons × 3 bands = 72

occasions = [
    "mariage", "soiree", "travail", "casual_quotidien",
    "sport", "plage", "voyage", "ceremonie"
]

seasons = ["ete", "hiver", "mi_saison"]
bands = ["froid", "modere", "chaud"]

# Key format: "mariage|ete|chaud"

# 24 agnostiques météo : occasion × season × _any
#   8 occasions × 3 seasons = 24
# Key format: "mariage|ete|_any"
```

---

## 🚪 Modèle 6 : Clothing Gate (Classifier)

### 📋 Description
- **Type** : Lightweight classifier
- **Purpose** : Filter non-clothing images
- **Input** : FashionCLIP embedding (512-d)
- **Output** : Probability of being clothing

### 🎯 Utilisation dans RecommendationAgent
```python
# Dans clothing_gate.py
from app.ml.clothing_gate import is_clothing

# Vérifier si image est un vêtement
if not is_clothing(embedding):
    raise ValueError("Image does not contain clothing")
```

### 🧮 Implementation
```python
# Deux classes : "clothing" vs "non-clothing"

def _text_vectors() -> np.ndarray:
    """Generate text embeddings for classification"""
    clothing_text = "clothing, garment, dress, shirt, pants"
    non_clothing_text = "furniture, landscape, face, food, animal"
    
    clothing_vec = clip.encode_text(clothing_text)
    non_clothing_vec = clip.encode_text(non_clothing_text)
    
    return np.stack([clothing_vec, non_clothing_vec])

def is_clothing(embedding: np.ndarray) -> bool:
    text_vecs = _text_vectors()
    probs = embedding @ text_vecs.T  # Dot product with class vectors
    return np.argmax(probs) == 0  # Class 0 = clothing
```

---

## 📊 Résumé : Modèles ML

| # | Modèle | Type | Input | Output | Usage |
|---|--------|------|-------|--------|-------|
| 1 | FashionCLIP | Vision+Text | Image | 512-d | Embeddings |
| 2 | Category Classifier | SVM | 512-d | 7 categories | Classification |
| 3 | Compatibility | LogReg | 2×512-d | [0,1] | Pairwise scoring |
| 4 | Ranking | LogReg+Additive | 6 features | [0,1] | Final score |
| 5 | Context Vectors | Pre-computed | 96×512-d | 512-d lookup | Context matching |
| 6 | Clothing Gate | Classifier | 512-d | [0,1] | Image validation |

---

## 🎓 Architecture du Scoring

```
OUTFIT (3 items: haut, bas, shoes)
  ↓
  ├─→ Extract embeddings (FashionCLIP)
  │    e1, e2, e3 → 512-d each
  │       ↓
  │
  ├─→ Pairwise compatibility
  │    compat(e1,e2), compat(e1,e3), compat(e2,e3)
  │    → Contextual boosts (season, color, style, pattern)
  │       ↓
  │
  ├─→ Visual coherence
  │    visual_score = mean([compat(e1,e2), compat(e1,e3), compat(e2,e3)])
  │       ↓
  │
  ├─→ Context fit
  │    mean_vec = mean([e1, e2, e3])
  │    context_fit = mean_vec @ ctx_vec
  │       ↓
  │
  ├─→ Features for Ranking Model
  │    ├─ visual_coherence (learned)
  │    ├─ context_fit (learned)
  │    ├─ season_compat (deterministic)
  │    ├─ style_match (deterministic)
  │    ├─ history_fit (deterministic)
  │    └─ recent (deterministic)
  │       ↓
  │
  └─→ Final Score = LogReg(visual, context_fit) + Additive layer
       score ∈ [0, 1]
```

---

## 🚀 Performance

| Modèle | Latency | Accuracy/AUC | GPU Required |
|--------|---------|--------------|--------------|
| FashionCLIP | 100-200ms | N/A | Yes (1st time) |
| Category | 5-10ms | 87% | No (inference) |
| Compatibility | 1-2ms | AUC 0.674 | No |
| Ranking | <1ms | N/A | No |
| Context Vectors | <1ms | N/A | No (pre-computed) |
| Clothing Gate | 1-2ms | ~95% | No |

**Total latency per outfit** : ~15-50ms (depends on compatibility scoring)

---

## 📚 Fichiers de Référence

- Vision Model : `app/ml/vision_model.py`
- Compatibility : `app/ml/compatibility_model.py`
- Ranking : `app/ml/ranking_model.py`
- Clothing Gate : `app/ml/clothing_gate.py`
- Garment Types : `app/ml/garment_types.py`
- Notebooks : `ml/notebooks/{08,09,10}_*.py`

---

**Ces 6 modèles travaillent ensemble pour générer les meilleures recommandations !** 🎯

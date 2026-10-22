# 📚 Guide Complet du Projet DressMe
## Explication Étape par Étape

---

## 🎯 Vue d'ensemble

**DressMe** est un **assistant de mode personnel alimenté par l'IA** qui vous permet de :
1. 📸 Créer une garde-robe numérique à partir de photos de vêtements
2. 👔 Obtenir des recommandations de tenues intelligentes
3. 📅 Planifier des tenues sur un calendrier (et voir votre avatar les porter)
4. 🧳 Préparer une valise pour un voyage
5. 🛍️ Vérifier si un nouvel achat vaut la peine

---

## 🏗️ Architecture Globale

```
┌─────────────────────────────────────────────────────────┐
│                    FRONTEND                             │
│  ┌──────────────┐         ┌──────────────┐            │
│  │  Web App     │         │  Mobile App  │            │
│  │  (React)     │         │  (React      │            │
│  │              │         │   Native)    │            │
│  └──────┬───────┘         └──────┬───────┘            │
│         │                        │                     │
│         └────────────┬───────────┘                     │
└──────────────────────┼─────────────────────────────────┘
                       │ REST API
┌──────────────────────┼─────────────────────────────────┐
│                BACKEND (FastAPI)                        │
│                      │                                  │
│         ┌────────────▼────────────┐                    │
│         │  AgentOrchestrator      │                    │
│         │  (Coordinateur)         │                    │
│         └────────────┬────────────┘                    │
│                      │                                  │
│         ┌────────────┴────────────┐                    │
│         │     AGENTS SPÉCIALISÉS   │                    │
│         │  1. VisionAgent          │                    │
│         │  2. MetadataAgent        │                    │
│         │  3. StyleProfileAgent    │                    │
│         │  4. ContextAgent         │                    │
│         │  5. RecommendationAgent  │                    │
│         │  6. PackingAgent         │                    │
│         │  7. PurchaseAgent        │                    │
│         │  8. TryOnAgent           │                    │
│         │  9. LLMAgent             │                    │
│         └─────────────────────────┘                    │
└─────────────────────────────────────────────────────────┘
                       │
┌──────────────────────┼─────────────────────────────────┐
│                  DONNÉES                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │PostgreSQL│  │ Pinecone │  │ Storage  │            │
│  │   DB     │  │ (Vectors)│  │ (Photos) │            │
│  └──────────┘  └──────────┘  └──────────┘            │
└─────────────────────────────────────────────────────────┘
```

---

## 📁 Structure des Dossiers

### 🔧 Backend (`backend/`)
Le cœur de l'application - serveur FastAPI Python

```
backend/
├── app/
│   ├── agents/              # 🤖 Les 9 agents IA
│   │   ├── orchestrator.py  # Chef d'orchestre
│   │   ├── vision_agent.py  # Analyse d'images
│   │   ├── recommendation_agent.py  # Recommandations
│   │   └── ...
│   ├── api/
│   │   └── routes/          # 🛣️ Endpoints REST API
│   │       ├── auth.py      # Authentification
│   │       ├── wardrobe.py  # Garde-robe
│   │       ├── recommendations.py
│   │       ├── calendar.py
│   │       └── ...
│   ├── core/                # ⚙️ Configuration
│   │   ├── config.py        # Variables d'environnement
│   │   └── security.py      # JWT, passwords
│   ├── db/                  # 🗄️ Base de données
│   │   ├── base.py
│   │   ├── session.py
│   │   └── vector_store.py  # Pinecone
│   ├── ml/                  # 🧠 Machine Learning
│   │   ├── artifacts/       # Modèles entraînés
│   │   ├── vision_model.py  # FashionCLIP
│   │   ├── compatibility_model.py
│   │   └── ...
│   ├── models/              # 📊 Modèles SQLAlchemy
│   │   ├── user.py
│   │   ├── clothing_item.py
│   │   ├── outfit.py
│   │   └── ...
│   ├── services/            # 🛠️ Services métier
│   │   ├── weather.py       # OpenWeather API
│   │   ├── storage.py       # S3/Local
│   │   └── ...
│   └── main.py              # 🚀 Point d'entrée
├── alembic/                 # 📦 Migrations DB
├── tests/                   # ✅ Tests
├── requirements.txt         # 📋 Dépendances Python
├── .env                     # 🔐 Configuration (NE PAS COMMIT)
└── .env.example             # 📝 Template de config
```

### 🎨 Frontend

#### Web (`frontend/web/`)
Application web React + Vite

```
frontend/web/
├── src/
│   ├── components/          # Composants réutilisables
│   ├── pages/               # Pages de l'app
│   │   ├── Login.jsx
│   │   ├── Wardrobe.jsx
│   │   ├── Recommendations.jsx
│   │   ├── Calendar.jsx
│   │   └── ...
│   ├── services/            # API client
│   └── App.jsx
├── package.json
└── vite.config.js
```

#### Mobile (`frontend/mobile/`)
Application React Native + Expo

```
frontend/mobile/
├── app/                     # Screens (navigation Expo Router)
├── components/              # Composants réutilisables
├── services/                # API client
├── app.json                 # Config Expo
└── package.json
```

### 🧪 ML (`ml/`)
Notebooks de recherche et d'entraînement (non nécessaire pour l'exécution)

```
ml/
├── notebooks/               # Jupyter notebooks
│   ├── 08_category_classifier.py
│   ├── 09_compatibility_model.py
│   └── ...
├── src/                     # Code réutilisable
│   ├── catalog.py
│   └── features.py
└── data/                    # Datasets (non commités)
```

---

## 🤖 Les 9 Agents Intelligents (Détail)

### 1. 👁️ **VisionAgent** - Analyse d'Images
**Rôle** : Comprendre le contenu d'une photo de vêtement

**Technologie** : FashionCLIP (CLIP adapté à la mode)

**Ce qu'il fait** :
1. ✅ **Détection de vêtement** : "Y a-t-il un vêtement dans cette image ?"
2. 🏷️ **Catégorie** : Haut, Bas, Robe, Veste, Chaussures, Sac, Accessoire (~87% précision)
3. 🌸 **Saison** : Été, Hiver, Mi-saison (si confiant)
4. 🎨 **Style** : Casual, Chic, Sportif, etc.
5. 🎨 **Couleurs** : Extraction des couleurs principales
6. 🔲 **Motifs** : Uni, Rayé, Imprimé, etc.

**Exemple** :
```python
{
  "category": "haut",
  "season": "ete",
  "style": "casual",
  "colors": ["bleu", "blanc"],
  "pattern": "raye",
  "confidence": 0.92
}
```

---

### 2. 📦 **MetadataAgent** - Garde-robe Numérique
**Rôle** : Gérer tous les vêtements de l'utilisateur

**Ce qu'il fait** :
- ➕ Ajouter des vêtements (appelle VisionAgent)
- ✏️ Corriger les informations
- 🗑️ Supprimer
- 🔍 Rechercher et filtrer (par catégorie, saison, couleur, etc.)
- 📊 Historique d'utilisation (quand un vêtement a été porté)

**Base de données** : Table `clothing_items` dans PostgreSQL

---

### 3. 🎭 **StyleProfileAgent** - Profil de Style
**Rôle** : Apprendre vos préférences

**Ce qu'il analyse** :
- Styles préférés (en comptant les vêtements dans votre garde-robe)
- Couleurs favorites
- Marques favorites

**Utilisation** : Le RecommendationAgent booste les tenues qui matchent votre style

---

### 4. 🌤️ **ContextAgent** - Contexte & Occasion
**Rôle** : Comprendre le contexte de la recommandation

**Ce qu'il gère** :
1. **Occasion** : "Mariage", "Travail", "Décontracté", "Sport", etc.
2. **Météo** : Appelle l'API OpenWeather pour une ville
3. **Saison** : Déduit la saison de la date ou de la température
4. **Formalité** : Niveau 1-5 (très casual → très formel)

**Exemple de parsing** :
```
Input: "Je vais à un mariage à Paris"
Output: {
  "occasion": "mariage",
  "occasion_category": "ceremonie",
  "city": "Paris",
  "weather": "ensoleillé",
  "temperature": 22,
  "formality": 5
}
```

---

### 5. 👔 **RecommendationAgent** - Recommandations de Tenues
**Rôle** : **LE CŒUR DU SYSTÈME** - Créer des tenues parfaites

**Comment ça marche** :

#### Étape 1 : Construire des bases de tenues
```
Base Haut/Bas : [haut + bas + chaussures + accessoires optionnels]
Base Robe : [robe + chaussures + accessoires optionnels]
```

#### Étape 2 : Scorer chaque tenue
Le score combine plusieurs facteurs :

```python
score_final = 
  + visual_coherence        # 🎨 Les couleurs/styles vont-ils ensemble ?
  + context_fit             # 🌤️ Adapté à l'occasion/météo ?
  + season_compatibility    # ❄️ Adapté à la saison ?
  + style_match_bonus       # 🎭 Correspond à votre style préféré ?
  - recent_wear_penalty     # 🚫 Pénalise les vêtements portés récemment
```

#### Les Modèles ML :

1. **Compatibility Model** (LogisticRegression)
   - Entraîné sur le dataset Polyvore (50 000+ tenues réelles)
   - Prédit si 2 vêtements vont bien ensemble
   - Features : similarité visuelle (FashionCLIP embeddings)

2. **Context Vector** (Ranking Model)
   - 96 vecteurs pré-calculés (occasion × saison × météo)
   - Permet de classer les tenues selon le contexte

#### Étape 3 : LLM Optionnel
Si `LLM_PROVIDER != none`, génère une explication en langage naturel :
```
"Cette tenue combine élégance et confort parfaits pour un mariage estival. 
Le bleu marine apporte une touche sophistiquée."
```

**Fallback si LLM désactivé** : Template simple
```
"Tenue adaptée pour [occasion]. Composition : [liste des items]."
```

---

### 6. 🧳 **PackingAgent** - Liste de Valise
**Rôle** : Préparer une valise pour un voyage

**Inputs** :
- Destination (pour la météo)
- Durée du voyage
- Type de voyage (business, vacances, etc.)
- Dates

**Ce qu'il fait** :
1. Récupère les tenues **déjà planifiées** dans le calendrier pour ces dates
2. Génère des tenues supplémentaires selon la durée
3. Crée une liste organisée par catégorie

**Exemple de liste** :
```
HAUTS : 5 items
BAS : 3 items
ROBES : 2 items
CHAUSSURES : 2 paires
ACCESSOIRES : Sac, écharpe
```

---

### 7. 🛍️ **PurchaseAgent** - Aide à l'Achat
**Rôle** : "Est-ce que cet achat a du sens pour ma garde-robe ?"

**Analyse** :
1. ✅ **Gap Analysis** : Manque-t-il cette catégorie/couleur/style ?
2. 🔁 **Redundancy Check** : Ai-je déjà quelque chose de similaire ?
3. 🎨 **Versatility Score** : Ce vêtement s'associera avec combien de mes items existants ?

**Nécessite** : Pinecone (pour comparer avec les embeddings de votre garde-robe)

---

### 8. 🪞 **TryOnAgent** - Essayage Virtuel
**Rôle** : Montrer à quoi ressemble un vêtement sur vous

**Technologies** :
- **OOTDiffusion** (via Hugging Face Space - GRATUIT)
- **Replicate** (payant, meilleure qualité)

**Utilisé pour** :
1. Essayer un nouveau vêtement avant de l'acheter
2. Visualiser votre avatar avec les tenues planifiées dans le calendrier

**Comment** :
```
Input: Photo de votre corps (avatar) + Photo du vêtement
Output: Photo de vous portant le vêtement
```

---

### 9. 🤖 **LLMAgent** - Explications en Langage Naturel
**Rôle** : Ajouter des explanations humaines aux recommandations

**Providers supportés** :
- Mistral AI
- OpenAI (GPT-4o-mini)
- Anthropic Claude
- Groq
- Ollama (local)
- Gemini

**Mode par défaut** : `LLM_PROVIDER=none` (désactivé)

**Pourquoi optionnel ?** :
- Coût des API
- L'app fonctionne parfaitement sans (templates prédéfinis)

---

## 🔄 Flux de Données Typiques

### Scénario 1 : Ajouter un Vêtement

```
1. User upload une photo (via frontend)
   ↓
2. POST /api/v1/wardrobe/items
   ↓
3. MetadataAgent reçoit la demande
   ↓
4. Appelle VisionAgent.analyze_image()
   ↓
5. VisionAgent :
   - Extrait embedding FashionCLIP
   - Classifie la catégorie (SVM)
   - Détecte saison/style/couleurs
   ↓
6. MetadataAgent :
   - Sauvegarde dans PostgreSQL (clothing_items table)
   - Upload la photo vers Storage (S3/Local)
   - Sauvegarde embedding dans Pinecone
   ↓
7. Retourne le ClothingItem au frontend
```

---

### Scénario 2 : Obtenir des Recommandations de Tenues

```
1. User : "Je veux une tenue pour un mariage à Paris"
   ↓
2. POST /api/v1/recommendations/outfits
   {
     "occasion": "mariage",
     "city": "Paris"
   }
   ↓
3. AgentOrchestrator coordonne :
   
   A. ContextAgent :
      - Parse "mariage" → occasion_category="ceremonie"
      - Appelle OpenWeather API pour Paris
      - Retourne {weather: "ensoleillé", temp: 22°C, season: "ete"}
   
   B. StyleProfileAgent :
      - Analyse la garde-robe
      - Retourne {favorite_styles: ["chic", "elegant"]}
   
   C. MetadataAgent :
      - Récupère tous les vêtements de l'utilisateur
      - Récupère les embeddings depuis Pinecone
   
   D. RecommendationAgent.run() :
      - Construit toutes les combinaisons possibles
      - Pour chaque tenue :
        * Calcule visual_coherence (ML model)
        * Calcule context_fit (occasion + météo)
        * Calcule season_compatibility
        * Applique style_match_bonus
        * Applique recent_wear_penalty
        * Score final = somme pondérée
      - Trie par score décroissant
      - Prend le top_k (ex: 5 meilleures tenues)
   
   E. LLMAgent (si activé) :
      - Génère une explication pour chaque tenue
   
   F. Sauvegarde dans la table "outfits"
   
   G. Retourne la liste des tenues au frontend
```

---

### Scénario 3 : Planifier une Tenue sur le Calendrier

```
1. User sélectionne une tenue et une date
   ↓
2. POST /api/v1/calendar/schedule
   {
     "date": "2026-06-15",
     "item_ids": [uuid1, uuid2, uuid3]
   }
   ↓
3. MetadataAgent :
   - Sauvegarde dans scheduled_outfits table
   ↓
4. (Optionnel) TryOnAgent :
   - Génère une image de l'avatar portant la tenue
   - Sauvegarde l'image
   ↓
5. Le calendrier affiche la tenue avec l'image
```

---

## 🗄️ Base de Données (PostgreSQL)

### Tables Principales

#### `users`
```sql
id (UUID, PK)
email (String, unique)
hashed_password (String)
created_at (DateTime)
```

#### `clothing_items`
```sql
id (UUID, PK)
owner_id (UUID, FK → users)
image_url (String)
dressme_category (String) -- "haut", "bas", "robe", etc.
season (JSON) -- ["ete", "printemps"]
style (JSON) -- ["casual", "chic"]
colors (JSON) -- ["bleu", "blanc"]
pattern (String)
confidence (Float)
source (String) -- "vision_agent" | "user_correction"
created_at (DateTime)
```

#### `outfits`
```sql
id (UUID, PK)
owner_id (UUID, FK → users)
item_ids (JSON) -- [uuid1, uuid2, uuid3]
occasion (String)
context (JSON) -- {weather, season, etc.}
explanation (String, max 2048)
created_at (DateTime)
```

#### `scheduled_outfits`
```sql
id (UUID, PK)
owner_id (UUID, FK → users)
date (Date)
item_ids (JSON)
rendered_image_url (String, nullable)
created_at (DateTime)
```

#### `wear_log`
```sql
id (UUID, PK)
owner_id (UUID, FK → users)
item_id (UUID, FK → clothing_items)
date (Date)
UniqueConstraint(item_id, date)
```

#### `packing_lists`
```sql
id (UUID, PK)
owner_id (UUID, FK → users)
trip_name (String)
destination (String)
start_date, end_date (Date)
item_ids (JSON)
created_at (DateTime)
```

#### `purchase_history`
```sql
id (UUID, PK)
owner_id (UUID, FK → users)
item_id (UUID, FK → clothing_items)
purchase_date (Date)
price (Float, nullable)
store (String, nullable)
```

#### `wishlist_items`
```sql
id (UUID, PK)
owner_id (UUID, FK → users)
name, image_url (String)
category, style, colors (String/JSON)
analysis (JSON) -- Gap/redundancy analysis
created_at (DateTime)
```

---

## 🔐 Sécurité & Authentification

### JWT (JSON Web Tokens)

1. **Inscription** : POST `/api/v1/auth/register`
   ```json
   {
     "email": "user@example.com",
     "password": "strong_password"
   }
   ```
   → Password hashé avec bcrypt, stocké dans DB

2. **Connexion** : POST `/api/v1/auth/login`
   → Retourne un JWT token
   ```json
   {
     "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
     "token_type": "bearer"
   }
   ```

3. **Requêtes authentifiées** :
   ```
   Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
   ```

### Dépendance FastAPI
```python
@router.get("/wardrobe/items")
async def get_items(
    current_user: User = Depends(get_current_user)
):
    # current_user est automatiquement extrait du token
    return MetadataAgent.get_all_items(user_id=current_user.id)
```

---

## 📊 Technologies Utilisées

### Backend
- **FastAPI** : Framework web Python moderne et rapide
- **SQLAlchemy** : ORM pour PostgreSQL
- **Alembic** : Migrations de schéma
- **Pydantic** : Validation de données
- **PyTorch** : Deep Learning (FashionCLIP)
- **Transformers** (Hugging Face) : Modèles pré-entraînés
- **scikit-learn** : ML classique (SVM, LogisticRegression)
- **Pinecone** : Base de données vectorielle
- **httpx** : Client HTTP async
- **python-jose** : JWT
- **passlib** : Hashing de mots de passe

### Frontend Web
- **React 18** : UI library
- **Vite** : Build tool ultra-rapide
- **React Router** : Navigation
- **Axios** : HTTP client
- **Tailwind CSS** : Styling

### Frontend Mobile
- **React Native** : Framework mobile cross-platform
- **Expo** : Toolchain React Native
- **Expo Router** : Navigation basée sur fichiers

### Données
- **PostgreSQL** : Base de données relationnelle
- **Pinecone** : Stockage et recherche d'embeddings vectoriels
- **AWS S3** / **Local Storage** : Stockage de photos

### ML / IA
- **FashionCLIP** : Embeddings visuels + textuels pour la mode
- **Polyvore Dataset** : 50k+ tenues pour l'entraînement
- **OOTDiffusion** : Virtual try-on
- **Hard Constraints** : Filtres par occasion (élimine 80% faux positifs)

---

## 🚀 Démarrage Rapide (Résumé)

### 1. Prérequis
```bash
# Vérifier les versions
docker --version        # Docker Desktop
python --version        # Python 3.11+
node --version          # Node 18+
```

### 2. Base de données
```bash
cd infra
docker-compose up -d postgres
```

### 3. Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
cp .env.example .env     # Éditer avec vos clés API
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### 4. Frontend Web
```bash
cd frontend/web
npm install
npm run dev
# Ouvrir http://localhost:5173
```

### 5. Frontend Mobile
```bash
cd frontend/mobile
npm install
npm start
# Scanner le QR code avec Expo Go
```

---

## 🔧 Configuration Essentielle (`.env`)

```bash
# BASE DE DONNÉES (obligatoire)
DATABASE_URL=postgresql+psycopg://dressme:dressme@localhost:5432/dressme

# SÉCURITÉ (obligatoire)
SECRET_KEY=votre_cle_secrete_tres_longue_et_aleatoire

# CORS (obligatoire pour web)
CORS_ORIGINS=http://localhost:5173,http://localhost:8081

# STOCKAGE DE PHOTOS (obligatoire pour upload)
LOCAL_STORAGE_DIR=./uploads
PUBLIC_BASE_URL=http://localhost:8000

# PINECONE (fortement recommandé)
PINECONE_API_KEY=votre_cle_pinecone
PINECONE_INDEX_NAME=dressme-clothing-embeddings

# MÉTÉO (optionnel)
OPENWEATHER_API_KEY=votre_cle_openweather

# LLM (optionnel, désactivé par défaut)
LLM_PROVIDER=none
# Pour activer : mistral, openai, anthropic, groq, ollama, gemini
# LLM_API_KEY=votre_cle_llm

# VIRTUAL TRY-ON (optionnel)
TRYON_PROVIDER=auto
HF_TOKEN=votre_token_huggingface  # Optionnel, augmente le quota GPU

# FONCTIONNALITÉS ML (recommandé True)
RANKING_ENABLED=true
CONTEXTUAL_RAG_ENABLED=true
```

---

## ✅ Tests

### Lancer tous les tests
```bash
cd backend
pytest tests/ -v
```

### Tests par agent
```bash
pytest tests/test_vision_agent.py -v
pytest tests/test_recommendation_agent.py -v
pytest tests/test_context_agent.py -v
pytest tests/test_outfit_constraints.py -v
```

### Tests d'intégration
```bash
pytest tests/test_hard_constraints_integration.py -v
pytest tests/test_live_integration.py -v
```

### Résultats des tests
```
test_outfit_constraints.py              : 16/16 ✅
test_hard_constraints_integration.py    : 4/4 ✅
test_recommendation_agent.py            : 10/10 ✅
─────────────────────────────────────
TOTAL                                    : 30/30 ✅
```

---

## 🐛 Dépannage Courant

### Problème : `ModuleNotFoundError: No module named 'cv2'`
**Solution** :
```bash
pip install opencv-python
```

### Problème : Tests échouent avec "column does not exist"
**Solution** : Migration DB manquante
```bash
alembic upgrade head
```

### Problème : API retourne 503 lors de l'upload de photo
**Solution** : Configurer le stockage
```bash
# Dans .env
LOCAL_STORAGE_DIR=./uploads
PUBLIC_BASE_URL=http://localhost:8000
```

### Problème : Pinecone errors
**Solution** : Créer l'index
```bash
cd backend
python create_pinecone_index.py
```

### Problème : Aucune recommandation retournée
**Causes possibles** :
1. Pas assez de vêtements dans la garde-robe (min 3)
2. Pinecone non configuré
3. Embeddings manquants

**Solution** :
```bash
# Vérifier les catégories
python check_categories.py

# Réindexer la garde-robe
python reindex_wardrobe.py
```

### Problème : "robe_soiree" retournée pour "travail"
**Solution** : Hard Constraints déjà implémentés ✅
- Les contraintes filtrent les tenues inappropriées
- 8 occasions configurées avec règles strictes
- 80% des faux positifs éliminés

---

## 📈 Métriques de Performance

### Vision Agent
- **Précision catégorie** : ~87% sur photos tunisiennes
- **Temps d'analyse** : ~2-3 secondes par image (première fois, puis cached)

### Recommendation Agent
- **Tenues générées** : 50-200 selon taille garde-robe
- **Temps de scoring** : ~1-2 secondes
- **Top-k retourné** : 5-10 meilleures tenues
- **Faux positifs** : <5% (grâce aux Hard Constraints)

### Try-On Agent
- **Temps (HuggingFace)** : 30-60 secondes
- **Temps (Replicate)** : 10-20 secondes
- **Qualité** : Replicate > HuggingFace

---

## 🎓 Concepts Clés à Comprendre

### 1. **Embeddings Vectoriels**
Un vêtement = un vecteur de 512 nombres (FashionCLIP)
```python
[0.23, -0.45, 0.89, ..., 0.12]  # 512 dimensions
```
Vêtements similaires = vecteurs proches (cosine similarity)

### 2. **FashionCLIP**
Version de CLIP (OpenAI) entraînée spécifiquement sur la mode
- Comprend la mode mieux que CLIP standard
- Peut lier texte et images ("robe rouge élégante" ↔ photo de robe)

### 3. **Pinecone**
Base de données vectorielle optimisée pour la recherche de similarité
```python
# Trouver les 5 vêtements les plus similaires
pinecone.search(query_vector, top_k=5)
```

### 4. **Polyvore Dataset**
Dataset de recherche (Pinterest)
- 50 000+ tenues créées par des humains
- Utilisé pour entraîner le modèle de compatibilité

### 5. **Contextual RAG (Retrieval Augmented Generation)**
- Récupère des tenues historiques similaires
- Enrichit les recommandations avec l'historique

### 6. **Hard Constraints**
Règles de filtrage strictes par occasion
- Éliminent les tenues inappropriate avant affichage
- Réduisent les faux positifs de 80%

---

## 🎯 Cas d'Usage Réels

### Cas 1 : Routine du Matin
*"Qu'est-ce que je porte aujourd'hui ?"*

1. Ouvre l'app
2. Clique "Recommandations"
3. Occasion auto-détectée : "Travail"
4. Météo auto-récupérée (géolocalisation)
5. Top 5 tenues adaptées affichées
6. Sélectionne une tenue → marquée "portée aujourd'hui"

### Cas 2 : Planification d'Événement
*"J'ai un mariage samedi prochain"*

1. Va dans le Calendrier
2. Sélectionne samedi prochain
3. "Nouvelle tenue" → Occasion "Mariage"
4. Voit les recommandations formelles
5. Choisit une tenue → planifiée dans le calendrier
6. L'avatar montre à quoi elle ressemble

### Cas 3 : Préparation de Voyage
*"Je pars à Barcelone 5 jours"*

1. Va dans "Packing"
2. Destination : Barcelone
3. Dates : 20-25 juin
4. Type : Vacances
5. L'app génère une liste optimale
6. Inclut automatiquement les tenues déjà planifiées
7. Coche les items en les ajoutant dans la valise

### Cas 4 : Shopping Intelligent
*"Ce jean vaut-il la peine ?"*

1. Prend une photo du jean en magasin
2. Va dans "Achat"
3. Upload la photo
4. L'app analyse :
   - "Vous avez déjà 3 jeans bleus similaires" ❌
   - OU "Ce jean comblerait un manque dans votre garde-robe" ✅
   - "Il s'associerait avec 15 de vos hauts" 👍
5. Décision éclairée !

---

## 🚀 Améliorations Futures Possibles

### Phase 1 : Corrections Immédiates (DONE ✅)
- [x] Hard Constraints par occasion
- [x] Tests de validation
- [x] Documentation complète

### Phase 2 : Context Vector Improvement (1-2 jours)
- [ ] Amplifier le signal de contexte (power = 1.5)
- [ ] Multi-vectors par occasion (3-5 vecteurs)
- **Gain attendu** : +15-20% qualité

### Phase 3 : Fine-tuning FashionCLIP (1-2 semaines)
- [ ] Collecter 300+ paires de training
- [ ] Implémenter Contrastive Learning
- [ ] Évaluer + tuner hyperparamètres
- **Gain attendu** : +40-60% qualité embeddings

### Phase 4 : Learning Loop (3 mois)
- [ ] Implémenter feedback UI (like/dislike)
- [ ] Pipeline de réentraînement nightly
- [ ] Monitoring + alertes
- **Gain attendu** : +50-100% amélioration en continu

### Améliorations futures
1. **Reconnaissance de marques/logos** (YOLOv8 + OCR)
2. **Recommandations de style personnalisées** (deep learning)
3. **Partage social** de tenues
4. **Achats intégrés** (liens vers e-commerce)
5. **Mode collaborative** (styliste virtuel)
6. **AR Try-On** (essayage en réalité augmentée)
7. **Sustainable fashion** (analyse durabilité)
8. **Capsule wardrobe** suggestions

---

## 📚 Ressources & Documentation

### Documentation Officielle
- FastAPI : https://fastapi.tiangolo.com/
- React : https://react.dev/
- React Native : https://reactnative.dev/
- Expo : https://docs.expo.dev/

### APIs Utilisées
- Pinecone : https://docs.pinecone.io/
- OpenWeather : https://openweathermap.org/api
- Hugging Face : https://huggingface.co/docs
- Replicate : https://replicate.com/docs

### ML/AI
- FashionCLIP : https://huggingface.co/patrickjohncyh/fashion-clip
- Polyvore Dataset : https://github.com/xthan/polyvore-dataset
- OOTDiffusion : https://github.com/levihsu/OOTDiffusion

---

## 🤝 Contribution au Projet

### Workflow Git
```bash
# 1. Créer une branche
git checkout -b feature/nom-de-la-feature

# 2. Faire vos modifications
git add .
git commit -m "feat: description de la feature"

# 3. Pousser
git push -u origin feature/nom-de-la-feature

# 4. Créer une Pull Request sur GitHub
```

### Convention de Commits
```
feat: nouvelle fonctionnalité
fix: correction de bug
docs: documentation
test: ajout de tests
refactor: refactoring
style: formatage
chore: tâches diverses
```

---

## 📞 Support

Pour toute question :
1. Lire ce guide
2. Consulter les logs : `docker-compose logs backend`
3. Vérifier la configuration `.env`
4. Lancer les tests
5. Contacter l'équipe

---

## ✨ Conclusion

**DressMe** est un projet full-stack moderne qui combine :
- 🎨 Frontend élégant (Web + Mobile)
- 🤖 IA avancée (Vision, ML, LLM)
- 🏗️ Architecture microservices (agents spécialisés)
- 📊 Données structurées (SQL + Vecteurs)
- ☁️ Infrastructure cloud-ready
- ✅ Quality Assurance (Hard Constraints, 30 tests)

C'est un excellent exemple de **comment l'IA peut améliorer la vie quotidienne** de manière concrète et pratique !

---

**Bon développement ! 🚀👔📸**
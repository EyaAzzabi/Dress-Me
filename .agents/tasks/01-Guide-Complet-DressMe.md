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

[... contenu complet du guide ...]

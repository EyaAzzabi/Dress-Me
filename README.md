# DressMe — Personal Fashion Assistant

AI-powered personal fashion assistant: build a digital wardrobe from clothing photos,
get personalized outfit recommendations, and check whether a new purchase is worth it.
See `docs/DressMe.pdf` for the project brief and
`docs/801880877_1090756726785409_1212958715350036331_n.png` for the full architecture
diagram this repo is scaffolded from.

## Structure

```
backend/    FastAPI service: auth, wardrobe/outfit/purchase APIs, agent orchestrator
frontend/
  mobile/   Expo / React Native app (primary client)
  web/      React/Vite web landing page
infra/      docker-compose for Postgres + backend (Pinecone is managed/cloud, no container)
docs/       project brief, personas & architecture deck
```

## Architecture

A FastAPI backend exposes REST endpoints consumed by the mobile/web clients, and
delegates fashion intelligence to an **Agent Orchestrator** coordinating specialized
agents:

- **Vision Agent** — image classification & embeddings (CLIP/CNN)
- **Metadata Agent** — manages the digital wardrobe
- **Style Profile Agent** — learns user style preferences (LLM/RAG)
- **Context Agent** — resolves occasion/weather/season (LLM + rules)
- **Recommendation Agent** — generates outfit suggestions
- **Purchase Agent** — evaluates a potential new purchase
- **LLM Agent** (optional) — natural-language explanations

Data lives in PostgreSQL (relational), Pinecone (vector similarity search), and cloud
object storage (images). See `docs/Copie de user persona architecture (1).pdf` for the
full personas, objectives, and architecture reference this scaffold follows.

## Getting started

```bash
# Backend + data stores
cp backend/.env.example backend/.env
docker compose -f infra/docker-compose.yml up --build

# Mobile app
cd frontend/mobile
npm install
cp .env.example .env
npm start

# Web app
cd frontend/web
npm install
npm run dev
```

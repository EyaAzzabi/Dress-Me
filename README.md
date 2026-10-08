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
  web/      React web client (placeholder)
infra/      docker-compose for Postgres + backend (Pinecone is managed/cloud, no container)
docs/       project brief, personas & architecture deck
```


## Architecture

A FastAPI backend exposes REST endpoints consumed by the mobile/web clients, and
delegates fashion intelligence to an **Agent Orchestrator** coordinating specialized
agents:

- **Vision Agent** — analyzes clothing images, extracts visual features and embeddings (CLIP/CNN)
- **Wardrobe Agent** — manages the user's digital wardrobe (Python + SQL)
- **Recommendation Agent** — generates personalized outfit suggestions (ML / Deep Learning)
- **Purchase Agent** — analyzes a new purchase, detects duplicates and evaluates compatibility (CV + Similarity Search)
- **LLM Agent** (optional) — provides natural-language explanations, personalized style advice and conversational interactions (GPT / LLaMA / Mistral)

The **Agent Orchestrator** analyzes the user's request, plans the required tasks,
coordinates the specialized agents, and generates a coherent response.

Data lives in **PostgreSQL** (relational data), **Qdrant** (vector similarity
search and visual embeddings), and **cloud object storage** (clothing photos,
generated images and user files).

The application can also integrate external services such as **OpenWeather**,
e-commerce APIs (Zara, H&M, ...) and social media APIs (Instagram, Pinterest).

See `docs/Copie de user persona architecture (1).pdf` for the full personas,
objectives, and architecture reference this scaffold follows.

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
```

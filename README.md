# DressMe — Personal Fashion Assistant

AI-powered personal fashion assistant: build a digital wardrobe from clothing photos,
get outfit recommendations, plan outfits on a calendar (and see your avatar wearing them),
pack a suitcase for a trip, and check whether a new purchase is worth it.

Project brief: `docs/DressMe.pdf` · architecture diagram: `docs/DressMe_architecture_4_agents.png`
· personas & architecture deck: `docs/Copie de user persona architecture (1).pdf`.

## Structure

```
backend/    FastAPI service: auth, wardrobe / outfits / calendar / packing / purchase / try-on
            APIs, plus the agent orchestrator (app/agents/)
frontend/
  mobile/   Expo / React Native app
  web/      React + Vite web app (same features as mobile)
ml/         Data understanding, scraping and training notebooks (research folder, not
            needed to run the app — trained artifacts are already in backend/app/ml/artifacts)
infra/      docker-compose: Postgres (+ the backend container)
docs/       project brief, personas, architecture
```

## Architecture

The clients call a REST API (`/api/v1`). Fashion intelligence lives in specialized agents
under `backend/app/agents/`, coordinated by `AgentOrchestrator`:

| Agent | What it does |
|---|---|
| **VisionAgent** | FashionCLIP embeddings; category (trained linear probe, ~84% on in-scope garments), plus zero-shot color / pattern / style / season. Returns a confidence per attribute. |
| **MetadataAgent** | The digital wardrobe: add / correct / remove, search and filters, usage history (calendar + "worn" log). |
| **StyleProfileAgent** | Learns the user's favorite styles/colors from the wardrobe. |
| **ContextAgent** | Occasion / weather (OpenWeather) / season. |
| **RecommendationAgent** | Builds outfits scored by a compatibility model trained on Polyvore; penalizes recently worn pieces. |
| **PackingAgent** | Suitcase list from trip length, type and season; always includes outfits already planned in the calendar. |
| **PurchaseAgent** | Checks a new item against the wardrobe (needs Pinecone). |
| **TryOnAgent** | Virtual try-on (free Hugging Face Space, or Replicate). Used by the Try-on screen and the calendar's avatar render. |
| **LLMAgent** | Optional natural-language explanations. Off by default (`LLM_PROVIDER=none`). |

Data: PostgreSQL (users, items, outfits, calendar, packing, wear log), Pinecone (item
embeddings), S3-compatible storage or a local folder (photos).

## Prerequisites

- **Docker Desktop** (for Postgres) — start it before anything else
- **Python 3.11+** (the Docker image uses 3.12) and **Node 18+**
- Several GB of disk for the Python dependencies (PyTorch) and the FashionCLIP model, which is
  downloaded from Hugging Face on first use

## Run it (local development)

Run the backend on your machine and Postgres in Docker. This is the setup the team uses and
gives you hot reload.

### 1. Database

```bash
docker compose -f infra/docker-compose.yml up -d postgres
```

Postgres listens on `localhost:5432` (user / password / db: `dressme`). The data lives in
the `postgres_data` Docker volume and survives restarts.

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt    # large: includes torch

cp .env.example .env               # then edit it — see "Configuration" below
alembic upgrade head               # create / update the tables
uvicorn app.main:app --reload --port 8000
```

Check: <http://localhost:8000/health> returns `{"status":"ok"}`; interactive API docs at
<http://localhost:8000/docs>.

> **After every `git pull`, run `alembic upgrade head` again.** Other people's schema
> changes arrive as migrations in `backend/alembic/versions/`. If you skip it, the API
> fails with "column does not exist" errors.

### 3. Web app

```bash
cd frontend/web
npm install
npm run dev
```

Open **<http://localhost:5173>** — use `localhost`, not `127.0.0.1`: the backend's CORS
allow-list only contains `localhost` origins. The API URL defaults to
`http://localhost:8000/api/v1` (override with `VITE_API_URL`, see `.env.example`).

### 4. Mobile app

```bash
cd frontend/mobile
npm install
npm start          # then press w (web), a (Android emulator), or scan the QR code with Expo Go
```

The mobile app reads the API URL from **`frontend/mobile/app.json` → `expo.extra.apiUrl`**
(the `.env.example` next to it is not read by the code). It defaults to
`http://localhost:8000/api/v1`. On a **physical phone** `localhost` is the phone itself:
change it to your computer's LAN IP (e.g. `http://192.168.1.20:8000/api/v1`), and set
`PUBLIC_BASE_URL` in `backend/.env` to the same host so photo URLs are reachable too.

### 5. Create an account

There is no seed data. Open the app, register with any email/password, then add a few
clothing photos from the Wardrobe screen.

## Run everything in Docker (alternative)

```bash
cp backend/.env.example backend/.env
docker compose -f infra/docker-compose.yml up --build
```

Starts Postgres and the backend on port 8000 (migrations run automatically at startup). You
still run the frontends with `npm` as above. The first build is slow (PyTorch); if the torch
download stalls, see the comment in `backend/Dockerfile` about pre-fetching the wheel into
`backend/wheels/`.

## Configuration (`backend/.env`)

Never commit `.env` (it is git-ignored). `backend/.env.example` documents every variable;
the ones you will actually touch:

| Variable | Needed for | Notes |
|---|---|---|
| `DATABASE_URL` | everything | Default matches the docker-compose Postgres. |
| `SECRET_KEY` | auth | Change it outside local dev. |
| `LOCAL_STORAGE_DIR` | **photo upload** (dev) | e.g. `./uploads`. Without a storage backend, adding a photo returns 503. Photos are served at `/media`. Use together with `PUBLIC_BASE_URL=http://localhost:8000`. |
| `AWS_*`, `STORAGE_BUCKET` | photo upload (real deployments) | S3 or S3-compatible. |
| `PINECONE_API_KEY` | **outfit recommendations, purchase check** | Free tier at pinecone.io is enough. Without it the app runs, but recommendations return no outfits (they need the stored embeddings) and the purchase check is degraded. |
| `OPENWEATHER_API_KEY` | weather by city | Optional; without it weather stays empty. |
| `TRYON_PROVIDER`, `HF_TOKEN` | virtual try-on / calendar avatar | `auto` uses Replicate if its keys are set, otherwise a **free** Hugging Face Space. `HF_TOKEN` (free account, read token) is optional but raises the daily GPU quota. Needs `LOCAL_STORAGE_DIR` too. |
| `REPLICATE_API_TOKEN`, `REPLICATE_TRYON_MODEL_VERSION` | try-on via Replicate (paid) | Optional. |
| `LLM_PROVIDER`, `LLM_API_KEY` | AI-written explanations | Optional, default `none`. |
| `CORS_ORIGINS` | browser clients | Add your deployed web origin. |

## Tests

```bash
cd backend
python -m pytest tests -q
```

- Most tests are fast and use an in-memory SQLite database.
- `tests/test_live_integration.py` runs against the real Postgres and real product photos
  from the internet, and exercises the real vision model — start Postgres first (it skips
  itself if Postgres isn't reachable).
- `tests/test_vision_agent.py` needs the local image set `ml/data/raw/tunisian_images`
  (git-ignored research data) and skips itself without it.
- Front ends: `npx tsc --noEmit` in `frontend/web` and `frontend/mobile` (the mobile app
  also has `npm run typecheck`).

## Working on the code

- **Changed a model in `backend/app/models/`?** Add an Alembic migration in the same commit
  (`alembic revision -m "what changed"`, edit it, then `alembic upgrade head`). The schema in
  the database and in the models must stay identical, or the API breaks for everyone.
  Test your migration both ways: `alembic downgrade -1` then `alembic upgrade head`.
- List columns (colors, item ids) are stored as JSON text via the type decorators in the
  models, not as native Postgres arrays — keep it that way so the models also work on SQLite.
- New agent behavior goes in `backend/app/agents/`; routes in `backend/app/api/routes/` stay
  thin and call the agents or the orchestrator.
- Run the test suite before pushing, and check both front ends type-check.

## Behaviors worth knowing

- **Uncertain photos:** if the Vision Agent is less than 50% sure of a photo's category
  (typically a photo of several pieces at once), `POST /wardrobe/` answers 422
  `low_category_confidence` and the apps ask the user to confirm the category. The 0.50
  threshold was calibrated on catalog-style photos and may need revisiting with real phone
  photos (`CATEGORY_MIN_CONFIDENCE` in `backend/app/ml/vision_model.py`).
- **Seasons:** `ete`, `hiver`, `mi_saison`, `toutes_saisons`. The model only *suggests* a
  season; the app shows "À confirmer" until the user picks one.
- **Calendar avatar:** `POST /calendar/{day}/render` dresses the avatar in the day's outfit —
  one try-on call per garment, a minute or more, so it only runs on request and the result is
  cached until the outfit or the avatar photo changes.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `connection refused` on port 5432 | Docker Desktop isn't running, or the Postgres container isn't up: `docker compose -f infra/docker-compose.yml up -d postgres`. |
| `column ... does not exist` / `UndefinedColumn` | You pulled new code: `alembic upgrade head`. |
| Browser shows a CORS error | Open the web app at `http://localhost:5173`, not `127.0.0.1`. |
| Adding a photo returns 503 "storage isn't configured" | Set `LOCAL_STORAGE_DIR=./uploads` (and `PUBLIC_BASE_URL`) in `backend/.env`, restart the backend. |
| Recommendations return nothing | `PINECONE_API_KEY` isn't set (or the wardrobe has fewer than a top + bottom or a dress). |
| First photo is very slow | FashionCLIP is downloading from Hugging Face (one time). |
| `npm install` fails with `EPERM` / `EACCES` on Windows | Try `npm install --ignore-scripts` (this is what worked for us); also close anything scanning or syncing the folder (editor, antivirus, OneDrive). |
| Try-on fails with a quota message | The free GPU quota is used up — wait, or set `HF_TOKEN` to a free Hugging Face token. |

## Where we are / what's next

Done: wardrobe with confidence-aware vision analysis, season handling, usage tracking,
season-aware packing, calendar with avatar render, free try-on provider.

Suggested next work, roughly by value:

1. **RecommendationAgent**: today `occasion` and `weather` only appear in the explanation text
   and don't influence the choice — filter/rank by them, add color-harmony rules and variety
   across the suggested outfits, and add a small hand-labeled set to measure quality.
2. **LLMAgent**: switch it on with a free provider (Mistral free tier, or Llama via Ollama:
   `LLM_PROVIDER=llama`, `LLM_BASE_URL=http://localhost:11434/v1`, `LLM_MODEL=llama3`).
3. **PurchaseAgent / StyleProfileAgent**: review and improve (not yet revisited).
4. **Calibration with real uploads**: confidence thresholds (category, style, season) were set
   on catalog photos.
5. Route the calendar endpoints through the orchestrator (there is no calendar agent yet).

# Infra

Local dev stack: Postgres (relational data) + the FastAPI backend. Vector search runs on
Pinecone, a managed cloud service — no local container for it, just a `PINECONE_API_KEY`
in `backend/.env`.

```bash
cp ../backend/.env.example ../backend/.env
# fill in PINECONE_API_KEY (from https://app.pinecone.io) before starting
docker compose up --build
```

Backend will be at http://localhost:8000, docs at http://localhost:8000/docs.

### Use Supabase for the backend database

Set `DATABASE_URL` in `backend/.env` to the Supabase Postgres connection string. From
this `infra` directory, start the backend with the opt-in Compose override:

```bash
docker compose --env-file ../backend/.env -f docker-compose.yml -f docker-compose.supabase.yml up --build -d --no-deps backend
```

The regular `docker compose up --build` command continues to use the local Docker
Postgres database.

### Database migrations

Tables aren't created automatically — run Alembic once Postgres is up:

```bash
cd ../backend
python -m alembic upgrade head
```

To generate a new migration after changing a model in `app/models/`:

```bash
python -m alembic revision --autogenerate -m "describe the change"
python -m alembic upgrade head
```

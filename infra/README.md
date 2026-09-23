# Infra

Local dev stack: Postgres (relational data) + Qdrant (vector search) + the FastAPI backend.

```bash
cp ../backend/.env.example ../backend/.env
docker compose up --build
```

Backend will be at http://localhost:8000, docs at http://localhost:8000/docs.

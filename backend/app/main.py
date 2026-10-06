from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import api_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)

if settings.local_storage_dir:
    # Dev/testing-only fallback for wardrobe photo uploads when no cloud storage
    # account is set up — see app/services/storage.py.
    from pathlib import Path

    Path(settings.local_storage_dir).mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=settings.local_storage_dir), name="media")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    # No cookies are used for auth (Bearer tokens via an Authorization header, see
    # frontend/mobile/src/api/client.ts and frontend/web) — allow_credentials=True
    # together with a wildcard origin is invalid per the CORS spec anyway, and isn't
    # needed here.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

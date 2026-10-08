from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "DressMe API"
    api_v1_prefix: str = "/api/v1"
    # Comma-separated. Defaults cover local dev (Vite web, Expo web/Metro) — the
    # mobile app itself authenticates via a Bearer header, not cookies, so it isn't
    # subject to browser CORS at all; this only matters for browser-based clients.
    cors_origins: str = "http://localhost:5173,http://localhost:8081,http://localhost:8082,http://localhost:19006"

    secret_key: str = "change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    database_url: str = "postgresql+psycopg://dressme:dressme@localhost:5432/dressme"
    pinecone_api_key: str | None = None
    pinecone_index_name: str = "dressme-clothing-embeddings"

    storage_bucket: str = "dressme-wardrobe"
    aws_region: str = "us-east-1"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    # Override for S3-compatible non-AWS storage (MinIO, DigitalOcean Spaces, ...).
    # Leave unset for real AWS S3. See app/services/storage.py.
    storage_endpoint_url: str | None = None
    # Explicit opt-in local-disk fallback for dev/testing without any cloud account —
    # a directory the backend process can write to; served back via StaticFiles at
    # /media (see app/main.py). Deliberately separate from "unconfigured" (leaving
    # everything above unset still raises, per app/services/storage.py's docstring) —
    # this only activates when someone sets it on purpose.
    local_storage_dir: str | None = None
    public_base_url: str = "http://localhost:8000"

    openweather_api_key: str | None = None
    llm_api_key: str | None = None
    llm_provider: str = "none"  # none | openai | mistral | llama
    # Only needed to override the provider's default (openai/mistral have one; "llama"
    # has no single standard host — self-hosted via vLLM/Ollama/Together, so both must
    # be set explicitly for that provider). See app/agents/llm_agent.py.
    llm_base_url: str | None = None
    llm_model: str | None = None

    # Virtual try-on (TryOnAgent) via Replicate's hosted API — no local GPU needed.
    # replicate_tryon_model_version has no safe hardcoded default: Replicate model
    # version ids change over time and can't be verified without an account, so it's
    # left for whoever sets up the account to copy from the model's Replicate page
    # (e.g. search "idm-vton" or "ootdiffusion" on replicate.com) rather than guessed.
    replicate_api_token: str | None = None
    replicate_tryon_model_version: str | None = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()

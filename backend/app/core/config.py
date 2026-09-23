from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "DressMe API"
    api_v1_prefix: str = "/api/v1"

    secret_key: str = "change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    database_url: str = "postgresql+psycopg://dressme:dressme@localhost:5432/dressme"
    qdrant_url: str = "http://localhost:6333"

    storage_bucket: str = "dressme-wardrobe"

    openweather_api_key: str | None = None
    llm_api_key: str | None = None
    llm_provider: str = "none"  # none | openai | mistral | llama

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()

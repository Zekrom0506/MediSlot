from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All application settings, read from environment variables (or a .env file)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "MediSlot"
    environment: str = "development"

    database_url: str = "postgresql+psycopg://medislot:medislot@localhost:5432/medislot"
    redis_url: str = "redis://localhost:6379/0"


@lru_cache
def get_settings() -> Settings:
    """Return one shared Settings object so the environment is only read once."""
    return Settings()

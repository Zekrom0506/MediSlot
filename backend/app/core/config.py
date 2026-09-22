from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "dev-only-secret-change-me"


class Settings(BaseSettings):
    """All application settings, read from environment variables (or a .env file)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "MediSlot"
    environment: str = "development"

    database_url: str = "postgresql+psycopg://medislot:medislot@localhost:5432/medislot"
    database_pool_size: int = 20
    database_max_overflow: int = 20

    redis_url: str = "redis://localhost:6379/0"

    clinic_timezone: str = "Asia/Kolkata"
    slot_generation_days: int = 14
    cancellation_deadline_hours: int = 2

    jwt_secret_key: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    @model_validator(mode="after")
    def refuse_default_secret_in_production(self) -> "Settings":
        """Fail fast at startup instead of running production with a guessable JWT secret."""
        if self.environment == "production" and self.jwt_secret_key == DEFAULT_JWT_SECRET:
            raise ValueError("JWT_SECRET_KEY must be set in production")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return one shared Settings object so the environment is only read once."""
    return Settings()

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings. The only place that reads environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://movie:movie@localhost:5432/movie"
    redis_url: str = "redis://localhost:6379/0"
    meili_url: str = "http://localhost:7700"
    meili_master_key: SecretStr | None = None

    # Optional (ADR-025). Unset or empty disables TMDB: no calls, posters stay placeholders.
    # Accepts the v3 API key or the v4 API Read Access Token from the TMDB account settings.
    tmdb_api_key: SecretStr | None = None
    tmdb_api_url: str = "https://api.themoviedb.org/3"

    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("tmdb_api_key", mode="before")
    @classmethod
    def _blank_key_is_unset(cls, value: object) -> object:
        # Compose passes `${TMDB_API_KEY:-}`, so "not configured" arrives as "".
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()

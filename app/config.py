"""Application configuration, loaded from environment variables (and a local .env file, if present).

Centralizing configuration here means every other module reads settings through a single
`get_settings()` accessor instead of calling `os.getenv` ad hoc, and makes it trivial to
override configuration in tests by setting environment variables before the app is imported.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the API.

    All fields can be overridden via environment variables of the same name (case-insensitive).
    See `.env.example` for a documented template.
    """

    # SQLAlchemy connection string. Defaults to a local SQLite file so the project runs with
    # zero external infrastructure. Must stay valid against PostgreSQL too -- see README.
    database_url: str = "sqlite:///./sales_metrics.db"

    # Shared secret required in the `X-API-Key` header for protected endpoints.
    api_key: str = "changeme"

    # TTL, in seconds, for the in-process cache used by GET /metrics/revenue.
    cache_ttl_seconds: int = 60

    # Human-readable API metadata (used in OpenAPI docs).
    app_name: str = "Sales Metrics API"
    app_version: str = "1.0.0"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    `lru_cache` ensures the environment is only parsed once per process, while still allowing
    tests to get a fresh instance by calling `get_settings.cache_clear()` after changing
    environment variables.
    """

    return Settings()

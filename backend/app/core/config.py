"""
backend/app/core/config.py — Application Configuration

This module uses Pydantic Settings to load configuration from environment
variables (and the .env file). Instead of scattered os.getenv() calls,
all config lives here in one typed class.

Usage anywhere in the app:
    from app.core.config import settings
    print(settings.GEMINI_API_KEY)
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """
    All application settings.
    
    Pydantic automatically reads these from environment variables.
    The variable names are case-insensitive — GEMINI_API_KEY in .env
    maps to settings.GEMINI_API_KEY here.
    """

    # ---- Database ----
    DATABASE_URL: str = "postgresql://dyversifying_user:change_me_in_production@localhost:5432/dyversifying_db"

    # ---- Gemini AI ----
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-001"
    EMBEDDING_DIMENSION: int = 3072

    # ---- Auth ----
    SECRET_KEY: str = "dev_secret_key_change_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours (matches render.yaml)

    # ---- File Storage ----
    UPLOAD_DIR: str = "data/raw"
    PROCESSED_DIR: str = "data/processed"

    # ---- App ----
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    # Comma-separated list of allowed frontend origins for CORS in production.
    # Example: "https://dyversifying.vercel.app,https://dyversifying.io"
    FRONTEND_URL: str = "http://localhost:3000"

    # Tell Pydantic to read from a .env file in the project root
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore unknown env vars — avoids errors from unrelated vars
    )


@lru_cache()
def get_settings() -> Settings:
    """
    Returns the settings instance.
    
    @lru_cache() means this is only computed ONCE and then cached —
    efficient for a module-level singleton that's accessed thousands of times.
    """
    return Settings()


# Module-level singleton — import this anywhere
settings = get_settings()

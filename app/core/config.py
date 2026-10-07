"""
Application settings using Pydantic BaseSettings.

Design: Singleton Pattern via @lru_cache — the Settings object is created once
and reused across the entire application, making it cheap to call get_settings()
anywhere without recreating the object.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration loaded from environment variables or a .env file."""

    APP_NAME: str = "Bulk Certificate Generator"
    APP_VERSION: str = "1.0.0"

    # Database
    DATABASE_URL: str = "sqlite:///./cert_generator.db"

    # Storage for generated PDFs
    STORAGE_DIR: Path = Path("storage/certificates")

    # Certificate generation backend (extensible via the Factory)
    GENERATOR_TYPE: str = "pillow_reportlab"

    # Limits
    MAX_RECIPIENTS_PER_JOB: int = 1000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings (Singleton via lru_cache)."""
    return Settings()

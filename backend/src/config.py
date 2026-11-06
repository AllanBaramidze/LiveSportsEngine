"""Application settings, read from environment variables or `.env.local`.

Import the ready-made `settings` object instead of building `Settings` yourself.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root (LiveSportsEngine/), so .env.local is found no matter which directory you run from.
ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration.

    Each field is filled from the environment variable of the same name (case-insensitive),
    falling back to `.env.local` in the repo root. Unknown variables in that file are ignored.

    Attributes:
        database_url: SQLAlchemy URL for Postgres.
        db_echo: Log every SQL statement. Noisy; for debugging only.
        valkey_host: Host of the Valkey server.
        valkey_port: Port of the Valkey server.
    """

    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env.local", extra="ignore")

    # e.g. postgresql+psycopg://user:password@localhost:5432/dbname
    database_url: str
    db_echo: bool = False

    valkey_host: str = "localhost"
    valkey_port: int = 6379



# Created once at import time; raises a validation error if a required value is missing.
settings = Settings()

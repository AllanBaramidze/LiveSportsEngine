from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root (LiveSportsEngine/), so .env.local is found no matter which directory you run from.
ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env.local", extra="ignore")

    # e.g. postgresql+psycopg://user:password@localhost:5432/dbname
    database_url: str
    db_echo: bool = False



settings = Settings()

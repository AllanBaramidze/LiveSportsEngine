# Changelog

All notable changes to this project. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Newest first.

## [Unreleased]

### 2026-10-03

#### Added
- `backend/documentation/`: `overview.md`, `changelog.md`, `espn_api.ipynb` (ESPN API breakdown with curl commands).
- `status` column on `matches` (ESPN `pre` / `in` / `post`, default `pre`); parser and upsert fill and update it. Migration `add status to matches`.
- NHL (`hockey/nhl`) added to ingested leagues.
- `src/main.py`: polling loop that ingests today's games (US Eastern date) every 60 s, logs per-league results, survives failed cycles, and shuts down cleanly on Ctrl+C.
- Editable install of the project (`[build-system]` + hatch `dev-mode-dirs = ["backend"]`) so `import src...` works from any directory.
- `[tool.mypy]` config with the pydantic plugin; `[tool.ruff] src = ["backend"]`.
- Layered ESPN ingest:
  - `client/espn/espn_client.py`: `EspnClient` (async, HTTP only)
  - `client/espn/parser.py`: `parse_scoreboard` (pure function)
  - `schemas/match.py`: `MatchCreate`
  - `database/repositories/matches.py`: upsert + read queries
  - `services/espn_ingest.py`: orchestration, owns the commit
- Example scripts: `client/espn/tests/test_async_ingest.py`, `database/tests/test_queries.py`.
- Alembic post-write hooks run ruff on newly generated migrations.
- Initial migration `create matches table` (`matches` with unique `espn_id`).
- Database setup: `config.py` (settings from `.env.local`), async engine + `SessionLocal`, `Match` model, Alembic `env.py` wired to settings and `Base.metadata`.
- `compose.yaml` (Postgres 18) and `.env.example`.

#### Fixed
- Postgres container volume predated `POSTGRES_DB`, so the `livesports` database was never created; created manually.
- First `add status` migration failed (`'SCHEDULED'` longer than `varchar(8)`); regenerated with default `pre`.

#### In progress
- `home_score` on `Match` (currently an incomplete line `Mapped[]` that stops the app from importing).

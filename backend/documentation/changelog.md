# Changelog

All notable changes to this project. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Newest first.

## [Unreleased]

### 2026-10-07 (evening)

#### Added
- In-game ESPN win-probability polling, every 10 s for `in` games: `EspnClient.get_game_info`
  (status + latest reading + its play), `parser.parse_observations`, `espn_ingest.poll_in_game`
  (per-game `ingest_time`, one commit), `main.query_ingame`.
- `espn_observations` table (model `EspnObservation`, schema `EspnObservationCreate`,
  repository `espn_observations.insert_observations`) with `espn_reading_count` and per-play scores.
- `matches.list_in_progress`, `matches.update_score` (only when the score differs).
- Games move `in` → `post` from the in-game poll's status check.

#### Changed
- Table `observations` renamed to `espn_observations` (one observations table per data source);
  its sequence, index and constraints renamed to match. Hand-written migrations, no data change.

#### Fixed
- `ingest_time` was stored 4 h early (naive `datetime.now()`); now `datetime.now(UTC)`.
- Tie probability read from the wrong key (`tieWinPercentage` → `tiePercentage`).

### 2026-10-04 → 2026-10-07

#### Added
- `observations` table designed (built the same evening; see above).
- Pre-game status check: `matches.list_due_pregame`, `EspnClient.get_match_status` (core `/status`),
  `parser.parse_state`, `matches.update_status`, `espn_ingest.refresh_statuses`, `main.query_pre`.
- `main.py` runs the daily schedule and the pre-game check as two loops (`every` + `asyncio.TaskGroup`).
- `sport` column on `matches` (passed into the parser from `LEAGUES`); `home_score` / `away_score` columns.
- NBA (`basketball/nba`) added to `LEAGUES`.
- Notebook: "Quick look" section (`fetch_scoreboard`, `find_value`) and a score walkthrough (section 10).

#### Changed
- Daily schedule window is today → today + 6 (Eastern), refreshed every 24 h.
- NHL removed from `LEAGUES` (ESPN publishes no NHL win probability).

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

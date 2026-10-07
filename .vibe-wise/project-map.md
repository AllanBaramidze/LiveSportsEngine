# Project Map

## Purpose
Real-time comparison of ESPN win probabilities against Polymarket prices during live North American sports games, surfacing divergences (README.md).

## Requirements
- Store each game (implemented: `matches` table).
- Record game scores (learner in progress: `home_score` on `Match`).
- Record, over the course of a game: ESPN home/away win probability and Polymarket home/away price, for charting and for the pricing engine (requested; design not chosen).
- Documentation folder at `backend/documentation/` (requested).

## Components
Implemented (verified):
- `backend/src/config.py`: settings from `.env.local` (pydantic-settings).
- `backend/src/database/database.py`: async engine + `SessionLocal`.
- `backend/src/database/models.py`: `Match` model.
- `backend/migrations/`: Alembic (2 migrations: create matches, add status).
- `backend/src/schemas/match.py`: `MatchCreate` (pydantic).
- `backend/src/client/espn/espn_client.py`: `EspnClient` (HTTP, scoreboard endpoint).
- `backend/src/client/espn/parser.py`: scoreboard JSON → `MatchCreate`.
- `backend/src/database/repositories/matches.py`: upsert + read queries.
- `backend/src/services/espn_ingest.py`: fetch → parse → upsert; LEAGUES nfl, mlb, nhl.
- `backend/src/main.py`: fixed 60 s polling loop.
Empty placeholders: `backend/src/services/espn_poller.py`, `backend/src/engine/` (pricing engine?).
Not present: Polymarket client.

## Main Flow
main.py loop (60 s) → espn_ingest.ingest_days → EspnClient.get_scoreboard ──HTTP──► ESPN
  → parse_scoreboard → MatchCreate → matches.upsert_matches → Postgres `matches`
Polymarket ──?──► ? ──?──► Postgres ?
Postgres ──?──► pricing engine (src/engine/, empty) ──?──► ?

## Data and Trust Boundaries
- Postgres 18 in Docker (`compose.yaml`), credentials in gitignored `.env.local`.
- ESPN: public, unauthenticated site API.
- Polymarket: unknown (no code yet). `Match.poly_slug` column exists; how it gets filled is unknown.

Schedule discovery (confirmed design 2026-10-04, not yet implemented): main.py ingests today..today+7 (Eastern) at startup, then once per new Eastern day ingests only today+7, via `date_range` + `ingest_days`. 30 s today-poll stays until live tracking (designed later).

Time handling (decided 2026-10-04): timestamps stored as `timestamptz` (exact instants, UTC from ESPN); shown in America/New_York for display. ESPN's scoreboard `dates=` is an Eastern calendar day.

## Build and Deployment
- `docker compose up -d db`
- `uv sync` (installs project editable; `backend/` on import path)
- `uv run alembic -c backend/alembic.ini upgrade head`
- `uv run python -m src.main`
Deployment: unknown.

In-game storage (PROPOSED by learner 2026-10-06, not confirmed, not implemented): poller → Redis (latest values, for the pricing engine's low-latency reads) → Postgres only when a value moved (durable history for backtesting / model training / crash recovery). Each entry has `espn_time` + `polymarket_time` for freshness.

`espn_observations.py` (CONFIRMED design 2026-10-07, not yet implemented): id PK; espn_id FK→matches.espn_id; wall_clock + ingest_time (timestamptz); espn_home_prob / espn_tie_prob (nullable) / espn_away_prob (NUMERIC); period (int); clock (nullable text); play_id; unique (espn_id, play_id, home, tie, away) NULLS NOT DISTINCT + ON CONFLICT DO NOTHING; index (espn_id, wall_clock). Sport detail tables (e.g. MLB pitcher / batter / count / inning side) reference the observation row. Leagues: NFL, NBA, MLB (NHL dropped). Source: ESPN core probabilities, latest reading every 5 s for `in` games.

Roadmap (learner, 2026-10-07): finish ESPN feed → Polymarket feed → frontend + model training on ESPN + Polymarket data. Model type not chosen.

## Unknowns
- Storage model for win-probability / price history over a game (proposal above; open: who writes Postgres, what counts as movement, fetch time vs source event time).
- How a match is linked to its Polymarket market.
- Pricing engine inputs, outputs and how it reads the data.
- Which ESPN endpoint to use for live win probability (options documented in `backend/documentation/espn_api.ipynb`; NHL has none).
- How ESPN readings (per play, time via play `wallclock`) and Polymarket prices (own clock) are aligned.

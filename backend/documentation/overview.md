# Live Sports Engine: Overview

_Last updated: 2026-10-03_

## Purpose

Compare ESPN's live win probabilities with Polymarket prices during North American
sports games, and surface moments where the two disagree by more than a meaningful
threshold.

## Current status

| Area | State |
|---|---|
| Postgres + migrations | Working (Docker, SQLAlchemy 2 async, Alembic) |
| ESPN game ingest | Working: scoreboard for NFL, MLB, NHL, upserted every 60 s |
| Game status (`pre` / `in` / `post`) | Working |
| Scores | In progress (`home_score` being added to `Match`) |
| ESPN win probability | Not started (endpoint researched, see `espn_api.ipynb`) |
| Polymarket prices | Not started |
| Pricing engine (`src/engine/`) | Not started (empty package) |
| Variable polling interval | Not started (`src/services/espn_poller.py` empty) |

## How data flows today

```
src/main.py  (loop: every 60 s)
   └─► services/espn_ingest.ingest_days([today, US Eastern])
          ├─► client/espn/espn_client.EspnClient.get_scoreboard   ──HTTP──►  ESPN site API
          ├─► client/espn/parser.parse_scoreboard   raw JSON ─► list[MatchCreate]
          └─► database/repositories/matches.upsert_matches   ─► Postgres `matches`
```

Not yet designed (open questions, see the end of this file):

```
Polymarket ──?──► ? ──?──► Postgres ?
Postgres   ──?──► pricing engine ──?──► ?
```

## Folder layout

```
LiveSportsEngine/
├── compose.yaml                 Postgres 18 container (reads .env.local)
├── .env.example                 template for .env.local (committed; real values are not)
├── pyproject.toml               deps + ruff/mypy config + editable install of backend/
└── backend/
    ├── alembic.ini              Alembic settings (DB URL injected at runtime, no secrets)
    ├── migrations/              env.py + versions/ (one file per schema change)
    ├── documentation/           this folder
    └── src/
        ├── main.py              entry point: the polling loop
        ├── config.py            Settings read from .env.local
        ├── schemas/match.py     MatchCreate: the shape shared by parser and repository
        ├── client/espn/
        │   ├── espn_client.py   HTTP only: returns raw ESPN JSON
        │   └── parser.py        pure function: raw JSON → MatchCreate
        ├── database/
        │   ├── database.py      async engine + SessionLocal
        │   ├── models.py        ORM tables (Match)
        │   └── repositories/matches.py   all SQL for `matches`; never commits
        ├── services/
        │   ├── espn_ingest.py   fetch → parse → store; owns the commit
        │   └── espn_poller.py   (empty) future variable-interval loop
        └── engine/              (empty) future pricing engine
```

### Layer rules

- **Client**: HTTP only. No parsing, no database.
- **Parser**: no network, no database. Testable against a saved JSON file.
- **Repository**: SQL only. Takes a session, never commits.
- **Service**: the only layer that touches both ESPN and the database; decides when to commit.

## Data model

### `matches` (one row per game)

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | internal id |
| `espn_id` | varchar(32), unique | ESPN event id; the upsert key |
| `league` | varchar(16) | `nfl`, `mlb`, `nhl` |
| `matchup` | text | e.g. "Kansas City Chiefs at Miami Dolphins" |
| `status` | varchar(8), default `pre` | ESPN `status.type.state`: `pre` / `in` / `post` |
| `home_team`, `away_team` | text | display names |
| `date` | timestamptz | scheduled start (UTC) |
| `poly_slug` | text, nullable | Polymarket market slug; how it gets filled is not decided |

Migrations: `create matches table`, `add status to matches`.

## ESPN data coverage (verified 2026-10-03)

| Data | NFL | MLB | NHL |
|---|---|---|---|
| Scoreboard + scores | ✅ | ✅ | ✅ |
| Win probability (summary `winprobability`, core `probabilities`) | ✅ | ✅ | ❌ (empty / HTTP 400) |
| Sportsbook odds (core `odds`) | ✅ | ✅ | ✅ |
| Live situation (core `situation`) | down, distance | balls, strikes, outs, runners | power play, empty net |

Details, field names and curl commands: [`espn_api.ipynb`](espn_api.ipynb).

## Running it

From the repo root:

```bash
docker compose up -d db                              # start Postgres
uv sync                                              # install deps + backend/ on import path
uv run alembic -c backend/alembic.ini upgrade head   # apply migrations
uv run python -m src.main                            # start the 60 s loop (Ctrl+C to stop)
```

Open a SQL prompt:

```bash
docker compose exec db psql -U postgres -d livesports
```

## Secrets

- Real credentials live only in `.env.local` (gitignored by `.env.*` with `!.env.example`).
- `alembic.ini` has an empty `sqlalchemy.url`; `migrations/env.py` fills it from settings.

## Open design questions

These are undecided. They belong to the project owner and are listed here so they don't get lost.

1. How to record ESPN win probability and Polymarket prices **over the course of a game**
   (many readings per game), and how the pricing engine reads them.
2. How a match is linked to its Polymarket market (`poly_slug` exists; source unknown).
3. What to do for NHL, where ESPN publishes no win probability.
4. How readings from ESPN and Polymarket are aligned in time (ESPN win probability
   entries carry a `playId`, not a timestamp; the play's `wallclock` has the time).
5. Poll interval rules for the variable poller.

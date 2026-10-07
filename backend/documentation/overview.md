# Live Sports Engine: Overview

_Last updated: 2026-10-07_

## Purpose

Compare ESPN's live win probabilities with Polymarket prices during North American
sports games, and surface moments where the two disagree by more than a meaningful
threshold.

## Current status

| Area | State |
|---|---|
| Postgres + migrations | Working (Docker, SQLAlchemy 2 async, Alembic) |
| Leagues | NFL, MLB, NBA (NHL dropped: ESPN has no NHL win probability) |
| Daily schedule ingest | Working: today → today + 6 (Eastern), every 24 h |
| Pre-game status check (`pre` → `in`) | Working: due games' status via ESPN core `/status` |
| Scores, sport | Working (columns on `matches`; live score updated by the in-game poll) |
| In-game ESPN win probability | Working: `espn_observations` table, polled every 10 s for `in` games |
| Game end (`in` → `post`) | Working: the in-game poll reads each game's status and moves it to `post` |
| Valkey (latest values) | Planned (after the Postgres path); layout not designed |
| Polymarket prices | Not started |
| Pricing engine (`src/engine/`) | Not started (empty package) |

## How data flows today

`main.py` runs three loops side by side (`every(...)` helper + `asyncio.TaskGroup`):

```
daily schedule (every 24 h)
   └─► espn_ingest.ingest_days(today … today+6)
          ├─► EspnClient.get_scoreboard      ──HTTP──►  ESPN site API
          ├─► parser.parse_scoreboard         raw JSON ─► list[MatchCreate]
          └─► matches.upsert_matches          ─► Postgres `matches`

pre-game check
   ├─► matches.list_due_pregame               `pre` games starting within `lead`
   └─► espn_ingest.refresh_statuses(games)
          ├─► EspnClient.get_match_status     ──HTTP──►  ESPN core API /status
          ├─► parser.parse_state              ─► "pre" | "in" | "post"
          └─► matches.update_status           ─► Postgres `matches.status`

in-game check (every 10 s)
   ├─► matches.list_in_progress               games with status "in"
   └─► espn_ingest.poll_in_game(games)
          ├─► fetch_game → EspnClient.get_game_info   status + latest reading + its play (5 requests)
          │                 ingest_time = now (UTC), stamped per game as its data arrives
          ├─► parser.parse_observations       ─► EspnObservationCreate
          ├─► espn_observations.insert_observations   ─► Postgres `espn_observations` (repeats ignored)
          ├─► matches.update_score            only when the score differs from `matches`
          └─► matches.update_status           "post" takes the game out of the loop
             (all of the above committed together)
```

Planned, not built:

```
in-game check ─► Valkey (latest values, for the pricing engine)
```

Not yet designed:

```
Polymarket ──?──► ? ──?──► Valkey / polymarket_observations ?
Valkey / Postgres ──?──► pricing engine ──?──► ?
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
        ├── main.py              entry point: the three polling loops
        ├── config.py            Settings read from .env.local
        ├── schemas/
        │   ├── match.py             MatchCreate: shared by parser and repository
        │   └── espn_observation.py  EspnObservationCreate: one ESPN win-probability reading
        ├── client/espn/
        │   ├── espn_client.py   HTTP only: returns raw ESPN JSON
        │   └── parser.py        pure functions: raw JSON → MatchCreate / state / EspnObservationCreate
        ├── database/
        │   ├── database.py      async engine + SessionLocal
        │   ├── models.py        ORM tables (Match, EspnObservation)
        │   └── repositories/
        │       ├── matches.py            all SQL for `matches`; never commits
        │       └── espn_observations.py  all SQL for `espn_observations`; never commits
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
| `sport` | text | `football`, `baseball`, `basketball` (from `LEAGUES`, not from ESPN's JSON) |
| `league` | varchar(16) | `nfl`, `mlb`, `nba` |
| `matchup` | text | e.g. "Kansas City Chiefs at Miami Dolphins" |
| `status` | varchar(8), default `pre` | ESPN `status.type.state`: `pre` / `in` / `post` |
| `home_team`, `away_team` | text | display names |
| `home_score`, `away_score` | varchar(16), default `'0'` | stored as text, as ESPN sends them |
| `date` | timestamptz | scheduled start (UTC) |
| `poly_slug` | text, nullable | Polymarket market slug; how it gets filled is not decided |

Migrations: `create matches table`, `add status`, `add scores`, `add sport`.

### `espn_observations` (built 2026-10-07; model `EspnObservation`)

One row per ESPN win-probability reading for a play of an in-progress game: written from
the first play onward, and again whenever ESPN rewrites that play's probability.
Each data source gets its own observations table (Polymarket will be `polymarket_observations`),
so sources can be added independently; they are lined up by time.

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | so sport detail tables can point at a row; ids are not consecutive |
| `espn_id` | FK → `matches.espn_id` | |
| `play_id` | text | ESPN play id (one probability entry per play; same id) |
| `wall_clock` | timestamptz | real-world time of the play (ESPN `wallclock`) |
| `period` | int | quarter / inning number |
| `clock` | text, nullable | in-game clock, e.g. `14:14` (NBA shows `0.0` in the last minute); none for MLB |
| `espn_home_prob` | numeric | 0–1 |
| `espn_tie_prob` | numeric, nullable | |
| `espn_away_prob` | numeric | 0–1 |
| `espn_reading_count` | int | ESPN's reading count at that moment; a jump > 1 between rows = readings missed between polls |
| `home_score`, `away_score` | int | score at that play |
| `ingest_time` | timestamptz | when this app received the reading (UTC, captured per game) |

- **Same reading** = `uq_espn_observations_reading`: unique on (`espn_id`, `play_id`,
  `espn_home_prob`, `espn_tie_prob`, `espn_away_prob`) with `NULLS NOT DISTINCT`; inserted with
  `ON CONFLICT DO NOTHING`, so a repeat poll is ignored and a rewrite becomes a new row.
- Index `ix_espn_observations_espn_id_wall_clock` for "this game's readings in time order".
- Source: ESPN core status + probabilities (latest reading) for `in` games.
- Sport detail tables (MLB first: pitcher, batter, count, inning side) will reference
  `espn_observations.id`, written in the same transaction as the observation.
- Three different times: `wall_clock` (when the play happened), `period` + `clock` (where in
  the game), `ingest_time` (when we knew). Gaps between `wall_clock`s show stoppages;
  `ingest_time − wall_clock` is ESPN's delay (≈ 16–20 s on the first MLB game).

Migrations: `created observations table`, `added reading count`, `add scores`,
`rename observations to espn_observations` (`op.rename_table`, hand-written),
`rename espn_observations indexes and constraints`.

## ESPN data coverage (verified 2026-10-03, NBA 2026-10-07)

| Data | NFL | MLB | NBA | NHL |
|---|---|---|---|---|
| Scoreboard + scores | ✅ | ✅ | ✅ | ✅ |
| Win probability (core `probabilities`) | ✅ (169 readings in one game) | ✅ | ✅ (483 in one preseason game) | ❌ (empty / HTTP 400) |
| Sportsbook odds (core `odds`) | ✅ | ✅ | not checked | ✅ |
| Live situation (core `situation`) | down, distance | balls, strikes, outs, runners | not checked | power play, empty net |

`EspnClient.get_game_info` makes 5 small requests (~5 KB) per game: `/status` → 
`probabilities?limit=1` (gives `count`) → `?limit=1&page=<count>` → the reading's `$ref` →
its `play` `$ref` (for `wallclock`, `clock`, `period`, scores). The site summary has the
reading data in one request but is ~535 KB.

End of game: the status endpoint (`state = "post"`) is used because the final play's text
differs by sport (NFL `END GAME`, NBA `End of Game`, MLB has no end-of-game play).

Details, field names and curl commands: [`espn_api.ipynb`](espn_api.ipynb).

## Running it

From the repo root:

```bash
docker compose up -d db                              # start Postgres
uv sync                                              # install deps + backend/ on import path
uv run alembic -c backend/alembic.ini upgrade head   # apply migrations
uv run python -m src.main                            # start the pollers (Ctrl+C to stop)
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

1. Valkey layout for the latest values, and how the pricing engine reads it.
2. How Polymarket prices are fetched and stored (`polymarket_observations`), and how they are
   lined up with `espn_observations` by time.
3. How a match is linked to its Polymarket market (`poly_slug` exists; source unknown).
4. NHL: another provider later, or not at all.
5. MLB (and other) sport detail tables: exact columns.

Decided and moved out of this list: ESPN win-probability storage (`espn_observations`), one
table per source, time alignment (`wall_clock` + `ingest_time`), NHL dropped for now, game end
via the status endpoint.

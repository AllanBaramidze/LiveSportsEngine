# Game → Polymarket link

_Written 2026-11-21. How `matches.poly_slug` gets filled, why it works this way, and what to do
when it misbehaves._

## 1. The bug, in one example

Sunday night, 2026-11-22, Vikings at 49ers, 8:20 pm Eastern (01:20 UTC on the 23rd).

| | Slug |
|---|---|
| The old code built | `nfl-min-sf-2026-11-22` → 404 |
| Polymarket uses | `nfl-min-sf-2026-11-23` |

"Use the UTC date for NFL" looks like the fix. It isn't:

| Real game | Real slug | Date in the slug |
|---|---|---|
| NBA, night of 2026-11-21 ET | `nba-por-nyk-2026-11-21` | Eastern day |
| NFL, night of 2026-11-22 ET | `nfl-min-sf-2026-11-23` | UTC day |
| NBA, played 2026-03-18 | `nba-den-mem-2026-01-25` | the day it was *first* scheduled |
| MLB doubleheader, game 1, 2026-07-17 | `mlb-tb-bos-2026-05-09` | the rained-out day, two months earlier |
| MLB doubleheader, game 2, 2026-04-05 | `mlb-chc-cle-2026-04-05-dh2` | has a suffix |

NFL used Eastern dates through 2025 and mostly UTC dates in 2026. **A slug is an id. You look ids
up; you don't calculate them.**

The old formula was wrong for 179 of 5,018 checkable games. In 22 of those (MLB) it produced the
slug of a real but different game, which would have recorded the wrong prices with no error.

## 2. The idea

Ask Polymarket "which games do you have this week?", recognize each one by **who plays and when**,
and copy its slug.

```
BEFORE
  ESPN JSON ─► parser ──(blocking HTTP to Polymarket, once per game)──► guessed slug ─► matches

AFTER
  ESPN JSON ─► parser ─► matches                           (knows nothing about Polymarket)
                            │
  every 10 min              ▼
  polymarket_link ── 1. read the window's games            repositories/matches.py
                  ── 2. fetch the league's events          client/polymarket/polymarket_client.py
                  ── 3. JSON ─► PolymarketGame             client/polymarket/parser.py
                  ── 4. pair games with events             services/game_matching.py
                  ── 5. write only what changed            services/polymarket_link.py
```

`poly_slug` has one writer. That is why a Polymarket outage can no longer break the ESPN schedule,
and a schedule refresh can no longer erase a link.

## 3. The code, in reading order

### Step 1: `schemas/polymarket_game.py`

Four fields: `slug`, `home_team`, `away_team`, `start`. It is what `MatchCreate` is for ESPN: the
shape the rest of the app sees instead of raw JSON. `AwareDatetime` rejects a time with no
timezone, the same bug class as the `ingest_time` bug of 2026-10-07.

### Step 2: `client/polymarket/polymarket_client.py`

`list_game_events(tag_id, start, end)` is HTTP only, like `EspnClient`. Three traps:

- **`include_markets=false`.** Without it two days of NFL is 23 MB. With it, 126 KB.
- **100 per page, whatever you ask for.** `limit=500` returns 100 and no error. The `while` loop
  follows `next_cursor`.
- **All or nothing.** A failed page raises. Half a list would look like "those games aren't listed".

`transport` exists so tests can replace the network without patching.

### Step 3: `client/polymarket/parser.py`

`parse_games(events)` is pure. Props events have the same teams and the same start as their game,
so keeping them would make every game ambiguous. They have a `parentEventId`; games don't.
Home and away come from `ordering`, never from list position (the lesson of ESPN's `homeAway`).

### Step 4: `services/game_matching.py` (the part to understand best)

`match_games(games, markets)` is pure and short.

1. **Same teams, same sides.** `same_team` accepts the full name or the end of it, because
   Polymarket says "Knicks" for NBA and "Minnesota Vikings" for NFL. The space in
   `" " + name` stops "Hornets" matching "nets".
2. **Within 12 h = a candidate.** Back-to-back games of the same teams are 22+ h apart.
3. **Accept a candidate if it is unambiguous**, in either of two ways:
   - it is the only one within 1 h, for both the game and the event (separates doubleheaders);
   - it is the only candidate at all, for both (tolerates wrong start times on Polymarket).
4. **Otherwise, no link.**

"For both" is the important phrase. A doubleheader where Polymarket lists only one event:

```
          17:00          21:00
games      G1             G2
events     E1             (none)

within 1 h:   G1-E1                  → G1 gets E1
candidates:   G1-E1, G2-E1           → E1 has two suitors, so this rule gives nothing
result:       G1 → E1, G2 → no link
```

Checking only "does G2 have one candidate?" would give G2 the wrong game's prices.

### Step 5: `services/polymarket_link.py`

- `plan_links` is pure: it decides what changes.
  - Matched: set the slug, and take it from any other row holding it (a makeup game inherits the
    postponed game's event).
  - Not matched: **keep** what is there. An event can be missing for a minute, and erasing would
    stop the price poller mid-game.
  - `repair=True` (manual command only): clear what can't be confirmed.
- `link_league` does the I/O: read, close the session, fetch, then write in one transaction. It
  reads games 24 h beyond the window, because a game it can't see can't compete for an event.
- `link_games` runs the leagues together with `return_exceptions=True`, like `ingest_days`.

### Step 6: the small edits

| File | Change | Why |
|---|---|---|
| `client/espn/parser.py` | slug and `eastern_date` removed | it is documented as pure, and was making HTTP calls |
| `schemas/match.py` | `poly_slug` removed | ESPN doesn't know it |
| `repositories/matches.py` | upsert no longer writes `poly_slug` | one writer |
| `repositories/matches.py` | upsert drops a repeated `espn_id` | ESPN listed an MLB game on two days, and Postgres rejects the whole league's upsert when that happens |
| `repositories/matches.py` | `list_between`, `list_by_slugs`, `set_poly_slug` | `list_matches` stops at 50 rows; a week of NBA is more |
| `main.py` | fourth loop, every 10 min | late listings and outages heal by themselves |
| `main.py` | `schedule_ready` event | on an empty database, linking would run before any games existed |
| `main.py` | `warned` set | one warning per unlinked game, not 144 a day |
| `polymarket_utils.py`, its test script | deleted | replaced |

No migration: the column already existed.

## 4. When something looks wrong

Start with the dry run. It writes nothing:

```bash
uv run python -m src.services.polymarket_link 2026-11-21 2026-11-28
```

| Symptom | Likely cause | What to do |
|---|---|---|
| `no Polymarket link` for one game | not listed yet, TBD teams, or an exhibition | nothing; it retries every 10 min |
| One game stays unlinked but is on the site | two events for that game, or a start more than 12 h off | look at both; don't widen `MAX_GAP` to fix one game |
| A whole league unlinked, no errors | the team-name format or the tag changed | compare `teams[].name` with `matches.home_team`; check `primaryTagId` at `/sports` |
| `Polymarket link failed` | outage, 429, or a changed response shape | existing links are untouched; it retries |
| Old rows have bad slugs | written by the old formula | run the command with `--apply` |
| Adding a league | | add it to `LEAGUE_TAGS`; a test fails if you forget |

Rules to keep:

1. Never build or parse a slug.
2. Never write `poly_slug` outside `polymarket_link.py`.
3. Never make the matcher guess between two candidates.
4. Before changing `CLOSE_GAP` or `MAX_GAP`, read the doubleheader and back-to-back tests.

## 5. Tests

```bash
uv run python -m unittest discover -s backend/tests -t backend
```

| File | Protects |
|---|---|
| `test_game_matching.py` | the rules, on real payloads of every case in section 1 |
| `test_polymarket_parser.py` | child events, home/away, malformed events |
| `test_polymarket_client.py` | query, pagination, errors |
| `test_polymarket_link.py` | what gets set, kept, moved, cleared |
| `test_espn_parser.py` | the ESPN parser stays offline |
| `test_main_linking.py` | loop order, warnings |
| `test_link_postgres.py` | the real SQL (skipped unless `TEST_DATABASE_URL` is set) |

They can't reach your dev database: `tests/__init__.py` overrides `DATABASE_URL`. For the Postgres
tests, create a database once, then set `TEST_DATABASE_URL` to your URL with that database name:

```bash
docker compose exec db createdb -U postgres livesports_test
```

The older `src/**/tests/test_*.py` files are manual scripts and are not part of this suite.

## 6. Known limits

- A game with two identical events stays unlinked (6 games in the seasons checked).
- A link means "this is the event". It doesn't promise a moneyline market or an open order book;
  Phase 2 has to handle both.
- Team names must be equal or a suffix. A rename on one side shows up as unlinked games, never as
  wrong links.
- The rules were measured on NFL and NBA 2025-26 and 2026-27 so far, and MLB 2026.

## 7. Check yourself

1. Why does the matcher need games from outside the window it is linking?
2. Why does an unmatched game keep its slug in the loop but lose it in `--apply`?
3. What breaks if `poly_slug` is put back into the upsert's `set_`?

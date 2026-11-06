"""Entry point: runs the ESPN polling loops until stopped.

Start it from the repo root with `uv run python -m src.main` (Postgres and Valkey must be up).
Three independent loops run side by side. They share no variables; they hand work over through
the `status` column of `matches` (`pre` -> `in` -> `post`):

* daily schedule: add the next 7 days of games as `pre`;
* pre-game check: flip games that have started from `pre` to `in`;
* in-game poll: save win-probability readings for `in` games and flip finished ones to `post`.

This module decides *when* things run. What each step does lives in `services/espn_ingest.py`.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from functools import partial
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from glide import GlideClient

from src.database.database import SessionLocal, engine
from src.database.repositories import matches
from src.database.valkey import create_valkey
from src.services.espn_ingest import (
    date_range,
    ingest_days,
    poll_in_game,
    refresh_statuses,
)

# Seconds to wait between runs of each loop (the wait starts after a run finishes).
POLL_ONCE_DAY = 86400  # daily schedule: 24 h
POLL_SECONDS_INGAME = 10  # in-game poll
POLL_PREGAME = 60  # pre-game check
# ESPN's `dates=` follows the US Eastern calendar, so "today" must too,
# whatever timezone this machine (or a future server) is in.
ESPN_TZ = ZoneInfo("America/New_York")

log = logging.getLogger(__name__)


async def run_once_daily() -> None:
    """Upsert the schedule for today and the next 6 days (7 days, US Eastern).

    The whole window is re-fetched on every run rather than only the newest day, so changed
    start times and new `poly_slug` values reach games already stored. Failures are logged per
    league; one league failing doesn't stop the others.
    """

    today = datetime.now(ESPN_TZ).date()  # is today's date
    week = date_range(today, today + timedelta(days=6))  # marks the 7-day gap

    results = await ingest_days(week)
    for league, result in results.items():
        if isinstance(result, BaseException):
            log.error("[%s] ingest failed: %r", league, result)
        else:
            log.info("[%s] upserted %d games", league, result)


async def query_pre() -> None:
    """Find `pre` games that are about to start (or just have) and refresh their state.

    A game is due from 1 minute before its start until 1 hour after it. The database session
    is closed before ESPN is called, so no connection is held open during the network requests.
    A game ESPN reports as `in` is saved as `in`, which hands it to the in-game poll.
    """
    log.info("Querying pre games")
    now = datetime.now(ESPN_TZ)
    async with SessionLocal() as session:
        games = await matches.list_due_pregame(
            session, now=now, lead=timedelta(minutes=1), max_overdue=timedelta(hours=1))
    if not games:
        log.info("No games found")
        return

    changes = await refresh_statuses(games)
    for espn_id, result in changes.items():
        if isinstance(result, BaseException):
            log.error("[%s] status check failed: %r", espn_id, result)
        else:
            log.info("[%s] stats -> %s", espn_id, result)


async def query_ingame(valkey: GlideClient) -> None:
    """Poll every live game and save its new or edited win-probability readings.

    Args:
        valkey: Connected Valkey client; holds each game's last reading count.
    """
    log.info("Querying ingame games")
    async with SessionLocal() as session:
        games = await matches.list_in_progress(session)
    if not games:
        log.info("No games found")
        return

    results = await poll_in_game(games, valkey)

    for espn_id, result in results.items():
        if isinstance(result, BaseException):
            log.error("[%s] in-game poll failed: %r", espn_id, result)
            continue
        log.info("[%s] %d new rows, count %d", espn_id, result["new_rows"], result["count"])
        if result["state"] == "post":
            log.info("[%s] game over -> post", espn_id)



async def every(seconds: int, name: str, job: Callable[[], Awaitable[None]]) -> None:
    """Run `job` forever: run it, wait `seconds`, repeat.

    The first run happens immediately. An exception inside `job` is logged and the loop carries
    on, so one bad run never kills the poller. Because the wait begins after the job finishes,
    the real period is `seconds` plus the job's own running time.

    Args:
        seconds: Wait between the end of one run and the start of the next.
        name: Label for the loop (currently unused in log messages).
        job: Zero-argument coroutine function; use `functools.partial` to bind arguments.
    """
    while True:
        try:
            await job()
        except Exception:
            log.exception("Exception occurred")
        await asyncio.sleep(seconds)


async def main() -> None:
    """Connect to Valkey, run the three loops together, and clean up on exit.

    The loops run inside an `asyncio.TaskGroup`: if one raises an unhandled error the others
    are cancelled too. The Valkey client and the database engine are always closed afterwards.
    """
    log.info("Daily schedule every: %ds, pre-game check every %ds", POLL_ONCE_DAY, POLL_PREGAME)
    valkey = await create_valkey()
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(every(POLL_ONCE_DAY, "daily schedule", run_once_daily))
            tg.create_task(every(POLL_PREGAME, "pregame check", query_pre))
            tg.create_task(every(POLL_SECONDS_INGAME, "ingame check", partial(query_ingame, valkey)))
    finally:
        await valkey.close()
        await engine.dispose()

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)  # hide a log line per request
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Stopped")

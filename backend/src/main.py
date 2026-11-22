"""Entry point: runs the ESPN polling loops until stopped.

Start it from the repo root with `uv run python -m src.main` (Postgres and Valkey must be up).
Four independent loops run side by side. They hand work over through `matches`: the `status`
column (`pre` -> `in` -> `post`) and, for Polymarket, `poly_slug`. The only shared variable is
an event that holds linking back until the first schedule run has finished:

* daily schedule: add the next 7 days of games as `pre`;
* pre-game check: flip games that have started from `pre` to `in`;
* in-game poll: save win-probability readings for `in` games and flip finished ones to `post`;
* Polymarket link: find each live or upcoming game's Polymarket event and save its slug.

This module decides *when* things run. What each step does lives in `services/espn_ingest.py`
and `services/polymarket_link.py`.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from functools import partial
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
from src.services.polymarket_link import link_upcoming

# Seconds to wait between runs of each loop (the wait starts after a run finishes).
POLL_ONCE_DAY = 86400  # daily schedule: 24 h
POLL_SECONDS_INGAME = 10  # in-game poll
POLL_PREGAME = 60  # pre-game check
POLL_LINKS = 600  # Polymarket link: picks up late listings and retries after an outage
# ESPN's `dates=` follows the US Eastern calendar, so "today" must too,
# whatever timezone this machine (or a future server) is in.
ESPN_TZ = ZoneInfo("America/New_York")

log = logging.getLogger(__name__)


async def run_once_daily(schedule_ready: asyncio.Event) -> None:
    """Upsert the schedule for today and the next 6 days (7 days, US Eastern).

    The whole window is re-fetched on every run rather than only the newest day, so changed
    start times reach games already stored. Failures are logged per league; one league failing
    doesn't stop the others.

    Args:
        schedule_ready: Set when the run ends, even if it failed, to let linking start.
    """

    today = datetime.now(ESPN_TZ).date()  # is today's date
    week = date_range(today, today + timedelta(days=6))  # marks the 7-day gap

    try:
        results = await ingest_days(week)
    finally:
        schedule_ready.set()  # also on failure: games already stored can still be linked
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



async def query_links(schedule_ready: asyncio.Event, warned: set[str]) -> None:
    """Link live and upcoming games to Polymarket, and warn about games close to starting without one.

    Args:
        schedule_ready: Waited on, so a fresh database has games before the first run.
        warned: Games already warned about, so each is logged once and not every 10 minutes.
    """
    await schedule_ready.wait()
    results = await link_upcoming()
    soon = datetime.now(UTC) + timedelta(days=1)
    for league, result in results.items():
        if isinstance(result, BaseException):
            log.error("[%s] Polymarket link failed: %r", league, result)
            continue
        if result.changes:
            log.info("[%s] %d Polymarket links changed", league, len(result.changes))
        for game in result.unlinked:
            if game.status != "post" and game.date <= soon and game.espn_id not in warned:
                warned.add(game.espn_id)
                log.warning("[%s] no Polymarket link: %s", game.espn_id, game.matchup)


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
    """Connect to Valkey, run the four loops together, and clean up on exit.

    The loops run inside an `asyncio.TaskGroup`: if one raises an unhandled error the others
    are cancelled too. The Valkey client and the database engine are always closed afterwards.
    """
    log.info("Daily schedule every: %ds, pre-game check every %ds", POLL_ONCE_DAY, POLL_PREGAME)
    valkey = await create_valkey()
    schedule_ready = asyncio.Event()
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(every(POLL_ONCE_DAY, "daily schedule", partial(run_once_daily, schedule_ready)))
            tg.create_task(every(POLL_PREGAME, "pregame check", query_pre))
            tg.create_task(every(POLL_SECONDS_INGAME, "ingame check", partial(query_ingame, valkey)))
            tg.create_task(every(POLL_LINKS, "polymarket link", partial(query_links, schedule_ready, set())))
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

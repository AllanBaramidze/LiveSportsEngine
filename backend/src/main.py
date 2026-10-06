"""The main entry point for running the app."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

from src.database.database import SessionLocal, engine
from src.database.repositories import matches
from src.services.espn_ingest import date_range, ingest_days, refresh_statuses

POLL_ONCE_DAY = 86400
POLL_SECONDS_INGAME = 30
POLL_PREGAME = 1800
# ESPN's `dates=` follows the US Eastern calendar, so "today" must too,
# whatever timezone this machine (or a future server) is in.
ESPN_TZ = ZoneInfo("America/New_York")

log = logging.getLogger(__name__)


async def run_once_daily() -> None:
    """this runs once a day to insert the schedule of games 8 days ahead and re-runs this window"""

    today = datetime.now(ESPN_TZ).date()  # is today's date
    week = date_range(today, today + timedelta(days=6))  # marks the 7-day gap

    results = await ingest_days(week)
    for league, result in results.items():
        if isinstance(result, BaseException):
            log.error("[%s] ingest failed: %r", league, result)
        else:
            log.info("[%s] upserted %d games", league, result)


async def query_pre() -> None:
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



async def every(seconds: int, name: str, job: Callable[[], Awaitable[None]]) -> None:
    while True:
        try:
            await job()
        except Exception:
            log.exception("Exception occurred")
        await asyncio.sleep(seconds)


async def main() -> None:
    log.info("Daily schedule every: %ds, pre-game check every %ds", POLL_ONCE_DAY, POLL_PREGAME)
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(every(POLL_ONCE_DAY, "daily schedule", run_once_daily))
            tg.create_task(every(POLL_PREGAME, "daily schedule", query_pre))
    finally:
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

"""The main entry point for running the app."""

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.client.espn.espn_client import EspnClient
from src.database.repositories import matches
from src.database.database import engine, SessionLocal
from src.services.espn_ingest import date_range, ingest_days

POLL_ONCE_DAY = 86400
POLL_SECONDS_INGAME = 30
POLL_DAILY = 1800
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

    today = datetime.now(ESPN_TZ)
    async with SessionLocal() as session:
        games = await matches.list_due_pregame(
            session, now=today, lead=timedelta(minutes=1), max_overdue=timedelta(hours=1))
        async with EspnClient() as espn:
            for game in games:
                #TODO data = await espn.get_match_status(game.sport, game.league, game.espn_id)




async def main() -> None:
    log.info("Polling schedule every: %ds", POLL_ONCE_DAY)
    try:
        while True:
            try:
                await run_once_daily()
            except Exception:
                log.exception("Exception occurred")
            await asyncio.sleep(POLL_ONCE_DAY)
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

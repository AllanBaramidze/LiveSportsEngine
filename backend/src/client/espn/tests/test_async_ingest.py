"""Run a one-off ESPN ingest for a date range and report what got stored.

Run from backend/ (after `alembic upgrade head`):
    python -m src.client.espn.tests.test_async_ingest
"""

import asyncio
from datetime import date

from src.database.database import SessionLocal, engine
from src.database.repositories import matches
from src.services.espn_ingest import date_range, ingest_days


async def main() -> None:
    results = await ingest_days(date_range(date(2026, 9, 27), date(2026, 10, 5)))
    for league, result in results.items():
        if isinstance(result, BaseException):
            print(f"[{league}] failed: {result!r}")
        else:
            print(f"[{league}] upserted {result} games")

    async with SessionLocal() as session:
        print(f"\nIn the database: {await matches.count_by_league(session)}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

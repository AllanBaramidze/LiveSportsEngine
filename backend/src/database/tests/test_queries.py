"""Examples of reading the `matches` table through the repository.

Run from backend/ (after the ingest script so there's data):
    python -m src.database.tests.test_queries
"""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from src.database.database import SessionLocal, engine
from src.database.models import Match
from src.database.repositories import matches


def show(title: str, rows: Sequence[Match]) -> None:
    print(f"\n== {title} ({len(rows)})")
    for m in rows:
        print(f"  {m.date:%a %b %d %H:%M} UTC  [{m.league}]  {m.matchup}")


async def main() -> None:
    async with SessionLocal() as session:
        # 1. Filter + limit
        show(
            "first 5 NFL games",
            await matches.list_matches(session, league="nfl", limit=5),
        )

        # 2. Date window: everything starting in the next 24 hours
        now = datetime.now(UTC)
        upcoming = await matches.list_matches(
            session, start=now, end=now + timedelta(days=1)
        )
        show("next 24 hours", upcoming)

        # 3. Partial, case-insensitive text search
        show("games with 'chiefs'", await matches.search_by_team(session, "chiefs"))

        # 4. One row by its natural key (None if it isn't there)
        print(
            f"\n== lookup 401872952: {await matches.get_by_espn_id(session, '401872952')}"
        )

        # 5. Aggregate
        print(f"\n== count by league: {await matches.count_by_league(session)}")

        # 6. Raw SQL escape hatch, e.g. for a query you worked out in psql first
        result = await session.execute(
            text("SELECT league, min(date), max(date) FROM matches GROUP BY league")
        )
        print("\n== raw SQL: date span per league")
        for league, first, last in result:
            print(f"  {league}: {first:%b %d} -> {last:%b %d}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

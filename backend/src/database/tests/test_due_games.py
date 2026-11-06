"""Manual script (not an automated test): try `list_due_pregame` against a pretend clock.

Pretends it is 4:26 pm Eastern on 2026-10-04 (lead 10 min, max overdue 3 h) and prints the
`pre` games that would be due. The result depends on what is in your `matches` table.

Run from the repo root (Postgres must be up):
    uv run python -m src.database.tests.test_due_games
"""

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.database.database import SessionLocal, engine
from src.database.repositories import matches

ET = ZoneInfo('America/New_York')

async def main() -> None:
    now = datetime(2026,10, 4, 16, 26, tzinfo=ET)
    async with SessionLocal() as session:
        games = await matches.list_due_pregame(
            session, now=now, lead=timedelta(minutes=10), max_overdue=timedelta(hours=3))
        print(f"{len(games)} due")
        for game in games:
            print(game.date.astimezone(ET), game.matchup)
            print(game.espn_id, game.league, game.sport)
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
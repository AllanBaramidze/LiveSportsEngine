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
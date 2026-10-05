"""Orchestrates an ESPN ingest: fetch -> parse -> store.

This is the only layer that knows about both ESPN and the database. It owns the
transaction (the commit), which keeps the client, parser and repository single-purpose.
"""

import asyncio
from collections.abc import Sequence
from datetime import date, timedelta

from src.client.espn.espn_client import EspnClient
from src.client.espn.parser import parse_scoreboard
from src.database.database import SessionLocal
from src.database.repositories import matches
from src.schemas.match import MatchCreate

LEAGUES = [("football", "nfl"), ("baseball", "mlb"), ("hockey", "nhl")]


def date_range(start: date, end: date) -> list[date]:
    """Every day from start to end, inclusive."""
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]

async def fetch_league(espn: EspnClient, sport: str, league: str, days: Sequence[date]
                       ) -> list[MatchCreate]:
    payloads = await asyncio.gather(
        *(espn.get_scoreboard(sport, league, day) for day in days)
    )
    return [game for payload in payloads for game in parse_scoreboard(payload, league, sport)]


async def ingest_league(espn: EspnClient, sport: str, league: str, days: Sequence[date]) -> int:
    games = await fetch_league(espn, sport, league, days)
    # Each concurrent task opens its own session: an AsyncSession must never be
    # shared between tasks running at the same time.
    async with SessionLocal() as session:
        count = await matches.upsert_matches(session, games)
        await session.commit()
    return count


async def ingest_days(days: Sequence[date], leagues=None) -> dict[str, int | BaseException]:
    """Ingest every league concurrently. One league failing doesn't stop the others."""
    if leagues is None:
        leagues = LEAGUES
    async with EspnClient() as espn:
        results = await asyncio.gather(
            *(ingest_league(espn, sport, league, days) for sport, league in leagues),
            return_exceptions=True,
        )
    return {
        league: result for (_, league), result in zip(leagues, results, strict=True)
    }



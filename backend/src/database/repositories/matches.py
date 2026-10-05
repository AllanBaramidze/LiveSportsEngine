"""All SQL for the `matches` table lives here.

Every function takes the session as an argument and never commits: the caller
decides where a transaction starts and ends, so several calls can be grouped
into one all-or-nothing commit.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Match
from src.schemas.match import MatchCreate

# --- writes 


async def upsert_matches(session: AsyncSession, games: Sequence[MatchCreate]) -> int:
    """Insert games, or update them if espn_id already exists. Safe to re-run."""
    if not games:
        return 0

    stmt = insert(Match).values([game.model_dump() for game in games])
    stmt = stmt.on_conflict_do_update(
        index_elements=[Match.espn_id],
        # poly_slug is left out on purpose so re-ingesting never wipes it.
        set_={
            "matchup": stmt.excluded.matchup,
            "status": stmt.excluded.status,
            "home_team": stmt.excluded.home_team,
            "home_score": stmt.excluded.home_score,
            "away_team": stmt.excluded.away_team,
            "away_score": stmt.excluded.away_score,
            "date": stmt.excluded.date,
        },
    )
    await session.execute(stmt)
    return len(games)

 # TODO async def update_matches(session: AsyncSession, espn_id: str, games: Sequence[MatchCreate]) -> int:

# --- reads 


async def get_by_espn_id(session: AsyncSession, espn_id: str) -> Match | None:
    return await session.scalar(select(Match).where(Match.espn_id == espn_id))


async def list_matches(session: AsyncSession,*,
    league: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 50,
) -> Sequence[Match]:
    """Games ordered by start time, optionally filtered. `start` is inclusive, `end` exclusive."""
    stmt = select(Match).order_by(Match.date).limit(limit)
    if league is not None:
        stmt = stmt.where(Match.league == league)
    if start is not None:
        stmt = stmt.where(Match.date >= start)
    if end is not None:
        stmt = stmt.where(Match.date < end)
    result = await session.scalars(stmt)
    return result.all()

async def list_due_pregame(session: AsyncSession, *,
                           now: datetime,
                           lead: timedelta,
                           max_overdue: timedelta) -> Sequence[Match]:
    """Games still marked 'pre' that start within 'lead' of 'now'"""
    stmt = (
        select(Match)
        .where(Match.status == "pre")
        .where(Match.date <= now + lead) # Starting Soon, or already started
        .where(Match.date >= now - max_overdue) # check back
        .order_by(Match.date)
    )
    result = await session.scalars(stmt)
    return result.all()



async def search_by_team(
    session: AsyncSession, team: str, limit: int = 20
) -> Sequence[Match]:
    """Case-insensitive partial match on either team, e.g. "chiefs"."""
    pattern = f"%{team}%"
    stmt = (
        select(Match)
        .where(or_(Match.home_team.ilike(pattern), Match.away_team.ilike(pattern)))
        .order_by(Match.date)
        .limit(limit)
    )
    result = await session.scalars(stmt)
    return result.all()


async def count_by_league(session: AsyncSession) -> dict[str, int]:
    stmt = (
        select(Match.league, func.count()).group_by(Match.league).order_by(Match.league)
    )
    result = await session.execute(stmt)
    return dict(result.tuples().all())

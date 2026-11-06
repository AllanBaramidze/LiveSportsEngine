"""All SQL for the `matches` table lives here.

Every function takes the session as an argument and never commits: the caller
decides where a transaction starts and ends, so several calls can be grouped
into one all-or-nothing commit.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Match
from src.schemas.match import MatchCreate

# --- writes 


async def upsert_matches(session: AsyncSession, games: Sequence[MatchCreate]) -> int:
    """Insert games, or update them if their `espn_id` already exists. Safe to re-run.

    On a conflict every field except `espn_id` is overwritten with the incoming value,
    including `poly_slug`, so each ingest refreshes start times, scores and the slug.

    Args:
        session: Open session; the caller commits.
        games: Games to store.

    Returns:
        How many games were sent (inserted or updated), not only the new ones.
    """
    if not games:
        return 0

    stmt = insert(Match).values([game.model_dump() for game in games])
    stmt = stmt.on_conflict_do_update(
        index_elements=[Match.espn_id],
        # Columns refreshed when the game already exists (everything but the key).
        set_={
            "matchup": stmt.excluded.matchup,
            "status": stmt.excluded.status,
            "home_team": stmt.excluded.home_team,
            "home_score": stmt.excluded.home_score,
            "away_team": stmt.excluded.away_team,
            "away_score": stmt.excluded.away_score,
            "date": stmt.excluded.date,
            "poly_slug": stmt.excluded.poly_slug,
        },
    )
    await session.execute(stmt)
    return len(games)

async def update_status(session: AsyncSession, espn_id: str, status: str) -> None:
    """Set one game's status (`pre`, `in` or `post`). The caller commits."""
    stmt = update(Match).where(Match.espn_id == espn_id).values(status=status)
    await session.execute(stmt)

async def update_score(session: AsyncSession, espn_id: str, home_score: int, away_score: int) -> None:
    """Set one game's score. Scores are stored as text, so the ints are converted. The caller commits."""
    stmt = update(Match).where(Match.espn_id == espn_id).values(home_score=str(home_score), away_score=str(away_score))
    await session.execute(stmt)


# --- reads 


async def get_by_espn_id(session: AsyncSession, espn_id: str) -> Match | None:
    """Return the game with this ESPN id, or `None` if it isn't stored."""
    return await session.scalar(select(Match).where(Match.espn_id == espn_id))


async def list_matches(session: AsyncSession,*,
    league: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 50,
) -> Sequence[Match]:
    """Games ordered by start time, optionally filtered.

    Args:
        session: Open session.
        league: Only this league (e.g. `nba`); all leagues if `None`.
        start: Earliest start time, inclusive.
        end: Latest start time, exclusive.
        limit: Maximum number of games returned.
    """
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
    """Games still marked `pre` that are due for a status check, earliest first.

    A game is due when it starts at or before `now + lead` (about to start, or already started)
    and no earlier than `now - max_overdue` (so a game ESPN never flips is eventually dropped).
    This is a filter only: how often it runs is decided in `main.py`.

    Args:
        session: Open session.
        now: The current time (timezone-aware).
        lead: How long before the start a game counts as due.
        max_overdue: How long after the scheduled start a `pre` game keeps being checked.
    """
    stmt = (
        select(Match)
        .where(Match.status == "pre")
        .where(Match.date <= now + lead) # Starting Soon, or already started
        .where(Match.date >= now - max_overdue) # check back
        .order_by(Match.date)
    )
    result = await session.scalars(stmt)
    return result.all()


async def list_in_progress(session: AsyncSession):
    """Live games (`status = in`), earliest start first. These are the games the in-game poller covers."""
    stmt = (
        select(Match)
        .where(Match.status == "in")
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
    """Number of stored games per league, e.g. `{"nba": 120, "nfl": 45}`."""
    stmt = (
        select(Match.league, func.count()).group_by(Match.league).order_by(Match.league)
    )
    result = await session.execute(stmt)
    return dict(result.tuples().all())

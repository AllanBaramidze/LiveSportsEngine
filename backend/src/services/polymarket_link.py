"""Fill `matches.poly_slug`: fetch Polymarket's games -> match -> store.

`poly_slug` is written only here. The ESPN ingest never touches it, so a Polymarket outage
can't break the schedule and a schedule refresh can't erase a link.

`main.py` calls `link_upcoming` every few minutes. To check or repair a range of days by hand:

    uv run python -m src.services.polymarket_link 2026-10-07 2026-11-11            # only prints
    uv run python -m src.services.polymarket_link 2026-10-07 2026-11-11 --apply    # writes
"""

import argparse
import asyncio
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from src.client.polymarket.parser import parse_games
from src.client.polymarket.polymarket_client import PolymarketClient
from src.database.database import SessionLocal, engine
from src.database.models import Match
from src.database.repositories import matches
from src.services.game_matching import MAX_GAP, match_games

# Polymarket's tag for each league. Tags outlast seasons; series ids (nfl-2026) don't.
# From https://gamma-api.polymarket.com/sports, field `primaryTagId`.
LEAGUE_TAGS = {"nfl": 450, "nba": 745, "mlb": 100381}

EASTERN = ZoneInfo("America/New_York")
# What the recurring job covers: yesterday (games still live) to just past the 7-day schedule.
LOOK_BACK = timedelta(days=1)
LOOK_AHEAD = timedelta(days=8)


@dataclass(frozen=True)
class LinkReport:
    """What linking one league did (or, in a dry run, would do).

    Attributes:
        games: The games in the window.
        changes: `{espn_id: new slug}`; `None` means the link was cleared. May include a game
            outside the window that had to give up a slug.
    """

    games: list[Match]
    changes: dict[str, str | None]

    @property
    def unlinked(self) -> list[Match]:
        """Games in the window that have no link once `changes` is applied."""
        return [g for g in self.games if not self.changes.get(g.espn_id, g.poly_slug)]


def plan_links(
    games: Sequence[Match],
    matched: Mapping[str, str],
    holders: Collection[Match],
    start: datetime,
    end: datetime,
    *,
    listed: bool,
    repair: bool,
) -> LinkReport:
    """Work out which rows must change. Pure.

    * A matched game gets its slug, and any other row holding that slug gives it up.
    * An unmatched game keeps what it has, because an event can be missing for a moment.
    * With `repair`, an unmatched game's slug is cleared, unless nothing at all was listed.

    Args:
        games: The window's games and their neighbours; only those in the window are linked.
        matched: Result of `match_games`.
        holders: Rows that currently hold any of the matched slugs, whatever their date.
        start: Window start, inclusive.
        end: Window end, exclusive.
        listed: Whether Polymarket listed any game at all.
        repair: Clear links that could not be confirmed.
    """
    in_window = [g for g in games if start <= g.date < end]
    links = {g.espn_id: matched[g.espn_id] for g in in_window if g.espn_id in matched}
    owner = {slug: espn_id for espn_id, slug in links.items()}

    changes: dict[str, str | None] = {}
    for holder in holders:
        if holder.poly_slug in owner and owner[holder.poly_slug] != holder.espn_id:
            changes[holder.espn_id] = None
    for game in in_window:
        if game.espn_id in links:
            if game.poly_slug != links[game.espn_id]:
                changes[game.espn_id] = links[game.espn_id]
        elif repair and listed and game.poly_slug:
            changes[game.espn_id] = None
    return LinkReport(in_window, changes)


async def link_league(
    polymarket: PolymarketClient,
    league: str,
    start: datetime,
    end: datetime,
    *,
    repair: bool = False,
    dry_run: bool = False,
) -> LinkReport:
    """Link one league's games in `[start, end)` in one transaction.

    No session is open during the HTTP requests. Events are read `MAX_GAP` beyond the window and
    games twice that, so every game competing for a candidate event is seen.
    """
    async with SessionLocal() as session:
        games = await matches.list_between(session, league, start - 2 * MAX_GAP, end + 2 * MAX_GAP)
    if not any(start <= g.date < end for g in games):
        return LinkReport([], {})  # off-season: nothing to ask Polymarket

    events = await polymarket.list_game_events(LEAGUE_TAGS[league], start - MAX_GAP, end + MAX_GAP)
    markets = parse_games(events)
    matched = match_games(games, markets)

    async with SessionLocal() as session:
        holders = await matches.list_by_slugs(session, matched.values())
        report = plan_links(games, matched, holders, start, end, listed=bool(markets), repair=repair)
        if not dry_run:
            for espn_id, slug in report.changes.items():
                await matches.set_poly_slug(session, espn_id, slug)
            await session.commit()
    return report


async def link_games(
    polymarket: PolymarketClient,
    start: datetime,
    end: datetime,
    *,
    repair: bool = False,
    dry_run: bool = False,
) -> dict[str, LinkReport | BaseException]:
    """Link every league at once. One league failing doesn't stop the others.

    Returns:
        `{league: report}`, or the exception for a league that failed (its links are untouched).
    """
    results = await asyncio.gather(
        *(link_league(polymarket, league, start, end, repair=repair, dry_run=dry_run) for league in LEAGUE_TAGS),
        return_exceptions=True,
    )
    return dict(zip(LEAGUE_TAGS, results, strict=True))


async def link_upcoming() -> dict[str, LinkReport | BaseException]:
    """The recurring job: link live and upcoming games."""
    now = datetime.now(UTC)
    async with PolymarketClient() as polymarket:
        return await link_games(polymarket, now - LOOK_BACK, now + LOOK_AHEAD)


def eastern_window(first: date, last: date) -> tuple[datetime, datetime]:
    """The UTC instants covering whole Eastern days `first` through `last`."""
    start = datetime.combine(first, time(), EASTERN)
    end = datetime.combine(last + timedelta(days=1), time(), EASTERN)
    return start.astimezone(UTC), end.astimezone(UTC)


async def repair_days(first: date, last: date, *, apply: bool) -> int:
    """Command-line repair: print what changes, write only if `apply`. Returns the exit code."""
    start, end = eastern_window(first, last)
    try:
        async with PolymarketClient() as polymarket:
            results = await link_games(polymarket, start, end, repair=True, dry_run=not apply)
    finally:
        await engine.dispose()

    failed = False
    for league, result in results.items():
        if isinstance(result, BaseException):
            print(f"[{league}] FAILED, nothing written: {result!r}")
            failed = True
            continue
        linked = len(result.games) - len(result.unlinked)
        print(f"[{league}] {linked}/{len(result.games)} linked, {len(result.changes)} changes")
        before = {g.espn_id: g.poly_slug for g in result.games}
        for espn_id, slug in result.changes.items():
            print(f"    {espn_id}: {before.get(espn_id, '(outside range)')} -> {slug}")
        for game in result.unlinked:
            print(f"    no link: {game.espn_id} {game.date:%Y-%m-%d %H:%M %Z} {game.matchup}")
    print("Written." if apply else "Dry run: nothing written. Add --apply to write.")
    return int(failed)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description="Check or repair matches.poly_slug for a range of Eastern days.")
    cli.add_argument("first", type=date.fromisoformat, help="first day, YYYY-MM-DD")
    cli.add_argument("last", type=date.fromisoformat, help="last day (included), YYYY-MM-DD")
    cli.add_argument("--apply", action="store_true", help="write the changes")
    args = cli.parse_args()
    if args.last < args.first:
        cli.error("last day is before the first")
    raise SystemExit(asyncio.run(repair_days(args.first, args.last, apply=args.apply)))

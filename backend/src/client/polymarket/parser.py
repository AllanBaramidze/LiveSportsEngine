"""Pure functions that turn raw Polymarket JSON into the app's own types.

No network and no database here, so every function can be tested against a saved JSON file.
"""

from collections.abc import Iterable
from typing import Any

from pydantic import ValidationError

from src.schemas.polymarket_game import PolymarketGame


def parse_games(events: Iterable[dict[str, Any]]) -> list[PolymarketGame]:
    """Keep the events that are games and reduce each to a `PolymarketGame`.

    A game is a top-level event (no `parentEventId`) with a slug, an aware start time, and
    exactly one home and one away team. Props and "first TD scorer" events share the game's
    teams and start time but have a parent, so they are dropped. `gameId` is not required:
    real 2025 NFL games had none.

    Args:
        events: Raw Gamma events.

    Returns:
        One entry per slug. Unusable events are skipped, so one bad event can't hide the others.
    """
    games: dict[str, PolymarketGame] = {}  # by slug: an event can appear on two pages
    for event in events:
        slug, teams = event.get("slug"), event.get("teams")
        if event.get("parentEventId") or not slug or not teams or len(teams) != 2:
            continue
        names = {team.get("ordering"): team.get("name") for team in teams}
        if not names.get("home") or not names.get("away"):
            continue
        try:
            games[slug] = PolymarketGame(
                slug=slug, home_team=names["home"], away_team=names["away"], start=event.get("startTime")
            )
        except ValidationError:  # missing, unreadable or timezone-less start time
            continue
    return list(games.values())

"""Decide which Polymarket event is which game. Pure: no network, no database.

Slugs can't be built from a game's teams and date. Their date is sometimes the Eastern day,
sometimes the UTC day, and for a rescheduled game it is the day the game was *first* planned
(the Nuggets-Grizzlies game of 2026-03-18 is `nba-den-mem-2026-01-25`). So games are recognized
by who plays and when, and the slug is copied from the event that was recognized.

The rules:
    1. Home is the same team and away is the same team.
    2. The starts are within `MAX_GAP` (12 h). Only then is the pair a candidate.
    3. A candidate is accepted if it is the only one within `CLOSE_GAP` (1 h) for both its game
       and its event (this separates doubleheaders), or the only candidate at all for both
       (this tolerates Polymarket start times that are hours off).
    4. Anything else stays unlinked. A missing link is visible; a wrong one poisons the data.
"""

from collections import Counter
from collections.abc import Sequence
from datetime import timedelta

from src.database.models import Match
from src.schemas.polymarket_game import PolymarketGame

# Two games of a doubleheader start 3+ hours apart, so 1 h can't reach both.
CLOSE_GAP = timedelta(hours=1)
# Back-to-back NBA games of the same teams start 22+ hours apart; wrong Polymarket start times
# seen so far are up to about 7 h off.
MAX_GAP = timedelta(hours=12)


def same_team(espn_name: str, polymarket_name: str) -> bool:
    """Whether the names mean the same team: "New York Knicks" is "Knicks" and "New York Knicks".

    The space stops "Charlotte Hornets" from matching "nets".
    """
    if not polymarket_name:
        return False
    return espn_name == polymarket_name or espn_name.endswith(" " + polymarket_name)


def only_choices(pairs: Sequence[tuple[str, str]]) -> dict[str, str]:
    """The (espn_id, slug) pairs in which neither side appears in any other pair."""
    per_game = Counter(espn_id for espn_id, _ in pairs)
    per_event = Counter(slug for _, slug in pairs)
    return {espn_id: slug for espn_id, slug in pairs if per_game[espn_id] == 1 and per_event[slug] == 1}


def match_games(games: Sequence[Match], markets: Sequence[PolymarketGame]) -> dict[str, str]:
    """Pair games with events, one to one.

    Args:
        games: Games of one league. Include neighbours of the games you care about: a game
            that isn't passed in can't stop another game from taking its event.
        markets: That league's Polymarket games.

    Returns:
        `{espn_id: slug}` for the games that could be matched safely.
    """
    close: list[tuple[str, str]] = []
    candidates: list[tuple[str, str]] = []
    for game in games:
        for market in markets:
            gap = abs(game.date - market.start)
            if gap > MAX_GAP:
                continue
            if not same_team(game.home_team, market.home_team) or not same_team(game.away_team, market.away_team):
                continue
            pair = (game.espn_id, market.slug)
            candidates.append(pair)
            if gap <= CLOSE_GAP:
                close.append(pair)
    # These can't disagree: a game with only one candidate has that same one as its close one.
    return only_choices(candidates) | only_choices(close)

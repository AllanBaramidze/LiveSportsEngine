"""Small builders shared by the tests."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.database.models import Match
from src.schemas.polymarket_game import PolymarketGame

FIXTURES = Path(__file__).parent / "fixtures"


def at(text: str) -> datetime:
    """A UTC instant from 'YYYY-MM-DD HH:MM'."""
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


def real_events(*slugs: str) -> list[dict[str, Any]]:
    """Real Gamma events (trimmed to the fields that matter), by slug."""
    events = load("polymarket_events.json")
    return [events[slug] for slug in slugs]


def game(
    espn_id: str, away: str, home: str, start: str, *,
    league: str = "nba", status: str = "pre", slug: str | None = None,
) -> Match:
    return Match(
        espn_id=espn_id, league=league, sport="test", matchup=f"{away} at {home}", status=status,
        home_team=home, home_score="0", away_team=away, away_score="0", date=at(start), poly_slug=slug,
    )


def market(slug: str, away: str, home: str, start: str) -> PolymarketGame:
    return PolymarketGame(slug=slug, away_team=away, home_team=home, start=at(start))

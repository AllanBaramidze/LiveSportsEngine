from datetime import datetime

from pydantic import BaseModel


class MatchCreate(BaseModel):
    """A game as our app understands it, independent of where it came from.

    The ESPN parser produces these and the matches repository stores them,
    so neither side needs to know about the other.
    """

    espn_id: str
    league: str
    sport: str
    matchup: str
    status: str
    home_team: str
    home_score: str
    away_team: str
    away_score: str
    date: datetime

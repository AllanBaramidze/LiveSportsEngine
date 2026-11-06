from datetime import datetime

from pydantic import BaseModel


class MatchCreate(BaseModel):
    """A game as our app understands it, independent of where it came from.

    The ESPN parser produces these and the matches repository stores them,
    so neither side needs to know about the other.

    Attributes:
        espn_id: ESPN event id; the natural key of a game.
        league: Lower-case league code, e.g. `nba`.
        sport: ESPN sport name, e.g. `basketball`. Taken from the request, not from ESPN's JSON.
        matchup: Display name, e.g. "Kansas City Chiefs at Miami Dolphins".
        status: ESPN game state: `pre`, `in` or `post`.
        home_team: Home team display name.
        home_score: Home score as text, exactly as ESPN sends it.
        away_team: Away team display name.
        away_score: Away score as text, exactly as ESPN sends it.
        date: Scheduled start; pydantic parses ESPN's ISO string into an aware datetime.
        poly_slug: Polymarket event slug, `{league}-{away}-{home}-{YYYY-MM-DD}` (Eastern date).
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
    poly_slug: str

from pydantic import AwareDatetime, BaseModel


class PolymarketGame(BaseModel):
    """One Polymarket game event, reduced to what is needed to recognize the game.

    Attributes:
        slug: The event's slug. An opaque id: never build one or read a date out of it.
        home_team: Polymarket's home team name (a nickname for NBA, the full name for NFL and MLB).
        away_team: Polymarket's away team name.
        start: Polymarket's scheduled start. Usually equal to ESPN's, occasionally hours off.
    """

    slug: str
    home_team: str
    away_team: str
    start: AwareDatetime

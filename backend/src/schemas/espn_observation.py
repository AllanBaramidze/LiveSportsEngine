from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class EspnObservationCreate(BaseModel):
    """
    The Structure for the In-game oberservations that get polled
    """

    espn_id: str
    play_id: str
    wall_clock: datetime
    period: int
    clock: str | None
    espn_home_prob: Decimal
    espn_tie_prob: Decimal| None
    espn_away_prob: Decimal
    ingest_time: datetime
    espn_reading_count: int
    home_score: int
    away_score: int
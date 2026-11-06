from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class EspnObservationCreate(BaseModel):
    """One ESPN win-probability reading for one play, ready to be stored.

    The parser produces these and the `espn_observations` repository inserts them.
    It mirrors the table minus the database-generated `id`.

    Attributes:
        espn_id: ESPN event id of the game (matches `Match.espn_id`).
        play_id: ESPN play id; probabilities and plays share the same ids.
        wall_clock: Real-world time the play happened (ESPN `wallclock`).
        period: Quarter, period or inning number.
        clock: In-game clock as displayed, e.g. `14:14`; `None` for sports without one (MLB).
        espn_home_prob: Home win probability, 0 to 1.
        espn_tie_prob: Tie probability, 0 to 1; `None` when ESPN sends none.
        espn_away_prob: Away win probability, 0 to 1.
        ingest_time: When this app received the reading (UTC), not when ESPN produced it.
        espn_reading_count: How many readings ESPN had for the game at that moment.
        home_score: Home score after the play.
        away_score: Away score after the play.
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
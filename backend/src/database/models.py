"""ORM models: one class per Postgres table.

Schema changes are made here and then turned into an Alembic migration
(`alembic revision --autogenerate`); always read the generated file before applying it.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Common base class; its metadata is what Alembic compares the database against."""


class Match(Base):
    """One row per game, created by the daily schedule ingest and kept current by the pollers.

    Attributes:
        id: Internal surrogate key.
        espn_id: ESPN event id; unique, and the key that upserts and foreign keys use.
        sport: ESPN sport name (`basketball`, `football`, `baseball`).
        league: League code (`nba`, `nfl`, `mlb`).
        matchup: Display name, e.g. "Washington Wizards at Charlotte Hornets".
        status: `pre` (not started), `in` (live) or `post` (finished).
        home_team: Home team display name.
        home_score: Latest home score, stored as text because ESPN sends text.
        away_team: Away team display name.
        away_score: Latest away score, stored as text.
        date: Scheduled start time (UTC instant).
        poly_slug: Polymarket event slug used to find this game's market; `None` if unknown.
    """

    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    espn_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    sport: Mapped[str]
    league: Mapped[str] = mapped_column(String(16))
    matchup: Mapped[str] 
    # ESPN's status.type.state: "pre" | "in" | "post". The default fills existing rows.
    status: Mapped[str] = mapped_column(String(8), server_default="pre")
    home_team: Mapped[str] 
    home_score: Mapped[str] = mapped_column(String(16), server_default="0")
    away_team: Mapped[str] 
    away_score: Mapped[str] = mapped_column(String(16), server_default="0")
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    poly_slug: Mapped[str | None]


    def __repr__(self) -> str:
        return f"Match(espn_id={self.espn_id!r}, matchup={self.matchup!r})"

class EspnObservation(Base):
    """One ESPN win-probability reading for one play of a live game.

    Rows are appended by the in-game poller and never updated. A *changed* probability on a
    play ESPN already reported becomes a new row, so the table is the live record of what
    ESPN said and when, including its later corrections.

    Three different times are stored; do not mix them up:
        * `wall_clock`: when the play happened in the real world (from ESPN).
        * `period` + `clock`: where in the game it happened.
        * `ingest_time`: when this app received the reading.

    Attributes:
        id: Surrogate key (not consecutive: ignored inserts still consume sequence values).
        espn_id: The game, a foreign key to `matches.espn_id`.
        play_id: ESPN play id; ESPN keeps one probability per play under the same id.
        wall_clock: Real-world time of the play.
        ingest_time: When this app received the reading (UTC).
        period: Quarter, period or inning number.
        clock: In-game clock text; `None` for sports without one (MLB).
        espn_home_prob: Home win probability, 0 to 1.
        espn_tie_prob: Tie probability, 0 to 1; `None` when ESPN sends none.
        espn_away_prob: Away win probability, 0 to 1.
        espn_reading_count: ESPN's reading count at that poll. A jump of more than 1 between
            stored rows means readings arrived between polls; a drop means ESPN deleted some.
        home_score: Home score after the play.
        away_score: Away score after the play.
    """

    __tablename__ = "espn_observations"

    __table_args__ = (
        # "Same reading" = same game, play and probabilities. NULLS NOT DISTINCT makes two rows
        # with a NULL tie probability count as equal, so repeat polls are rejected as intended.
        UniqueConstraint(
            "espn_id", "play_id", "espn_home_prob", "espn_tie_prob" ,"espn_away_prob",
            name="uq_espn_observations_reading",
            postgresql_nulls_not_distinct=True,
        ),
        # Serves "this game's readings in time order".
        Index("ix_espn_observations_espn_id_wall_clock", "espn_id", "wall_clock"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    espn_id: Mapped[str] = mapped_column(ForeignKey("matches.espn_id"))
    play_id: Mapped[str]
    wall_clock: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingest_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period: Mapped[int]
    clock: Mapped[str | None]
    espn_home_prob: Mapped[Decimal] = mapped_column(Numeric)
    espn_tie_prob: Mapped[Decimal | None] = mapped_column(Numeric)
    espn_away_prob: Mapped[Decimal] = mapped_column(Numeric)
    espn_reading_count: Mapped[int] = mapped_column(Integer)
    home_score: Mapped[int] = mapped_column(Integer)
    away_score: Mapped[int] = mapped_column(Integer)
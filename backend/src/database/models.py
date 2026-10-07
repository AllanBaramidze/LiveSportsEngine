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
    pass


class Match(Base):
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
    __tablename__ = "espn_observations"

    __table_args__ = (
        UniqueConstraint(
            "espn_id", "play_id", "espn_home_prob", "espn_tie_prob" ,"espn_away_prob",
            name="uq_espn_observations_reading",
            postgresql_nulls_not_distinct=True,
        ),
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
from datetime import datetime

from sqlalchemy import DateTime, String
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

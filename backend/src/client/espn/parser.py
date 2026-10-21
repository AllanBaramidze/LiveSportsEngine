from datetime import datetime
from typing import Any

from src.schemas.espn_observation import EspnObservationCreate
from src.schemas.match import MatchCreate


def parse_scoreboard(data: dict[str, Any], league: str, sport: str) -> list[MatchCreate]:
    """Turn a raw ESPN scoreboard payload into MatchCreate objects.

    Pure function (no network, no DB), so it can be tested against a saved JSON file.
    """
    games = []
    for event in data.get("events", []):
        competitors = event["competitions"][0]["competitors"]
        # competitors[0] isn't always home, instead using ESPN's homeAway field.
        teams = {c["homeAway"]: c["team"]["displayName"] for c in competitors}
        sides = {c["homeAway"]: c for c in event["competitions"][0]["competitors"]}
        away, home = sides["away"], sides["home"]
        games.append(
            MatchCreate(
                espn_id=event["id"],
                league=league,
                sport=sport,
                matchup=event["name"],
                status=event["status"]["type"]["state"],
                home_team=teams["home"],
                home_score=home["score"],
                away_team=teams["away"],
                away_score=away["score"],
                date=event["date"],  # pydantic parses ESPN's ISO string into a datetime
            )
        )
    return games


def parse_state(data: dict[str, Any]) -> str:
    """Take ESPN state to check the update"""
    # Pass in some JSON, and with the game ID, update the state
    return data["type"]["state"]


def parse_observations(data: dict[str, Any], espn_id: str, ingest_time: datetime) -> list[EspnObservationCreate]:
    """Pair each reading with its play and build the rows for espn_observations (oldest → newest)."""
    plays_by_id = {play["id"]: play for play in data["plays"]}  # lookup table, built once

    observations = []
    for reading in data["readings"]:  # one reading at a time (oldest → newest)
        play_id = reading["play"]["$ref"].split("/plays/")[1].split("?")[0]
        play = plays_by_id.get(play_id)
        if play is None:  # its play isn't in this poll yet
            continue  # skip it; the next poll retries

        clock_info = play.get("clock")
        clock = clock_info["displayValue"] if clock_info else None

        observations.append(
            EspnObservationCreate(
                espn_id=espn_id,
                play_id=play["id"],
                wall_clock=play["wallclock"],
                period=play["period"]["number"],
                clock=clock,
                espn_home_prob=reading["homeWinPercentage"],
                espn_tie_prob=reading.get("tiePercentage"),
                espn_away_prob=reading["awayWinPercentage"],
                ingest_time=ingest_time,
                espn_reading_count=data["count"],
                home_score=play["homeScore"],
                away_score=play["awayScore"],
            )
        )
    return observations
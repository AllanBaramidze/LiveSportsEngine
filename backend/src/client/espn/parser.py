from typing import Any

from src.schemas.match import MatchCreate


def parse_scoreboard(data: dict[str, Any], league: str, sport: str) -> list[MatchCreate]:
    """Turn a raw ESPN scoreboard payload into MatchCreate objects.

    Pure function (no network, no DB), so it can be tested against a saved JSON file.
    """
    games = []
    for event in data.get("events", []):
        competitors = event["competitions"][0]["competitors"]
        # competitors[0] isn't always home, so use ESPN's homeAway field.
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

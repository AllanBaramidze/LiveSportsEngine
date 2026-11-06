"""Pure functions that turn raw ESPN JSON into the app's own types.

No network and no database here, so every function can be tested against a saved JSON file.
The client fetches, these functions interpret, and the service decides what to store.
"""

from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

from src.client.polymarket.polymarket_utils import get_match_abbr
from src.schemas.espn_observation import EspnObservationCreate
from src.schemas.match import MatchCreate

EASTERN = ZoneInfo("America/New_York")

def eastern_date(espn_date: str) -> str:
    """Convert ESPN's UTC start time to the US Eastern calendar day (`YYYY-MM-DD`).

    Polymarket slugs use the Eastern date, which can differ from the UTC date for night
    games: `2026-10-22T02:00Z` is still 21 October in Eastern time.

    Args:
        espn_date: ISO timestamp from ESPN, e.g. `2026-10-22T02:00Z`.
    """
    utc = datetime.fromisoformat(espn_date) # "2026-10-22T02:00Z" → 2026-10-22 02:00+00:00
    eastern = utc.astimezone(EASTERN) # → 2026-10-21 22:00-04:00
    return eastern.date().isoformat() # → "2026-10-21"

def parse_scoreboard(data: dict[str, Any], league: str, sport: str) -> list[MatchCreate]:
    """Turn a raw ESPN scoreboard payload into `MatchCreate` objects, one per event.

    Home and away are read from each competitor's `homeAway` field, because the order of
    `competitors` is not reliable. `sport` and `league` are not in ESPN's JSON in a usable
    form, so the caller passes them in.

    Args:
        data: Scoreboard JSON for one league and one day.
        league: League code, e.g. `nba`.
        sport: ESPN sport name, e.g. `basketball`.

    Returns:
        The games in ESPN's order; empty if the day has no events.
    """
    games = []
    for event in data.get("events", []):
        competitors = event["competitions"][0]["competitors"]
        # competitors[0] isn't always home, instead using ESPN's homeAway field.
        teams = {c["homeAway"]: c["team"]["displayName"] for c in competitors}
        sides = {c["homeAway"]: c for c in event["competitions"][0]["competitors"]}
        away, home = sides["away"], sides["home"]
        poly_slug = get_match_abbr(teams["home"], teams["away"], league, eastern_date(event["date"]))
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
                poly_slug=poly_slug,
            )
        )
    return games


def parse_state(data: dict[str, Any]) -> str:
    """Read a game's state from ESPN's core `/status` JSON.

    Args:
        data: Response of the core `/status` endpoint (also `status` in `get_game_info`).

    Returns:
        `"pre"` (not started), `"in"` (live) or `"post"` (finished).
    """
    return data["type"]["state"]


def parse_observations(data: dict[str, Any], espn_id: str, ingest_time: datetime) -> list[EspnObservationCreate]:
    """Pair each reading with its play and build the rows for `espn_observations`.

    ESPN keeps two lists per game, win-probability readings and plays, matched by play id.
    The reading carries the probabilities; the play carries the time, period, clock and score.

    Args:
        data: Result of `EspnClient.get_game_info` (`readings`, `plays` and `count` are used).
        espn_id: ESPN event id of the game.
        ingest_time: When the data was received (UTC); set by the caller, since it is not in
            ESPN's JSON.

    Returns:
        One observation per reading, in the order given (oldest to newest). A reading whose
        play is missing from `data` is skipped; it is picked up again on a later poll.
    """
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
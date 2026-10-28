from typing import Dict, Any, Tuple

import requests


def get_team_names(league: str) -> Dict[str, Any]:
    """
    Returns a dictionary with team names as keys and abbreviations as values
    :param league:
    :return: League dictionary
    """
    url = f"https://gamma-api.polymarket.com/teams?league={league}"
    response = requests.get(url)
    return response.json()

def get_match_abbr(home_team: str, away_team: str, league: str, date: str) -> str:
    """
    Returns the abbreviation of the home team and away team in that league
    :param date: YYYY-MM-DD
    :param home_team:
    :param away_team:
    :param league:
    :return: {home_team: abbreviation, away_team: abbreviation}
    """
    teams = get_team_names(league)


    def lookup(full_name: str) -> str | None:
        for team in teams:
            if full_name == team["name"] or full_name.endswith(" " + team["name"]):
                return team["abbreviation"]
        return None


    return f"{league}-{lookup(away_team)}-{lookup(home_team)}-{date}"


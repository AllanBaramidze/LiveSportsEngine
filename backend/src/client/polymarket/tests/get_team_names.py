"""
Getting the right Polymarket slug from the team names lookup, 1
"""
from typing import Dict, Any, Tuple

import requests


def get_team_names(league: str) -> Dict[str, Any]:
    url = f"https://gamma-api.polymarket.com/teams?league={league}"
    response = requests.get(url)
    return response.json()

def get_match_abbr(home_team: str, away_team: str, league: str) -> tuple[str | None, str | None]:
    teams = get_team_names(league)

    by_name = {t['name']: t['abbreviation'] for t in teams}

    def lookup(full_name: str) -> str | None:
        if full_name in by_name:
            return by_name[full_name]
        nickname = full_name.split()[-1]
        return by_name.get(nickname)

    return lookup(home_team), lookup(away_team)

if __name__ == "__main__":
    home, away = get_match_abbr("Toronto Raptors", "New York Knicks", "nba")
    print(f"{home} vs {away}")

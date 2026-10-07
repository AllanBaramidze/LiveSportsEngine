import json

import httpx


def get_scoreboard(sport, league, date) -> dict:
    URL = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard?dates={date}&limit=500"
    response = httpx.get(URL)
    data = response.json()
    return data

def clean_data(data: dict):

    games = []
    for game in data.get("events", []):
        competition = game['competitions'][0]

        home_team = competition['competitors'][0]
        away_team = competition['competitors'][1]

        game_info = {
            "name": game.get("name"),
            "status": game["status"]["type"]["description"],
            "home_team": {
                "name": home_team["team"]["displayName"],
                "score": home_team.get("score")
            },
            "away_team": {
                "name": away_team["team"]["displayName"],
                "score": away_team.get("score")
            }
        }

        games.append(game_info)

    return games


if __name__ == "__main__":
    basic = clean_data(get_scoreboard("football", "nfl","20260927"))
    print(json.dumps(basic, indent=4))
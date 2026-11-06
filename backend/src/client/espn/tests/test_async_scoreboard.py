"""Manual script (not an automated test): poll ESPN scoreboards for a date range.

An early experiment, kept for reference. It talks to ESPN directly with its own small client
and does not use the app's `EspnClient`, parser or database. It pauses `POLL_SECONDS` between days.

Run from the repo root:
    uv run python -m src.client.espn.tests.test_async_scoreboard
"""

import asyncio
from datetime import date, timedelta

import httpx

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports"
LEAGUES = [("football", "nfl"), ("baseball", "mlb")]
POLL_SECONDS = 3


async def get_scoreboard(client: httpx.AsyncClient, sport: str, league: str, date: str) -> dict:
    """Fetch one league's scoreboard for `date` (`YYYYMMDD`) and return the raw JSON."""
    response = await client.get(f"{BASE_URL}/{sport}/{league}/scoreboard?dates={date}&limit=500")
    response.raise_for_status()
    return response.json()

def clean_data(data: dict) -> list:
    """Reduce a scoreboard to name, status and both teams' names and scores.

    Takes the home team as competitor 0, which is not reliable; the real parser uses `homeAway`.
    """
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

async def poll_once(client: httpx.AsyncClient, date: str) -> None:
    """Fetch every league for one day at once and print how many games each returned."""
    results = await asyncio.gather(
        *[get_scoreboard(client, sport, league, date) for sport, league in LEAGUES],
        return_exceptions=True
    )

    for (sport, league), result in zip(LEAGUES, results):
        if isinstance(result, Exception):
            print(f"[{league}] failed: {result!r}")
            continue
        games = clean_data(result)
        print(f"[{sport}/{league}] {len(games)} games")

async def main() -> None:
    print("Starting ESPN Scoreboard Poller")
    current = date(2026, 9, 27)
    end = date(2026, 10, 5)
    print(f"Polling ESPN for {current}")
    print(f"Polling ESPN for {len(LEAGUES)} leagues every {POLL_SECONDS} seconds")
    async with httpx.AsyncClient(timeout=10.0) as client:
        while current <= end:
            await poll_once(client, current.strftime("%Y%m%d"))
            current += timedelta(days=1)
            await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrupted")

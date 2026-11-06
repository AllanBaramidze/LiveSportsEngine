"""Manual script (not an automated test): fetch and parse one finished game's readings.

Calls `EspnClient.get_game_info` for NFL game 401872952 with no saved count, prints the start of
the raw result, then the parsed state and observations. Needs network access only, no database.

Run from the repo root:
    uv run python -m src.client.espn.tests.test_game_info
"""

import asyncio
import json
from datetime import UTC, datetime

from src.client.espn.espn_client import EspnClient
from src.client.espn.parser import parse_observations, parse_state


async def main() -> None:
    async with EspnClient() as espn:
        result = await espn.get_game_info("football", "nfl", "401872952", None)
        print(json.dumps(result, indent=2, default=str)[:3000])
        received = datetime.now(UTC)
        if result is not None:
            observation = parse_observations(result, "401872952", received)
            print("state:", parse_state(result["status"]))
            print(observation)

if __name__ == "__main__":
    asyncio.run(main())
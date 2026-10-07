import asyncio
import json
from datetime import UTC, datetime

from src.client.espn.espn_client import EspnClient
from src.client.espn.parser import parse_observations, parse_state


async def main() -> None:
    async with EspnClient() as espn:
        result = await espn.get_game_info("football", "nfl", "401872952")
        print(json.dumps(result, indent=2, default=str)[:3000])
        received = datetime.now(UTC)
        if result is not None:
            observation = parse_observations(result, "401872952", received)
            print("state:", parse_state(result["status"]))
            print(observation)



if __name__ == "__main__":
    asyncio.run(main())
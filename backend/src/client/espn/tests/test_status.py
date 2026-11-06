"""Manual script (not an automated test): fetch one game's status and print its state.

Calls `EspnClient.get_match_status` for an NHL game and runs the result through `parse_state`
(`pre`, `in` or `post`). Needs network access only, no database.

Run from the repo root:
    uv run python -m src.client.espn.tests.test_status
"""

import asyncio

from src.client.espn.espn_client import EspnClient
from src.client.espn.parser import parse_state


async def main() -> None:
    async with EspnClient() as espn:
        data = await espn.get_match_status("hockey", "nhl", "401892445")  # use your method's name
    print(parse_state(data))


if __name__ == "__main__":
    asyncio.run(main())
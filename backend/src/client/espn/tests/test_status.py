import asyncio

from src.client.espn.espn_client import EspnClient
from src.client.espn.parser import parse_state


async def main() -> None:
    async with EspnClient() as espn:
        data = await espn.get_match_status("hockey", "nhl", "401892445")  # use your method's name
    print(parse_state(data))


if __name__ == "__main__":
    asyncio.run(main())
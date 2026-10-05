import asyncio

from src.client.espn.espn_client import EspnClient


async def main() -> None:
    async with EspnClient() as espn:
        data = await espn.get_match_status("hockey", "nhl", "401892445")  # use your method's name
    print(data["type"]["state"], "|", data["type"]["detail"])


if __name__ == "__main__":
    asyncio.run(main())
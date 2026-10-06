from datetime import date
from typing import Any, Self

import httpx

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/"
CORE_URL = "https://sports.core.api.espn.com/v2/sports"
# /{sport}/leagues/{league}/events/{espn_id}/competitions/{espn_id}/status
class EspnClient:
    """Thin async wrapper around ESPN's public site API. HTTP only: no parsing, no DB.

    Use as `async with EspnClient() as espn:` so the connection pool gets closed.
    """

    def __init__(self, timeout: float = 10.0) -> None:
        self._http = httpx.AsyncClient(base_url=BASE_URL, timeout=timeout)


    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self._http.aclose()


    async def get_scoreboard(self, sport: str, league: str, day: date) -> dict[str, Any]:
        response = await self._http.get(f"{sport}/{league}/scoreboard",
            params={"dates": day.strftime("%Y%m%d"), "limit": 500},
        )
        response.raise_for_status()
        return response.json()

    async def get_match_status(self, sport: str, league: str, espn_id: str) -> dict[str, Any]:
        response = await self._http.get(f"{CORE_URL}/{sport}/leagues/{league}/events/{espn_id}/competitions/{espn_id}/status")
        response.raise_for_status()
        return response.json()
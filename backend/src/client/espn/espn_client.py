import asyncio
import math
from datetime import date
from typing import Any, Self

import httpx

LIMIT = 12

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

    async def _page(self, url: str, page: int) -> dict[str, Any]:
        response = await self._http.get(url, params={"limit": LIMIT,"page": page})
        response.raise_for_status()
        return response.json()


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

    async def _fetch_pages(
        self, prob_url: str, plays_url: str, pages: list[int]
    ) -> dict[int, tuple[dict[str, Any], dict[str, Any]]]:
        """Fetch the same page numbers from probabilities and plays, all at once."""
        results = await asyncio.gather(
            *(self._page(prob_url, p) for p in pages),
            *(self._page(plays_url, p) for p in pages),
        )
        prob_pages, play_pages = results[: len(pages)], results[len(pages) :]
        return {p: (prob, plays) for p, prob, plays in zip(pages, prob_pages, play_pages, strict=True)}

    async def get_game_info(self, sport: str, league: str, espn_id: str, count: int | None) -> dict[str, Any]:
        """Status plus the newest readings and their plays (the last two pages of LIMIT).

        `count` is the reading count from the previous poll (Valkey); None or 0 means ask ESPN.
        """
        game_url = f"{CORE_URL}/{sport}/leagues/{league}/events/{espn_id}/competitions/{espn_id}"
        prob_url = f"{game_url}/probabilities"
        plays_url = f"{game_url}/plays"

        status = await self.get_match_status(sport, league, espn_id)
        # TODO: MLB answers 400 on probabilities for ~2 min after a game goes "in",
        # which raises here and throws away `status`.

        if not count:  # first poll of this game, Valkey lost the key, or no readings last time
            count = (await self._page(prob_url, 1))["count"]
        if count == 0:
            return {"status": status, "count": 0, "readings": [], "plays": []}

        last = math.ceil(count / LIMIT)
        pages = [last - 1, last] if last > 1 else [1]
        fetched = await self._fetch_pages(prob_url, plays_url, pages)

        # The count moved since last poll (new page filled, or deletions shrank it):
        # also fetch the real newest two pages.
        page_count = fetched[max(fetched)][0]["pageCount"]
        if page_count != last:
            newest = [p for p in (page_count - 1, page_count) if p >= 1 and p not in fetched]
            fetched |= await self._fetch_pages(prob_url, plays_url, newest)

        ordered = [fetched[p] for p in sorted(fetched)]  # oldest page first
        return {
            "status": status,
            "count": fetched[max(fetched)][0]["count"],  # fresh from this poll
            "readings": [item for prob, _ in ordered for item in prob["items"]],
            "plays": [item for _, plays in ordered for item in plays["items"]],
        }







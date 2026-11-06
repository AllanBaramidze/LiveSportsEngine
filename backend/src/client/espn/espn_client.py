"""Async HTTP client for ESPN's public (unofficial, unauthenticated) APIs.

Two hosts are used: the *site* API for scoreboards and the *core* API for per-game status,
win probabilities and plays. This module only fetches and returns raw JSON; interpreting it
is the parser's job.
"""

import asyncio
import math
from datetime import date
from typing import Any, Self

import httpx

# Items per page when reading the probabilities and plays lists. Also the page size the
# "newest two pages" logic in `get_game_info` relies on.
LIMIT = 12

# Site API: scoreboards. Used as the client's base URL.
BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/"
# Core API: status, probabilities, plays. Always requested with the absolute URL.
CORE_URL = "https://sports.core.api.espn.com/v2/sports"
# /{sport}/leagues/{league}/events/{espn_id}/competitions/{espn_id}/status


class EspnClient:
    """Thin async wrapper around ESPN's public site API. HTTP only: no parsing, no DB.

    Use as `async with EspnClient() as espn:` so the connection pool gets closed.
    """

    def __init__(self, timeout: float = 10.0) -> None:
        """Create the HTTP connection pool.

        Args:
            timeout: Seconds to wait for each request before raising.
        """
        self._http = httpx.AsyncClient(base_url=BASE_URL, timeout=timeout)


    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self._http.aclose()

    async def _page(self, url: str, page: int) -> dict[str, Any]:
        """Fetch one page of a paginated core-API list, `LIMIT` items per page.

        Pages are numbered from 1 and ordered oldest first. A page past the end returns HTTP 200
        with no items, not an error.

        Raises:
            httpx.HTTPStatusError: On a non-2xx response.
        """
        response = await self._http.get(url, params={"limit": LIMIT,"page": page})
        response.raise_for_status()
        return response.json()


    async def get_scoreboard(self, sport: str, league: str, day: date) -> dict[str, Any]:
        """Fetch every event of one league on one day.

        Args:
            sport: ESPN sport name, e.g. `basketball`.
            league: League code, e.g. `nba`.
            day: A US Eastern calendar day (ESPN's `dates=` follows Eastern time).

        Returns:
            The raw scoreboard JSON.

        Raises:
            httpx.HTTPStatusError: On a non-2xx response.
        """
        response = await self._http.get(f"{sport}/{league}/scoreboard",
            params={"dates": day.strftime("%Y%m%d"), "limit": 500},
        )
        response.raise_for_status()
        return response.json()

    async def get_match_status(self, sport: str, league: str, espn_id: str) -> dict[str, Any]:
        """Fetch one game's status from the core API (about 360 bytes).

        Returns the state (`pre` / `in` / `post`), period and clock, but not the score.

        Raises:
            httpx.HTTPStatusError: On a non-2xx response.
        """
        response = await self._http.get(f"{CORE_URL}/{sport}/leagues/{league}/events/{espn_id}/competitions/{espn_id}/status")
        response.raise_for_status()
        return response.json()

    async def _fetch_pages(
        self, prob_url: str, plays_url: str, pages: list[int]
    ) -> dict[int, tuple[dict[str, Any], dict[str, Any]]]:
        """Fetch the same page numbers from the probabilities and plays lists, all at once.

        Returns:
            `{page_number: (probabilities_page, plays_page)}`.
        """
        results = await asyncio.gather(
            *(self._page(prob_url, p) for p in pages),
            *(self._page(plays_url, p) for p in pages),
        )
        prob_pages, play_pages = results[: len(pages)], results[len(pages) :]
        return {p: (prob, plays) for p, prob, plays in zip(pages, prob_pages, play_pages, strict=True)}

    async def get_game_info(self, sport: str, league: str, espn_id: str, count: int | None) -> dict[str, Any]:
        """Fetch a live game's status plus its newest win-probability readings and plays.

        ESPN lists readings oldest first and ignores sort parameters, so the newest ones are on
        the last pages. With `count` readings and `LIMIT` per page, the last page is
        `ceil(count / LIMIT)`; the last two pages are fetched so a burst of plays between two
        polls is not missed. If ESPN's own page count differs from that guess (readings were
        added or deleted since `count` was saved), the real newest two pages are fetched too.

        The status is requested first, but it is only returned if every later request also
        succeeds; if one raises, the status is lost with it (see the TODO below).

        Args:
            sport: ESPN sport name.
            league: League code.
            espn_id: ESPN event id.
            count: Reading count saved by the previous poll (Valkey). `None` or 0 means
                unknown, and ESPN is asked for it with one extra request.

        Returns:
            A dict with `status` (raw status JSON), `count` (fresh from this poll), `readings`
            and `plays` (item lists, oldest first). `readings` and `plays` are empty when ESPN
            has no readings yet.

        Raises:
            httpx.HTTPStatusError: On a non-2xx response. The status is then lost with it.
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







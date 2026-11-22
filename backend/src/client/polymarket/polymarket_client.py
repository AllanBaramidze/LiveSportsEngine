"""Async HTTP client for Polymarket's public APIs.

This module only fetches and returns raw JSON; interpreting it is the parser's job.
"""

from datetime import UTC, datetime
from typing import Any, Self

from httpx import AsyncBaseTransport, AsyncClient

gammaURL = "https://gamma-api.polymarket.com"
'''Discover events and markets, and retrieve the metadata needed to work with them.'''

clobURL = "https://clob.polymarket.com"
'''Read live market state, then place and manage orders.'''

# Gamma returns at most 100 events per page and silently ignores a larger limit.
PAGE_SIZE = 100


def gamma_time(moment: datetime) -> str:
    """An aware datetime as the UTC text Gamma's filters expect."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class PolymarketClient:
    """Thin async wrapper around Polymarket. HTTP only: no parsing, no DB.

    Use as `async with PolymarketClient() as polymarket:` so the connection pool gets closed.
    """

    def __init__(self, timeout: float = 15.0, transport: AsyncBaseTransport | None = None) -> None:
        """Create the HTTP connection pool.

        Args:
            timeout: Seconds to wait for each request before raising.
            transport: Replaces the network in tests; leave as `None` otherwise.
        """
        self._http = AsyncClient(timeout=timeout, transport=transport)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self._http.aclose()

    async def list_game_events(self, tag_id: int, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """Fetch every event of one league that starts in a time window, across all pages.

        `include_markets=false` matters: with markets, two days of NFL is 23 MB; without, 126 KB.

        Args:
            tag_id: The league's Polymarket tag.
            start: Earliest start (timezone-aware).
            end: Latest start (timezone-aware).

        Returns:
            The complete list of raw events, child events included. Never a partial list: callers
            treat a missing event as "not listed", so half a list would be worse than an error.

        Raises:
            httpx.HTTPStatusError: On a non-2xx response on any page.
            ValueError: On a body that isn't an event list, or a cursor that repeats.
        """
        params: dict[str, str | int] = {
            "tag_id": tag_id,
            "include_markets": "false",
            "limit": PAGE_SIZE,
            "start_time_min": gamma_time(start),
            "start_time_max": gamma_time(end),
        }
        events: list[dict[str, Any]] = []
        seen_cursors: set[str] = set()
        while True:
            response = await self._http.get(f"{gammaURL}/events/keyset", params=params)
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict) or not isinstance(body.get("events"), list):
                # ValueError, not TypeError: the data is bad, not the caller's argument.
                raise ValueError(f"Gamma returned no event list: {str(body)[:200]}")  # noqa: TRY004
            events.extend(body["events"])

            cursor = body.get("next_cursor")
            if not cursor:
                return events
            if cursor in seen_cursors:
                raise ValueError(f"Gamma repeated the page cursor {cursor!r}")
            seen_cursors.add(cursor)
            params["after_cursor"] = cursor

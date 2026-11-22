import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from src.client.polymarket.polymarket_client import PolymarketClient
from tests.helpers import at

START, END = at("2026-11-22 00:00"), at("2026-11-29 00:00")


class ListGameEventsTest(unittest.IsolatedAsyncioTestCase):
    async def fetch(self, *responses, start=START, end=END):
        self.requests = []
        queue = list(responses)

        def handle(request):
            self.requests.append(request)
            return queue.pop(0)

        async with PolymarketClient(transport=httpx.MockTransport(handle)) as client:
            return await client.list_game_events(450, start, end)

    async def test_asks_for_one_league_and_window_without_the_heavy_markets(self):
        await self.fetch(httpx.Response(200, json={"events": []}))
        [request] = self.requests
        self.assertEqual(request.url.host, "gamma-api.polymarket.com")
        self.assertEqual(request.url.path, "/events/keyset")
        self.assertEqual(
            dict(request.url.params),
            {
                "tag_id": "450",
                "include_markets": "false",
                "limit": "100",
                "start_time_min": "2026-11-22T00:00:00Z",
                "start_time_max": "2026-11-29T00:00:00Z",
            },
        )

    async def test_window_is_sent_in_utc(self):
        eastern = datetime(2026, 11, 22, 19, 0, tzinfo=ZoneInfo("America/New_York"))
        await self.fetch(httpx.Response(200, json={"events": []}), start=eastern)
        self.assertEqual(self.requests[0].url.params["start_time_min"], "2026-11-23T00:00:00Z")

    async def test_follows_every_page(self):
        events = await self.fetch(
            httpx.Response(200, json={"events": [{"slug": "a"}], "next_cursor": "p2"}),
            httpx.Response(200, json={"events": [{"slug": "b"}], "next_cursor": "p3"}),
            httpx.Response(200, json={"events": [{"slug": "c"}]}),
        )
        self.assertEqual([e["slug"] for e in events], ["a", "b", "c"])
        self.assertEqual([r.url.params.get("after_cursor") for r in self.requests], [None, "p2", "p3"])

    async def test_failure_on_a_later_page_raises_instead_of_returning_half_a_list(self):
        with self.assertRaises(httpx.HTTPStatusError):
            await self.fetch(
                httpx.Response(200, json={"events": [{"slug": "a"}], "next_cursor": "p2"}),
                httpx.Response(503),
            )

    async def test_rate_limit_raises(self):
        with self.assertRaises(httpx.HTTPStatusError):
            await self.fetch(httpx.Response(429))

    async def test_success_status_with_the_wrong_body_raises(self):
        for body in ({"error": "busy"}, [], {"events": None}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                await self.fetch(httpx.Response(200, json=body))

    async def test_repeating_cursor_raises_instead_of_looping_forever(self):
        page = {"events": [], "next_cursor": "same"}
        with self.assertRaises(ValueError):
            await self.fetch(httpx.Response(200, json=page), httpx.Response(200, json=page))

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from src import main
from src.services.polymarket_link import LinkReport
from tests.helpers import game


class LinkLoopTest(unittest.IsolatedAsyncioTestCase):
    async def test_linking_waits_for_the_first_schedule_run(self):
        ready = asyncio.Event()
        with patch.object(main, "link_upcoming", AsyncMock(return_value={})) as link:
            task = asyncio.create_task(main.query_links(ready, set()))
            await asyncio.sleep(0)
            link.assert_not_awaited()
            ready.set()
            await task
            link.assert_awaited_once()

    async def test_failed_schedule_run_still_releases_linking(self):
        ready = asyncio.Event()
        espn_down = patch.object(main, "ingest_days", AsyncMock(side_effect=RuntimeError("ESPN down")))
        with espn_down, self.assertRaises(RuntimeError):
            await main.run_once_daily(ready)
        self.assertTrue(ready.is_set())

    async def test_one_failed_league_is_logged_and_does_not_raise(self):
        ready = asyncio.Event()
        ready.set()
        gamma_down = patch.object(main, "link_upcoming", AsyncMock(return_value={"nfl": RuntimeError("down")}))
        with gamma_down, self.assertLogs(main.log, "ERROR") as logs:
            await main.query_links(ready, set())
        self.assertIn("nfl", logs.output[0])

    async def test_unlinked_game_is_warned_about_once_not_every_ten_minutes(self):
        ready, warned = asyncio.Event(), set()
        ready.set()
        missing = game("1", "Away", "Home", "2026-01-01 00:00")
        report = {"nba": LinkReport([missing], {})}
        with patch.object(main, "link_upcoming", AsyncMock(return_value=report)), self.assertLogs(main.log) as logs:
            await main.query_links(ready, warned)
            await main.query_links(ready, warned)
        self.assertEqual(sum("no Polymarket link" in line for line in logs.output), 1)

    async def test_no_warning_for_finished_or_far_off_games(self):
        ready = asyncio.Event()
        ready.set()
        finished = game("1", "Away", "Home", "2026-01-01 00:00", status="post")
        far_off = game("2", "Away", "Home", "2099-01-01 00:00")
        report = {"nba": LinkReport([finished, far_off], {})}
        with patch.object(main, "link_upcoming", AsyncMock(return_value=report)), self.assertNoLogs(main.log):
            await main.query_links(ready, set())

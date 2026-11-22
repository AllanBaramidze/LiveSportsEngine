"""The linker against a real Postgres, with only Polymarket's HTTP faked.

Skipped unless TEST_DATABASE_URL is set. Its database name must end in `_test`, and each test
works in a schema of its own that is dropped afterwards. One-time setup:

    docker compose exec db createdb -U postgres livesports_test

Then set TEST_DATABASE_URL to your DATABASE_URL with that database name and run the tests.
"""

import os
import unittest
import uuid
from unittest.mock import patch

import httpx
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.client.polymarket.polymarket_client import PolymarketClient
from src.database.models import Base, Match
from src.database.repositories import matches
from src.schemas.match import MatchCreate
from src.services import polymarket_link
from tests.helpers import at, game, real_events

URL = os.environ.get("TEST_DATABASE_URL", "")
TAGS = {"nfl": "450", "nba": "745", "mlb": "100381"}
NIGHT = "nfl-min-sf-2026-11-23"
START, END = at("2026-11-21 00:00"), at("2026-11-29 00:00")


def vikings(espn_id="401", start="2026-11-23 01:20", **kwargs):
    return game(espn_id, "Minnesota Vikings", "San Francisco 49ers", start, league="nfl", **kwargs)


def incoming(**changes):
    values = {
        "espn_id": "401", "league": "nfl", "sport": "football", "status": "pre",
        "matchup": "Minnesota Vikings at San Francisco 49ers",
        "home_team": "San Francisco 49ers", "home_score": "0",
        "away_team": "Minnesota Vikings", "away_score": "0", "date": at("2026-11-23 01:20"),
    }
    return MatchCreate(**(values | changes))


@unittest.skipUnless(URL, "set TEST_DATABASE_URL to run the Postgres tests")
class PostgresTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if not (make_url(URL).database or "").endswith("_test"):
            self.fail("TEST_DATABASE_URL must name a database ending in _test")
        self.schema = f"link_{uuid.uuid4().hex[:12]}"
        self.admin = create_async_engine(URL)
        async with self.admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{self.schema}"'))
        self.engine = create_async_engine(URL, connect_args={"options": f"-csearch_path={self.schema}"})
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        patcher = patch.object(polymarket_link, "SessionLocal", self.sessions)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def asyncTearDown(self):
        await self.engine.dispose()
        async with self.admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))
        await self.admin.dispose()

    async def store(self, *games):
        async with self.sessions() as session:
            session.add_all(games)
            await session.commit()

    async def upsert(self, *games):
        async with self.sessions() as session:
            count = await matches.upsert_matches(session, games)
            await session.commit()
        return count

    async def slugs(self):
        async with self.sessions() as session:
            rows = await session.execute(select(Match.espn_id, Match.poly_slug))
            return {espn_id: slug for espn_id, slug in rows}

    async def link(self, events, start=START, end=END, *, down=(), **options):
        self.asked = []

        def handle(request):
            tag = request.url.params["tag_id"]
            self.asked.append(tag)
            if tag in down:
                return httpx.Response(503)
            return httpx.Response(200, json={"events": events.get(tag, [])})

        async with PolymarketClient(transport=httpx.MockTransport(handle)) as client:
            return await polymarket_link.link_games(client, start, end, **options)

    async def test_links_a_night_game(self):
        await self.store(vikings())
        await self.link({TAGS["nfl"]: real_events(NIGHT, f"{NIGHT}-player-props")})
        self.assertEqual(await self.slugs(), {"401": NIGHT})

    async def test_replaces_the_old_guessed_slug(self):
        await self.store(vikings(slug="nfl-min-sf-2026-11-22"))
        await self.link({TAGS["nfl"]: real_events(NIGHT)})
        self.assertEqual(await self.slugs(), {"401": NIGHT})

    async def test_second_run_changes_nothing(self):
        await self.store(vikings())
        await self.link({TAGS["nfl"]: real_events(NIGHT)})
        again = await self.link({TAGS["nfl"]: real_events(NIGHT)})
        self.assertEqual(again["nfl"].changes, {})

    async def test_daily_schedule_refresh_keeps_the_link(self):
        await self.store(vikings(slug=NIGHT))
        await self.upsert(incoming(date=at("2026-11-23 01:30")))
        self.assertEqual(await self.slugs(), {"401": NIGHT})

    async def test_game_listed_on_two_days_does_not_break_the_upsert(self):
        count = await self.upsert(incoming(home_score="0"), incoming(home_score="7"))
        self.assertEqual(count, 1)
        async with self.sessions() as session:
            stored = await matches.get_by_espn_id(session, "401")
        self.assertEqual(stored.home_score, "7")

    async def test_outage_in_one_league_does_not_stop_another_or_erase_its_links(self):
        await self.store(
            vikings(slug="existing"),
            game("501", "Portland Trail Blazers", "New York Knicks", "2026-11-22 00:30"),
        )
        results = await self.link({TAGS["nba"]: real_events("nba-por-nyk-2026-11-21")}, down={TAGS["nfl"]})
        self.assertIsInstance(results["nfl"], httpx.HTTPStatusError)
        self.assertEqual(await self.slugs(), {"401": "existing", "501": "nba-por-nyk-2026-11-21"})

    async def test_empty_listing_erases_nothing(self):
        await self.store(vikings(slug=NIGHT))
        await self.link({}, repair=True)
        self.assertEqual(await self.slugs(), {"401": NIGHT})

    async def test_league_without_games_is_not_requested(self):
        await self.store(vikings())
        await self.link({TAGS["nfl"]: real_events(NIGHT)})
        self.assertEqual(self.asked, [TAGS["nfl"]])

    async def test_slug_moves_to_the_makeup_game_from_far_outside_the_window(self):
        await self.store(vikings("original", "2026-10-01 00:00", slug=NIGHT, status="post"), vikings("makeup"))
        await self.link({TAGS["nfl"]: real_events(NIGHT)})
        self.assertEqual(await self.slugs(), {"original": None, "makeup": NIGHT})

    async def test_game_just_outside_the_window_still_blocks_a_wrong_match(self):
        slug = "mlb-chc-cle-2026-04-05"
        teams = ("Chicago Cubs", "Cleveland Guardians")
        await self.store(
            game("g1", *teams, "2026-04-05 17:10", league="mlb", status="post"),
            game("g2", *teams, "2026-04-05 20:30", league="mlb"),
        )
        await self.link({TAGS["mlb"]: real_events(slug)}, at("2026-04-05 19:00"), at("2026-04-06 19:00"))
        self.assertEqual(await self.slugs(), {"g1": None, "g2": None})

    async def test_dry_run_reports_without_writing(self):
        await self.store(vikings())
        results = await self.link({TAGS["nfl"]: real_events(NIGHT)}, dry_run=True)
        self.assertEqual(results["nfl"].changes, {"401": NIGHT})
        self.assertEqual(await self.slugs(), {"401": None})

    async def test_more_than_fifty_games_are_all_considered(self):
        # `list_matches` stops at 50 by default; a week of NBA is more than that.
        await self.store(*(game(str(i), f"Away {i}", f"Home {i}", "2026-11-22 00:00") for i in range(60)))
        results = await self.link({})
        self.assertEqual(len(results["nba"].games), 60)

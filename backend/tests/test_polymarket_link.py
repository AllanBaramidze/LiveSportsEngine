import unittest
from datetime import date

from src.services.espn_ingest import LEAGUES
from src.services.polymarket_link import LEAGUE_TAGS, eastern_window, plan_links
from tests.helpers import at, game

START, END = at("2026-11-21 00:00"), at("2026-11-29 00:00")


def knicks(espn_id="1", start="2026-11-22 00:00", slug=None, status="pre"):
    return game(espn_id, "New York Knicks", "Boston Celtics", start, slug=slug, status=status)


class PlanLinksTest(unittest.TestCase):
    def plan(self, games, matched, *, listed=True, repair=False, holders=()):
        return plan_links(games, matched, holders, START, END, listed=listed, repair=repair)

    def test_sets_a_missing_link(self):
        self.assertEqual(self.plan([knicks()], {"1": "s"}).changes, {"1": "s"})

    def test_replaces_a_wrong_link(self):
        self.assertEqual(self.plan([knicks(slug="wrong")], {"1": "s"}).changes, {"1": "s"})

    def test_correct_link_is_not_rewritten(self):
        self.assertEqual(self.plan([knicks(slug="s")], {"1": "s"}).changes, {})

    def test_no_match_keeps_the_link_it_has(self):
        self.assertEqual(self.plan([knicks(slug="s")], {}).changes, {})

    def test_slug_moves_from_whoever_held_it(self):
        old = knicks("old", "2026-09-01 00:00", slug="s", status="post")
        self.assertEqual(self.plan([knicks()], {"1": "s"}, holders=[old]).changes, {"old": None, "1": "s"})

    def test_duplicate_holder_is_released_when_the_owner_is_already_right(self):
        owner, copycat = knicks(slug="s"), knicks("2", slug="s")
        result = self.plan([owner, copycat], {"1": "s"}, holders=[owner, copycat])
        self.assertEqual(result.changes, {"2": None})

    def test_two_games_can_swap_links(self):
        a, b = knicks("a", slug="y"), knicks("b", slug="x")
        result = self.plan([a, b], {"a": "x", "b": "y"}, holders=[a, b])
        self.assertEqual(result.changes, {"a": "x", "b": "y"})

    def test_neighbour_outside_the_window_is_not_linked(self):
        outside = knicks(start="2026-11-20 23:59")
        result = self.plan([outside], {"1": "s"})
        self.assertEqual((result.changes, result.games), ({}, []))

    def test_repair_clears_an_unconfirmed_link(self):
        self.assertEqual(self.plan([knicks(slug="guess")], {}, repair=True).changes, {"1": None})

    def test_repair_does_nothing_when_polymarket_listed_nothing(self):
        result = self.plan([knicks(slug="s")], {}, listed=False, repair=True)
        self.assertEqual(result.changes, {})

    def test_repair_leaves_games_outside_the_window_alone(self):
        result = self.plan([knicks(start="2026-11-29 00:00", slug="s")], {}, repair=True)
        self.assertEqual(result.changes, {})

    def test_report_lists_games_left_without_a_link(self):
        games = [knicks("linked"), knicks("kept", slug="old"), knicks("none")]
        result = self.plan(games, {"linked": "s"})
        self.assertEqual([g.espn_id for g in result.unlinked], ["none"])

    def test_report_counts_a_released_game_as_unlinked(self):
        owner, copycat = knicks(slug="s"), knicks("2", slug="s")
        result = self.plan([owner, copycat], {"1": "s"}, holders=[owner, copycat])
        self.assertEqual([g.espn_id for g in result.unlinked], ["2"])


class EasternWindowTest(unittest.TestCase):
    def test_covers_whole_eastern_days_including_the_last(self):
        self.assertEqual(
            eastern_window(date(2026, 11, 21), date(2026, 11, 22)),
            (at("2026-11-21 05:00"), at("2026-11-23 05:00")),
        )

    def test_day_the_clocks_go_back_is_25_hours(self):
        self.assertEqual(
            eastern_window(date(2026, 11, 1), date(2026, 11, 1)),
            (at("2026-11-01 04:00"), at("2026-11-02 05:00")),
        )


class LeagueCoverageTest(unittest.TestCase):
    def test_every_ingested_league_can_be_linked(self):
        self.assertLessEqual({league for _, league in LEAGUES}, set(LEAGUE_TAGS))

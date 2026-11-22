import unittest

from src.client.polymarket.parser import parse_games
from src.services.game_matching import match_games, same_team
from tests.helpers import game, market, real_events

AWAY, HOME = "New York Knicks", "Boston Celtics"


def knicks_at_celtics(espn_id, start):
    return game(espn_id, AWAY, HOME, start)


def listing(slug, start):
    return market(slug, "Knicks", "Celtics", start)


class SameTeamTest(unittest.TestCase):
    def test_exact_full_name(self):
        self.assertTrue(same_team("Minnesota Vikings", "Minnesota Vikings"))

    def test_nickname_is_the_end_of_the_espn_name(self):
        for espn, poly in (
            ("New York Knicks", "Knicks"),
            ("Portland Trail Blazers", "Trail Blazers"),
            ("LA Clippers", "Clippers"),
            ("Philadelphia 76ers", "76ers"),
        ):
            with self.subTest(espn):
                self.assertTrue(same_team(espn, poly))

    def test_nickname_must_start_on_a_word_boundary(self):
        self.assertFalse(same_team("Charlotte Hornets", "nets"))
        self.assertFalse(same_team("Brooklyn Nets", "ets"))

    def test_same_city_is_not_the_same_team(self):
        self.assertFalse(same_team("Los Angeles Rams", "Los Angeles Chargers"))
        self.assertFalse(same_team("New York Jets", "New York Giants"))

    def test_city_alone_is_not_a_team(self):
        self.assertFalse(same_team("New York Knicks", "New York"))

    def test_empty_name_matches_nothing(self):
        self.assertFalse(same_team("New York Knicks", ""))
        self.assertFalse(same_team("New York Knicks ", ""))


class RealPayloadTest(unittest.TestCase):
    """Each case is a real game that slug-building got wrong or could get wrong."""

    def link(self, games, *slugs):
        return match_games(games, parse_games(real_events(*slugs)))

    def test_nfl_night_game_whose_slug_has_the_utc_date(self):
        games = [game("1", "Minnesota Vikings", "San Francisco 49ers", "2026-11-23 01:20")]
        self.assertEqual(self.link(games, "nfl-min-sf-2026-11-23"), {"1": "nfl-min-sf-2026-11-23"})

    def test_nba_night_game_whose_slug_has_the_eastern_date(self):
        games = [game("1", "Portland Trail Blazers", "New York Knicks", "2026-11-22 00:30")]
        self.assertEqual(self.link(games, "nba-por-nyk-2026-11-21"), {"1": "nba-por-nyk-2026-11-21"})

    def test_rescheduled_game_keeps_the_slug_of_its_original_date(self):
        games = [game("1", "Denver Nuggets", "Memphis Grizzlies", "2026-03-19 00:30")]
        self.assertEqual(self.link(games, "nba-den-mem-2026-01-25"), {"1": "nba-den-mem-2026-01-25"})

    def test_event_whose_start_time_is_five_hours_off(self):
        games = [game("1", "Philadelphia Eagles", "Los Angeles Chargers", "2025-12-09 01:15")]
        self.assertEqual(self.link(games, "nfl-phi-lac-2025-12-08"), {"1": "nfl-phi-lac-2025-12-08"})

    def test_doubleheader_gives_each_game_its_own_event(self):
        games = [
            game("g1", "Chicago Cubs", "Cleveland Guardians", "2026-04-05 17:10"),
            game("g2", "Chicago Cubs", "Cleveland Guardians", "2026-04-05 20:30"),
        ]
        self.assertEqual(
            self.link(games, "mlb-chc-cle-2026-04-05", "mlb-chc-cle-2026-04-05-dh2"),
            {"g1": "mlb-chc-cle-2026-04-05", "g2": "mlb-chc-cle-2026-04-05-dh2"},
        )

    def test_makeup_doubleheader_where_game_one_has_a_slug_from_two_months_earlier(self):
        games = [
            game("g1", "Tampa Bay Rays", "Boston Red Sox", "2026-07-17 17:35"),
            game("g2", "Tampa Bay Rays", "Boston Red Sox", "2026-07-17 23:10"),
        ]
        self.assertEqual(
            self.link(games, "mlb-tb-bos-2026-05-09", "mlb-tb-bos-2026-07-17"),
            {"g1": "mlb-tb-bos-2026-05-09", "g2": "mlb-tb-bos-2026-07-17"},
        )

    def test_reversed_home_and_away_is_a_different_event(self):
        games = [game("1", "Dallas Cowboys", "Seattle Seahawks", "2026-08-16 00:00")]
        self.assertEqual(
            self.link(games, "nfl-sea-dal-2026-08-16", "nfl-dal-sea-2026-08-16"),
            {"1": "nfl-dal-sea-2026-08-16"},
        )

    def test_split_squad_games_two_hours_apart(self):
        games = [
            game("a", "Cincinnati Reds", "San Francisco Giants", "2026-03-13 23:05"),
            game("b", "San Francisco Giants", "Cincinnati Reds", "2026-03-14 01:05"),
        ]
        self.assertEqual(
            self.link(games, "mlb-cin-sf-2026-03-13", "mlb-sf-cin-2026-03-13"),
            {"a": "mlb-cin-sf-2026-03-13", "b": "mlb-sf-cin-2026-03-13"},
        )

    def test_two_events_for_the_same_game_are_not_guessed_between(self):
        games = [game("1", "Indiana Pacers", "Memphis Grizzlies", "2025-10-26 00:00")]
        self.assertEqual(self.link(games, "nba-ind-mem-2025-10-25", "nba-ind-mem-2025-10-26"), {})


class RuleTest(unittest.TestCase):
    def test_nothing_to_match(self):
        self.assertEqual(match_games([], []), {})
        self.assertEqual(match_games([knicks_at_celtics("1", "2026-11-22 00:00")], []), {})
        self.assertEqual(match_games([], [listing("s", "2026-11-22 00:00")]), {})

    def test_placeholder_teams_are_not_linked(self):
        games = [game("1", "TBD", "TBD", "2026-12-04 05:00")]
        self.assertEqual(match_games(games, [listing("s", "2026-12-04 05:00")]), {})

    def test_one_matching_team_is_not_enough(self):
        for away, home in (("Miami Heat", HOME), (AWAY, "Miami Heat")):
            with self.subTest(away=away, home=home):
                games = [game("1", away, home, "2026-11-22 00:00")]
                self.assertEqual(match_games(games, [listing("s", "2026-11-22 00:00")]), {})

    def test_twelve_hours_is_the_outer_limit_in_both_directions(self):
        games = [knicks_at_celtics("1", "2026-11-22 12:00")]
        for start, expected in (
            ("2026-11-22 00:00", {"1": "s"}),
            ("2026-11-23 00:00", {"1": "s"}),
            ("2026-11-21 23:59", {}),
            ("2026-11-23 00:01", {}),
        ):
            with self.subTest(start):
                self.assertEqual(match_games(games, [listing("s", start)]), expected)

    def test_one_hour_is_close_enough_to_beat_a_second_candidate(self):
        games = [knicks_at_celtics("1", "2026-11-22 12:00")]
        markets = [listing("near", "2026-11-22 13:00"), listing("far", "2026-11-22 18:00")]
        self.assertEqual(match_games(games, markets), {"1": "near"})

    def test_just_over_an_hour_does_not_beat_a_second_candidate(self):
        games = [knicks_at_celtics("1", "2026-11-22 12:00")]
        markets = [listing("near", "2026-11-22 13:01"), listing("far", "2026-11-22 18:00")]
        self.assertEqual(match_games(games, markets), {})

    def test_game_two_does_not_borrow_game_ones_event(self):
        games = [knicks_at_celtics("g1", "2026-11-22 17:00"), knicks_at_celtics("g2", "2026-11-22 21:00")]
        self.assertEqual(match_games(games, [listing("one", "2026-11-22 17:00")]), {"g1": "one"})

    def test_only_event_between_two_games_is_given_to_neither(self):
        games = [knicks_at_celtics("g1", "2026-11-22 17:00"), knicks_at_celtics("g2", "2026-11-22 21:00")]
        self.assertEqual(match_games(games, [listing("one", "2026-11-22 19:00")]), {})

    def test_two_games_within_an_hour_of_one_event_are_given_neither(self):
        games = [knicks_at_celtics("g1", "2026-11-22 17:00"), knicks_at_celtics("g2", "2026-11-22 18:00")]
        self.assertEqual(match_games(games, [listing("one", "2026-11-22 17:30")]), {})

    def test_back_to_back_nights_do_not_cross(self):
        games = [knicks_at_celtics("fri", "2026-11-21 02:00"), knicks_at_celtics("sat", "2026-11-22 00:00")]
        markets = [listing("sat-slug", "2026-11-22 00:00"), listing("fri-slug", "2026-11-21 02:00")]
        self.assertEqual(match_games(games, markets), {"fri": "fri-slug", "sat": "sat-slug"})

    def test_input_order_does_not_change_the_answer(self):
        games = [knicks_at_celtics("g1", "2026-11-22 17:00"), knicks_at_celtics("g2", "2026-11-22 21:00")]
        markets = [listing("one", "2026-11-22 17:00"), listing("two", "2026-11-22 21:10")]
        expected = {"g1": "one", "g2": "two"}
        self.assertEqual(match_games(games, markets), expected)
        self.assertEqual(match_games(games[::-1], markets[::-1]), expected)

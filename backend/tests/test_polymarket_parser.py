import copy
import unittest

from src.client.polymarket.parser import parse_games
from tests.helpers import at, real_events

NIGHT = "nfl-min-sf-2026-11-23"


class ParseGamesTest(unittest.TestCase):
    def broken(self, **changes):
        event = copy.deepcopy(real_events(NIGHT)[0])
        event.update(changes)
        return event

    def test_reads_slug_teams_and_start(self):
        [parsed] = parse_games(real_events(NIGHT))
        self.assertEqual(parsed.slug, NIGHT)
        self.assertEqual(parsed.away_team, "Minnesota Vikings")
        self.assertEqual(parsed.home_team, "San Francisco 49ers")
        self.assertEqual(parsed.start, at("2026-11-23 01:20"))

    def test_child_events_are_not_games(self):
        events = real_events(NIGHT, f"{NIGHT}-player-props", f"{NIGHT}-first-td-scorer")
        self.assertEqual([g.slug for g in parse_games(events)], [NIGHT])

    def test_home_and_away_come_from_ordering_not_position(self):
        teams = real_events(NIGHT)[0]["teams"][::-1]
        [parsed] = parse_games([self.broken(teams=teams)])
        self.assertEqual((parsed.away_team, parsed.home_team), ("Minnesota Vikings", "San Francisco 49ers"))

    def test_an_event_repeated_across_pages_counts_once(self):
        self.assertEqual(len(parse_games(real_events(NIGHT, NIGHT))), 1)

    def test_event_without_a_game_id_still_counts(self):
        # 81 real NFL games in 2025 had no gameId.
        self.assertEqual(len(parse_games([self.broken(gameId=None)])), 1)

    def test_closed_event_still_counts(self):
        self.assertEqual(len(parse_games([self.broken(closed=True)])), 1)

    def test_unusable_events_are_skipped_without_losing_the_good_one(self):
        vikings, niners = real_events(NIGHT)[0]["teams"]
        cases = {
            "no slug": {"slug": None},
            "empty slug": {"slug": ""},
            "no start": {"startTime": None},
            "start is not a date": {"startTime": "soon"},
            "start has no timezone": {"startTime": "2026-11-23T01:20:00"},
            "teams is null": {"teams": None},
            "one team": {"teams": [vikings]},
            "three teams": {"teams": [vikings, niners, niners]},
            "no ordering": {"teams": [{"name": "A"}, {"name": "B"}]},
            "both home": {"teams": [niners, niners]},
            "blank name": {"teams": [vikings, {"name": "", "ordering": "home"}]},
        }
        good = real_events("nfl-mia-buf-2026-11-22")[0]
        for label, changes in cases.items():
            with self.subTest(label):
                games = parse_games([self.broken(**changes), good])
                self.assertEqual([g.slug for g in games], ["nfl-mia-buf-2026-11-22"])

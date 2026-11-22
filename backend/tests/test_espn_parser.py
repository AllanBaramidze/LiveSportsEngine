import unittest
from unittest.mock import patch

from src.client.espn.parser import parse_scoreboard
from tests.helpers import at, load


class ParseScoreboardTest(unittest.TestCase):
    def parse(self):
        # The parser is documented as pure: any connection attempt fails the test.
        with patch("socket.socket.connect", side_effect=AssertionError("parser used the network")):
            return parse_scoreboard(load("espn_scoreboard_nfl.json"), "nfl", "football")

    def test_parses_without_the_network(self):
        [parsed] = self.parse()
        self.assertEqual(parsed.away_team, "Minnesota Vikings")
        self.assertEqual(parsed.home_team, "San Francisco 49ers")
        self.assertEqual(parsed.date, at("2026-11-23 01:20"))

    def test_does_not_produce_a_slug(self):
        [parsed] = self.parse()
        self.assertNotIn("poly_slug", parsed.model_dump())

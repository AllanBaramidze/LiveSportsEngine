"""
Getting the right Polymarket slug from the team names lookup, 1
"""
from src.client.polymarket.polymarket_utils import get_match_abbr


if __name__ == "__main__":
    home, away = get_match_abbr("Toronto Raptors", "New York Knicks", "nba")
    print(f"{home} vs {away}")

"""Orchestrates an ESPN ingest: fetch -> parse -> store.

This is the only layer that knows about both ESPN and the database. It owns the
transaction (the commit), which keeps the client, parser and repository single-purpose.
"""

import asyncio
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from src.client.espn.espn_client import EspnClient
from src.client.espn.parser import parse_observations, parse_scoreboard, parse_state
from src.database.database import SessionLocal
from src.database.models import Match
from src.database.repositories import espn_observations, matches
from src.schemas.match import MatchCreate

LEAGUES = [("football", "nfl"), ("baseball", "mlb"), ("basketball", "nba")]


def date_range(start: date, end: date) -> list[date]:
    """Every day from start to end, inclusive."""
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]

async def fetch_league(espn: EspnClient, sport: str, league: str, days: Sequence[date]
                       ) -> list[MatchCreate]:
    payloads = await asyncio.gather(
        *(espn.get_scoreboard(sport, league, day) for day in days)
    )
    return [game for payload in payloads for game in parse_scoreboard(payload, league, sport)]


async def ingest_league(espn: EspnClient, sport: str, league: str, days: Sequence[date]) -> int:
    games = await fetch_league(espn, sport, league, days)
    # Each concurrent task opens its own session: an AsyncSession must never be
    # shared between tasks running at the same time.
    async with SessionLocal() as session:
        count = await matches.upsert_matches(session, games)
        await session.commit()
    return count


async def ingest_days(days: Sequence[date], leagues=None) -> dict[str, int | BaseException]:
    """Ingest every league concurrently. One league failing doesn't stop the others."""
    if leagues is None:
        leagues = LEAGUES
    async with EspnClient() as espn:
        results = await asyncio.gather(
            *(ingest_league(espn, sport, league, days) for sport, league in leagues),
            return_exceptions=True,
        )
    return {
        league: result for (_, league), result in zip(leagues, results, strict=True)
    }


async def refresh_statuses(games: Sequence[Match]) -> dict[str, str | BaseException]:
    """Ask ESPN for each game's current state and save any that changed"""
    async with EspnClient() as espn:
        responses = await asyncio.gather(
            *(espn.get_match_status(g.sport, g.league, g.espn_id) for g in games),
            return_exceptions=True,
        )
    changes: dict[str, str | BaseException] = {}
    async with SessionLocal() as session:
        for game, response in zip(games, responses, strict=True):
            if isinstance(response, BaseException):
                changes[game.espn_id] = response
                continue
            state = parse_state(response)
            if state != game.status:
                await matches.update_status(session, game.espn_id, state)
                changes[game.espn_id] = state
        await session.commit()
    return changes

async def fetch_game(espn: EspnClient, game: Match) -> tuple[dict[str, Any], datetime]:
    """Get one game's info and the moment it arrived."""
    data = await espn.get_game_info(game.sport, game.league, game.espn_id)
    return data, datetime.now(UTC)

async def poll_in_game(games: Sequence[Match]) -> dict[str, dict[str, Any] | BaseException]:
    """Fetch each live game's latest reading and status; save new readings and finished games."""
    async with EspnClient() as espn:
        responses = await asyncio.gather(
            *(fetch_game(espn, g) for g in games),
            return_exceptions=True,
        )
    results: dict[str, dict[str, Any] | BaseException] = {}
    async with SessionLocal() as session:
        for game, response in zip(games, responses, strict=True):
            if isinstance(response, BaseException):
                results[game.espn_id] = response
                continue
            data, ingest_time = response

            observation_id = None
            if data["reading"] is not None:
                observation = parse_observations(data, game.espn_id, ingest_time)
                observation_id = await espn_observations.insert_observations(session, observation)

                if (str(observation.home_score), str(observation.away_score)) != (game.home_score, game.away_score):
                    await matches.update_score(session, game.espn_id, observation.home_score, observation.away_score)

            state = parse_state(data["status"])
            if state != game.status:
                await matches.update_status(session, game.espn_id, state)

            results[game.espn_id] = {"observation_id": observation_id, "state": state}
        await session.commit()
    return results

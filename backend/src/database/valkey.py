"""Valkey connection and the per-game reading count.

The client is created inside `main()` (creating it is async: it connects right away)
and passed into every function here, the same way repositories take a session.
"""

from glide import GlideClient, GlideClientConfiguration, NodeAddress

from src.config import settings


def reading_count_key(espn_id: str) -> str:
    """Valkey key holding one game's ESPN reading count, e.g. `espn:reading_count:401872952`."""
    return f"espn:reading_count:{espn_id}"


async def create_valkey() -> GlideClient:
    """Connect to Valkey. The caller closes it with `await client.close()`."""
    config = GlideClientConfiguration([NodeAddress(settings.valkey_host, settings.valkey_port)])
    return await GlideClient.create(config)


async def get_reading_count(client: GlideClient, espn_id: str) -> int | None:
    """Last saved reading count for a game, or None if there isn't one yet."""
    raw = await client.get(reading_count_key(espn_id))
    return int(raw) if raw is not None else None


async def set_reading_count(client: GlideClient, espn_id: str, count: int) -> None:
    """Save a game's reading count. Valkey stores strings, so the int is converted."""
    await client.set(reading_count_key(espn_id), str(count))


async def delete_reading_count(client: GlideClient, espn_id: str) -> None:
    """Forget a game's reading count (used once the game is finished). Missing keys are fine."""
    await client.delete([reading_count_key(espn_id)])
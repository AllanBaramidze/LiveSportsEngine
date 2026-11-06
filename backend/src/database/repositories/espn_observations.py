"""All SQL for the `espn_observations` table lives here.

Every function takes the session as an argument and never commits: the caller
decides where a transaction starts and ends, so several calls can be grouped
into one all-or-nothing commit.
"""


from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import EspnObservation
from src.schemas.espn_observation import EspnObservationCreate

# --Write

async def insert_observations(session: AsyncSession, observation: EspnObservationCreate) -> int | None:
    """Insert one reading, ignoring exact repeats.

    A repeat is a row with the same `espn_id`, `play_id` and probabilities as one already stored
    (the `uq_espn_observations_reading` constraint). The same play with a *changed* probability
    counts as new, which is how ESPN's later corrections are kept.

    Args:
        session: Open session; the caller commits.
        observation: The reading to store.

    Returns:
        The new row's id, or `None` if it was a repeat and nothing was inserted.
    """
    stmt = (
        insert(EspnObservation)
        .values(**observation.model_dump())
        .on_conflict_do_nothing()
        .returning(EspnObservation.id)
    )
    return await session.scalar(stmt)

# --Read
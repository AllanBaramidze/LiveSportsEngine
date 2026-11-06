"""Async SQLAlchemy engine and session factory for Postgres.

Use `SessionLocal` as `async with SessionLocal() as session:`. Never share one session
between tasks that run at the same time; open one per task.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings

# One engine per process: it owns the connection pool.
engine = create_async_engine(settings.database_url, echo=settings.db_echo)

# Factory for sessions. expire_on_commit=False keeps objects usable after commit,
# which matters in async code where lazy-reloading attributes isn't allowed.
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield one session and close it afterwards.

    Shaped for use as a FastAPI dependency. The pollers use `SessionLocal()` directly.
    Callers commit explicitly; nothing is committed here.
    """
    async with SessionLocal() as session:
        yield session

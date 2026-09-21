from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import async_session_factory

# ---------------------------------------------------------------------------
# Redis singleton
# ---------------------------------------------------------------------------
_redis_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Return the shared Redis connection pool."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
    return _redis_pool


async def close_redis() -> None:
    """Close the Redis connection pool (called on shutdown)."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None


# ---------------------------------------------------------------------------
# DB session
# ---------------------------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async SQLAlchemy session, auto-close after use."""
    async with async_session_factory() as session:
        yield session

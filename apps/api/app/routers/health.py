from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.deps import get_db, get_redis

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(
    db: AsyncSession = Depends(get_db),
    redis_client: aioredis.Redis = Depends(get_redis),
):
    """
    Health check — verifies DB and Redis connectivity.
    Returns: {"status": "ok", "db": true, "redis": true}
    """
    # Check DB
    db_ok = False
    try:
        result = await db.execute(text("SELECT 1"))
        db_ok = result.scalar() == 1
    except Exception:
        db_ok = False

    # Check Redis
    redis_ok = False
    try:
        redis_ok = await redis_client.ping()
    except Exception:
        redis_ok = False

    status = "ok" if (db_ok and redis_ok) else "degraded"

    return {
        "status": status,
        "db": db_ok,
        "redis": redis_ok,
    }

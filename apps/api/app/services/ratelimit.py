"""Fixed-window rate limiting on Redis for the public / embedded chat endpoints.

Design notes
- Keys: ``rl:<scope>`` → INCR, EXPIRE on first hit. Cheap, good enough for a demo
  and for the abuse we care about (a bot hammering a publishable key).
- Fail-open: if Redis is unreachable we log and let the request through — the
  assistant must not go down because the limiter did.
- Limits live in Settings so an operator can tune them without a deploy.
"""

import logging
from dataclasses import dataclass

from fastapi import HTTPException, Request

from app.config import settings
from app.deps import get_redis

logger = logging.getLogger(__name__)


@dataclass
class LimitResult:
    allowed: bool
    remaining: int
    retry_after: int  # seconds


async def hit(scope: str, limit: int, window_sec: int) -> LimitResult:
    """Count one hit for ``scope``; return whether it is still within ``limit``."""
    try:
        r = await get_redis()
        key = f"rl:{scope}"
        n = await r.incr(key)
        if n == 1:
            await r.expire(key, window_sec)
        ttl = await r.ttl(key)
        retry_after = ttl if ttl and ttl > 0 else window_sec
        return LimitResult(allowed=n <= limit, remaining=max(limit - n, 0), retry_after=retry_after)
    except Exception as exc:  # Redis down → fail open
        logger.warning("rate limiter unavailable (%s); allowing request", exc)
        return LimitResult(allowed=True, remaining=limit, retry_after=0)


def client_ip(request: Request) -> str:
    """Best-effort client address (first hop of X-Forwarded-For when behind a proxy)."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


def _too_many(result: LimitResult, message: str) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail=message,
        headers={"Retry-After": str(result.retry_after)},
    )


async def enforce_public_limits(app_id, request: Request) -> None:
    """Per (assistant, IP) window + per-assistant daily cap for customer / embedded chat."""
    ip = client_ip(request)
    per_ip = await hit(f"pub:{app_id}:{ip}", settings.PUBLIC_RATE_LIMIT_PER_IP, settings.PUBLIC_RATE_WINDOW_SEC)
    if not per_ip.allowed:
        raise _too_many(per_ip, f"Bạn gửi quá nhiều câu hỏi. Vui lòng thử lại sau {max(per_ip.retry_after // 60, 1)} phút.")
    per_app = await hit(f"pub-day:{app_id}", settings.PUBLIC_RATE_LIMIT_PER_APP_DAY, 24 * 3600)
    if not per_app.allowed:
        raise _too_many(per_app, "Trợ lý đã đạt hạn mức sử dụng trong ngày. Vui lòng liên hệ tổng đài hoặc thử lại vào ngày mai.")


async def enforce_staff_limits(app_id, employee_id) -> None:
    """Lighter guard for logged-in staff: stops runaway loops, not humans."""
    res = await hit(f"staff:{app_id}:{employee_id}", settings.STAFF_RATE_LIMIT_PER_EMPLOYEE, settings.PUBLIC_RATE_WINDOW_SEC)
    if not res.allowed:
        raise _too_many(res, f"Bạn gửi quá nhiều câu hỏi trong thời gian ngắn. Vui lòng thử lại sau {max(res.retry_after // 60, 1)} phút.")

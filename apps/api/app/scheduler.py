"""``python -m app.scheduler`` — fires report schedules and cleans up expired files.

The database is the source of truth. Every tick the ticker claims due rows with
``FOR UPDATE SKIP LOCKED``, queues one job per row on ``querion-jobs`` and moves ``next_run_at``
to the next slot, so two tickers (or a redeploy in the middle of a tick) can never double-fire,
and a ticker that was down skips the missed slots instead of firing them all at once.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

from sqlalchemy import select

logger = logging.getLogger("scheduler")

TICK_SECONDS = int(os.getenv("SCHEDULER_TICK_SECONDS", "30"))
CLEANUP_EVERY_TICKS = max(1, int(os.getenv("SCHEDULER_CLEANUP_TICKS", str(3600 // max(1, TICK_SECONDS)))))
HEARTBEAT_KEY = "scheduler:heartbeat"
HEARTBEAT_TTL = 300
MAX_PER_TICK = 20


async def fire_due_schedules() -> int:
    """Queue every schedule that is due. Returns how many were fired."""
    from app.db import async_session_factory
    from app.models.schedule import Schedule
    from app.models.workflow import Workflow
    from app.services.jobs import enqueue_workflow_run
    from app.services.observability import create_run
    from app.services.scheduling import ScheduleError, next_run_at

    now = datetime.now(timezone.utc)
    fired = 0
    async with async_session_factory() as db:
        rows = (await db.execute(
            select(Schedule)
            .where(Schedule.enabled.is_(True), Schedule.next_run_at.isnot(None), Schedule.next_run_at <= now)
            .order_by(Schedule.next_run_at)
            .limit(MAX_PER_TICK)
            .with_for_update(skip_locked=True)
        )).scalars().all()

        for schedule in rows:
            wf = await db.get(Workflow, schedule.workflow_id)
            try:
                schedule.next_run_at = next_run_at(schedule.cron, schedule.timezone, after=now)
            except ScheduleError as exc:
                logger.error("schedule %s has an invalid cron (%s) — disabling", schedule.id, exc)
                schedule.enabled = False
                continue
            if wf is None:
                logger.error("schedule %s points at a deleted workflow — disabling", schedule.id)
                schedule.enabled = False
                continue

            run = await create_run(db, workflow_id=wf.id, workspace_id=schedule.workspace_id,
                                   channel="scheduled", query=schedule.name)
            run.status = "queued"
            await db.flush()
            try:
                enqueue_workflow_run(run.id, wf.id, dict(schedule.inputs or {}), schedule_id=schedule.id)
            except Exception as exc:
                logger.exception("could not queue schedule %s", schedule.id)
                run.status = "failed"
                run.error = f"Không xếp được hàng đợi: {exc}"
                continue
            schedule.last_run_id = run.id
            schedule.last_enqueued_at = now
            fired += 1
            logger.info("fired schedule %s (%s) → run %s", schedule.id, schedule.name, run.id)
        await db.commit()
    return fired


async def cleanup_expired_artifacts() -> int:
    """Delete report files past their retention date (row + object)."""
    from app.db import async_session_factory
    from app.models.artifact import Artifact
    from app.storage import delete_file

    removed = 0
    async with async_session_factory() as db:
        rows = (await db.execute(
            select(Artifact).where(Artifact.expires_at.isnot(None),
                                   Artifact.expires_at <= datetime.now(timezone.utc)).limit(200)
        )).scalars().all()
        for artifact in rows:
            try:
                delete_file(artifact.storage_key)
            except Exception:
                pass  # object already gone: still drop the row
            await db.delete(artifact)
            removed += 1
        if removed:
            await db.commit()
            logger.info("cleaned up %d expired artifacts", removed)
    return removed


async def cleanup_expired_memories() -> int:
    """Bản ghi nhớ hết hạn tự biến mất, giống tệp báo cáo hết hạn.

    Bộ nhớ không dùng tới nữa mà vẫn nằm đó là vừa tốn ngữ cảnh vừa là dữ liệu cá nhân giữ quá
    thời hạn đã công bố với cán bộ.
    """
    from app.db import async_session_factory
    from app.services.memory import purge_expired

    async with async_session_factory() as db:
        removed = await purge_expired(db)
        if removed:
            await db.commit()
            logger.info("cleaned up %d expired memories", removed)
        return removed


async def _heartbeat() -> None:
    """Let the admin UI tell "scheduler is down" from "nothing is due"."""
    try:
        import redis.asyncio as aioredis

        from app.config import settings
        client = aioredis.from_url(settings.REDIS_URL)
        await client.set(HEARTBEAT_KEY, datetime.now(timezone.utc).isoformat(), ex=HEARTBEAT_TTL)
        await client.aclose()
    except Exception:
        logger.debug("heartbeat failed", exc_info=True)


async def run_forever() -> None:
    logger.info("scheduler started — tick %ss", TICK_SECONDS)
    ticks = 0
    while True:
        try:
            await fire_due_schedules()
            await _heartbeat()
            if ticks % CLEANUP_EVERY_TICKS == 0:
                await cleanup_expired_artifacts()
                await cleanup_expired_memories()
        except Exception:
            logger.exception("scheduler tick failed")  # never let one bad tick kill the loop
        ticks += 1
        await asyncio.sleep(TICK_SECONDS)


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("SCHEDULER_LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    for noisy in ("httpcore", "httpx", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()

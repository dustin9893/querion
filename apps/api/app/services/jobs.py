"""Enqueuing background work on the ``querion-jobs`` RQ queue."""

from __future__ import annotations

import logging
from typing import Any

import redis
from rq import Queue

from app.config import settings

logger = logging.getLogger(__name__)

JOBS_QUEUE = "querion-jobs"
RUN_WORKFLOW_TASK = "app.jobs.tasks.run_workflow_job"
JOB_TIMEOUT = 15 * 60  # a report may call several systems and the LLM


def jobs_queue() -> Queue:
    return Queue(JOBS_QUEUE, connection=redis.from_url(settings.REDIS_URL))


def enqueue_workflow_run(run_id: Any, workflow_id: Any, inputs: dict[str, Any] | None,
                         *, schedule_id: Any = None) -> str:
    """Queue a workflow run. Returns the RQ job id."""
    job = jobs_queue().enqueue(
        RUN_WORKFLOW_TASK,
        str(run_id), str(workflow_id), inputs or {},
        str(schedule_id) if schedule_id else None,
        job_timeout=JOB_TIMEOUT,
        result_ttl=3600,
        failure_ttl=7 * 24 * 3600,
    )
    logger.info("queued workflow run %s (job %s)", run_id, job.id)
    return job.id

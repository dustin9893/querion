"""``python -m app.jobs.worker`` — RQ worker for report / form jobs.

Runs from the API image (it needs the workflow runtime, tools, MinIO and providers). Indexing
keeps its own lighter worker in apps/worker.
"""

import logging
import os
import sys

import redis
from rq import Worker

from app.config import settings
from app.services.jobs import JOBS_QUEUE

if sys.platform == "darwin":  # macOS fork() + Obj-C runtime, same as the indexing worker
    os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")

logging.basicConfig(
    level=getattr(logging, os.getenv("JOBS_LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
for noisy in ("httpcore", "httpx", "urllib3", "openai", "rq.job", "rq.queue"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
logger = logging.getLogger("jobs")


def main() -> None:
    logger.info("jobs worker starting — queue=%s redis=%s", JOBS_QUEUE, settings.REDIS_URL)
    Worker([JOBS_QUEUE], connection=redis.from_url(settings.REDIS_URL)).work(with_scheduler=False)


if __name__ == "__main__":
    main()

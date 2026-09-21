"""RQ worker entry point."""

import os
import sys
import logging
import redis
from rq import Worker

# Fix macOS fork() crash with Obj-C runtime (no-op on Linux/Windows)
if sys.platform == "darwin":
    os.environ["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"

# Load .env from project root
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

from worker.config import REDIS_URL, QUEUE_NAME
from worker.callbacks import handle_job_failure

# WORKER_LOG_LEVEL=DEBUG is opt-in. pdfminer (used by pdfplumber) logs several hundred
# thousand DEBUG lines per PDF, which made a 1 MB file take ~35 s to parse instead of ~3 s.
LOG_LEVEL = os.getenv("WORKER_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
for noisy in ("pdfminer", "pdfplumber", "httpcore", "httpx", "urllib3", "openai", "rq.job", "rq.queue"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
logger = logging.getLogger("worker")

if __name__ == "__main__":
    logger.info(f"REDIS_URL: {REDIS_URL}")
    logger.info(f"Queue: {QUEUE_NAME}")
    logger.info(f"OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES")

    conn = redis.from_url(REDIS_URL)
    worker = Worker(
        [QUEUE_NAME],
        connection=conn,
        exception_handlers=[handle_job_failure],
    )
    logger.info("Worker started, waiting for jobs...")
    worker.work(logging_level=LOG_LEVEL)

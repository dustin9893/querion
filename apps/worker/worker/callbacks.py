"""RQ exception handler — mark documents as failed when a job crashes."""

import logging
from datetime import datetime, timezone
from sqlalchemy import text as sql_text

from worker.db import get_db

logger = logging.getLogger(__name__)


def handle_job_failure(job, exc_type, exc_value, traceback):
    """Called by RQ when any job raises an exception (including import errors).

    Extracts document_id from job args and marks it as failed in DB.
    """
    try:
        # job.args[0] is the document_id string
        if job.args:
            document_id = job.args[0]
            logger.error(f"Job {job.id} for document {document_id} failed: {exc_value}")

            db = get_db()
            try:
                db.execute(
                    sql_text("""
                        UPDATE documents
                        SET status = 'failed',
                            error_message = :error,
                            updated_at = :now
                        WHERE id = :id::uuid AND status = 'indexing'
                    """),
                    {
                        "error": str(exc_value)[:500],
                        "now": datetime.now(timezone.utc),
                        "id": document_id,
                    },
                )
                db.commit()
                logger.info(f"Document {document_id} marked as failed")
            finally:
                db.close()
    except Exception as e:
        logger.exception(f"Failed to handle job failure callback: {e}")

    return True  # Let RQ continue with its default failure handling

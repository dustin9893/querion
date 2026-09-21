"""Observability — every answer the platform produces is a Run with node-level RunSteps.

Channels:
  staff       — employee portal (/v1/staff/apps/{id}/chat)
  customer    — public customer page (/v1/public/assistants/{id}/chat)
  admin_test  — admin dataset chat or workflow test-run
  embed       — chat widget embedded on an allowed third-party website (client_origin set)

Runs are the backbone of the Compliance audit log (routers/audit.py).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.run import Run, RunStep

PREVIEW_LEN = 500


def _preview(text: str | None) -> str | None:
    if not text:
        return None
    from app.services.pii import mask_pii  # local import: avoid cycles
    text = " ".join(mask_pii(text).text.split())
    return text[:PREVIEW_LEN]


async def create_run(
    db: AsyncSession,
    *,
    app_id: uuid.UUID | None = None,
    workflow_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    employee_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    channel: str = "staff",
    query: str | None = None,
    client_origin: str | None = None,
) -> Run:
    """Create a run row when an answer starts being produced (flushed, not committed)."""
    run = Run(
        app_id=app_id,
        workflow_id=workflow_id,
        conversation_id=conversation_id,
        workspace_id=workspace_id,
        employee_id=employee_id,
        user_id=user_id,
        channel=channel,
        client_origin=(client_origin or None),
        query_preview=_preview(query),
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()  # get the id without committing
    return run


async def log_step_start(
    db: AsyncSession,
    *,
    run_id: uuid.UUID,
    node_id: str,
    node_type: str,
    input_data: dict | None = None,
) -> RunStep:
    """Log the start of a node / pipeline stage."""
    step = RunStep(
        run_id=run_id,
        node_id=node_id,
        node_type=node_type,
        started_at=datetime.now(timezone.utc),
        input_json=input_data,
    )
    db.add(step)
    await db.flush()
    return step


async def log_step_end(
    step: RunStep,
    *,
    output_data: dict | None = None,
) -> None:
    """Log the completion of a node / pipeline stage."""
    step.ended_at = datetime.now(timezone.utc)
    step.output_json = output_data


async def complete_run(
    run: Run,
    *,
    status: str = "completed",
    answer: str | None = None,
    error: str | None = None,
) -> None:
    """Mark a run as finished and record latency + previews."""
    run.status = status
    run.ended_at = datetime.now(timezone.utc)
    if answer is not None:
        run.answer_preview = _preview(answer)
    if error:
        run.error = error[:2000]
    if run.started_at:
        run.latency_ms = int((run.ended_at - run.started_at).total_seconds() * 1000)


def sources_summary(sources: list[dict], limit: int = 5) -> list[dict]:
    """Compact citation list stored in step output (no full chunk text)."""
    out = []
    for s in sources[:limit]:
        out.append({
            "filename": s.get("filename"),
            "section": s.get("section"),
            "version": s.get("version"),
            "score": s.get("score"),
            "chunk_id": s.get("chunk_id"),
        })
    return out

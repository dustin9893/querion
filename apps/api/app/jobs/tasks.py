"""RQ tasks. Sync entry points that drive the async runtime on their own event loop."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


def run_workflow_job(run_id: str, workflow_id: str, inputs: dict[str, Any] | None = None,
                     schedule_id: str | None = None) -> dict[str, Any]:
    """Execute a workflow for an existing `runs` row (created by the API or the scheduler)."""
    return asyncio.run(_run_workflow(run_id, workflow_id, inputs or {}, schedule_id))


async def _run_workflow(run_id: str, workflow_id: str, inputs: dict[str, Any],
                        schedule_id: str | None) -> dict[str, Any]:
    from app.db import async_session_factory, engine
    from app.models.run import Run
    from app.models.workflow import Workflow
    from app.services.observability import complete_run
    from app.services.workflow_runtime import run_workflow

    try:
        async with async_session_factory() as db:
            run = await db.get(Run, uuid.UUID(run_id))
            wf = await db.get(Workflow, uuid.UUID(workflow_id))
            if run is None or wf is None:
                logger.error("run %s or workflow %s no longer exists", run_id, workflow_id)
                return {"status": "missing"}
            run.status = "running"
            await db.commit()

            try:
                result = await run_workflow(
                    db, wf.graph_json, query=str(inputs.get("_query") or wf.name),
                    inputs=inputs, run=run, workspace_id=wf.workspace_id,
                    schedule_id=uuid.UUID(schedule_id) if schedule_id else None,
                )
            except Exception as exc:
                logger.exception("workflow run %s failed", run_id)
                await complete_run(run, status="failed", error=f"{type(exc).__name__}: {exc}")
                await db.commit()
                return {"status": "failed", "error": str(exc)}

            artifacts = [a for a in result.get("artifacts", []) if not a.get("error")]
            errors = [a["error"] for a in result.get("artifacts", []) if a.get("error")]
            await complete_run(
                run,
                status="failed" if (errors and not artifacts) else "completed",
                answer=result.get("answer"),
                error="; ".join(errors) if errors else None,
            )
            await db.commit()
            return {"status": run.status, "artifacts": artifacts}
    finally:
        # Each job runs on its own event loop, so connections must not be reused across jobs.
        await engine.dispose()

"""Pausing an answer for a human decision, and continuing it afterwards.

When a tool marked ``requires_approval`` is about to run, the agent stops and the API
records a ``tool_approvals`` row. The agent's own state lives in the LangGraph checkpointer
under ``thread_id = run.id``; this row is the compliance record (who decided, when, on what
arguments) and the handle the UI posts back to.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app import App
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.run import Run
from app.models.tool import Tool, ToolApproval
from app.services.chat import AnswerCollector
from app.services.observability import complete_run

PENDING = "pending"


async def record_pending(
    db: AsyncSession, *, run: Run, conversation_id: uuid.UUID | None, pending: dict,
) -> ToolApproval:
    """Persist "this answer is waiting for a decision" and park the run."""
    tool = None
    slug = (pending.get("tool") or "")[:128]
    if slug:
        tool = (await db.execute(select(Tool).where(Tool.slug == slug.split("__")[0]))).scalars().first()
    approval = ToolApproval(
        run_id=run.id, conversation_id=conversation_id, tool_id=tool.id if tool else None,
        tool_slug=slug, args_preview=json.dumps(pending.get("args") or {}, ensure_ascii=False)[:1000],
        decision=PENDING,
    )
    db.add(approval)
    run.status = "waiting"
    await db.commit()
    await db.refresh(approval)
    return approval


async def load_pending(db: AsyncSession, approval_id: str) -> ToolApproval | None:
    try:
        approval = await db.get(ToolApproval, uuid.UUID(approval_id))
    except ValueError:
        return None
    return approval if approval and approval.decision == PENDING else None


async def mark_decided(
    db: AsyncSession, approval: ToolApproval, *, approve: bool,
    employee_id: uuid.UUID | None = None, user_id: uuid.UUID | None = None,
) -> None:
    approval.decision = "approved" if approve else "rejected"
    approval.employee_id = employee_id
    approval.user_id = user_id
    approval.decided_at = datetime.now(timezone.utc)
    await db.commit()


async def continue_after_decision(
    db: AsyncSession, *, app: App, approval: ToolApproval, approve: bool, channel: str,
):
    """SSE frames for the rest of the answer, saving the message and closing the run.

    Yields the same envelope the chat endpoints use, so the front-end needs no special case
    beyond posting the decision.
    """
    from app.services.agent_runtime import resume_agent_stream

    run = await db.get(Run, approval.run_id)
    conv = await db.get(Conversation, approval.conversation_id) if approval.conversation_id else None
    collector = AnswerCollector()

    async for frame in resume_agent_stream(
        db, app, collector, thread_id=str(approval.run_id), approved=approve, channel=channel, run=run,
    ):
        yield frame

    yield "data: [DONE]\n\n"

    if run is not None:
        await complete_run(
            run,
            status="blocked" if collector.blocked else ("completed" if collector.answer else "failed"),
            answer=collector.answer or None, error=collector.error,
        )
    if conv is not None and collector.answer:
        msg = Message(conversation_id=conv.id, role="assistant", content=collector.answer,
                      sources=collector.sources[:5] if collector.sources else None,
                      run_id=approval.run_id)
        db.add(msg)
        conv.updated_at = datetime.now(timezone.utc)
        await db.commit()
        yield f"data: {json.dumps({'type': 'message_saved', 'message_id': str(msg.id), 'run_id': str(approval.run_id)}, ensure_ascii=False)}\n\n"
    else:
        await db.commit()

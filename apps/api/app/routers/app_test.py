"""Admin test console ("Thử nghiệm hỏi đáp"): chat with any assistant of the active unit.

Same pipeline as the staff and customer channels — `app_answer_stream` (workflow / RAG /
plain LLM), PII masking, output guard, audit run — but authenticated with the admin JWT and
the `X-Workspace-Id` header, so an admin can try an assistant before publishing it and see
exactly what users will get. Conversations carry `user_id` (never `employee_id`), which keeps
them out of the staff portal and of the customer endpoints. Runs are logged with channel
`admin_test`.
"""

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.usage import UsageScope
from app.deps import get_db
from app.auth.deps import require_ws_role, WorkspaceContext
from app.models.user_workspace import WsRole
from app.models.app import App
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.feedback import MessageFeedback
from app.services.chat import answer_for_app, generate_title, AnswerCollector
from app.services.tools.approvals import continue_after_decision, load_pending, mark_decided, record_pending
from app.services.observability import create_run, complete_run
from app.services.pii import mask_pii, notice_for

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/apps", tags=["apps-test"])

MAX_MESSAGE_CHARS = 2000


class TestChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CHARS)
    conversation_id: str | None = None


class TestMessage(BaseModel):
    id: str
    role: str
    content: str
    sources: list | None
    created_at: str
    run_id: str | None = None
    feedback: str | None = None


class TestFeedbackRequest(BaseModel):
    rating: str
    reason: str | None = Field(None, max_length=500)


async def _load_app(db: AsyncSession, app_id: str, ws_ctx: WorkspaceContext) -> App:
    try:
        app = await db.get(App, uuid.UUID(app_id))
    except ValueError:
        app = None
    if not app or app.workspace_id != ws_ctx.workspace_id:
        raise HTTPException(status_code=404, detail="App not found")
    return app


async def _own_conversation(db: AsyncSession, conversation_id: str, app: App, ws_ctx: WorkspaceContext) -> Conversation | None:
    try:
        conv_id = uuid.UUID(conversation_id)
    except ValueError:
        return None
    return (await db.execute(select(Conversation).where(
        Conversation.id == conv_id,
        Conversation.app_id == app.id,
        Conversation.user_id == ws_ctx.user.id,
    ))).scalar_one_or_none()


@router.get("/{app_id}/test-conversations/{conversation_id}/messages", response_model=list[TestMessage])
async def get_test_messages(
    app_id: str,
    conversation_id: str,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    """Reload the admin's own test conversation (id kept in the browser)."""
    app = await _load_app(db, app_id, ws_ctx)
    conv = await _own_conversation(db, conversation_id, app, ws_ctx)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    msgs = (await db.execute(select(Message).where(Message.conversation_id == conv.id)
                             .order_by(Message.created_at))).scalars().all()
    fb_rows = await db.execute(select(MessageFeedback.message_id, MessageFeedback.rating)
                               .where(MessageFeedback.message_id.in_([m.id for m in msgs] or [uuid.uuid4()])))
    fb = {mid: rating for mid, rating in fb_rows.all()}
    return [TestMessage(id=str(m.id), role=m.role, content=m.content, sources=m.sources,
                        created_at=m.created_at.isoformat(), run_id=str(m.run_id) if m.run_id else None,
                        feedback=fb.get(m.id)) for m in msgs]


@router.post("/{app_id}/test-chat")
async def test_chat(
    app_id: str,
    body: TestChatRequest,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    """Streamed answer for an admin trying an assistant (published or not). Same SSE envelope
    as the staff/customer chat; the run is audited with channel `admin_test`."""
    app = await _load_app(db, app_id, ws_ctx)
    pii = mask_pii(body.message)
    question = pii.text

    if body.conversation_id:
        conv = await _own_conversation(db, body.conversation_id, app, ws_ctx)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conv = Conversation(workspace_id=app.workspace_id, app_id=app.id,
                            user_id=ws_ctx.user.id, title="Thử nghiệm hỏi đáp")
        db.add(conv)
        await db.commit()
        await db.refresh(conv)

    user_msg = Message(conversation_id=conv.id, role="user", content=question)
    db.add(user_msg)
    await db.commit()

    count = (await db.execute(select(func.count()).select_from(Message)
                              .where(Message.conversation_id == conv.id))).scalar() or 0
    is_first = count == 1
    history = [
        {"role": m.role, "content": m.content}
        for m in (await db.execute(select(Message).where(Message.conversation_id == conv.id)
                                   .order_by(Message.created_at))).scalars().all()
        if m.id != user_msg.id
    ]

    run = await create_run(
        db, app_id=app.id, workflow_id=app.workflow_id, conversation_id=conv.id,
        workspace_id=app.workspace_id, user_id=ws_ctx.user.id, channel="admin_test", query=question,
    )
    await db.commit()

    async def generate():
        yield f"data: {json.dumps({'type': 'conversation_id', 'conversation_id': str(conv.id)})}\n\n"
        if pii.found:
            yield f"data: {json.dumps({'type': 'notice', 'content': notice_for(pii.kinds), 'masked': pii.kinds})}\n\n"
        collector = AnswerCollector()
        try:
            async for chunk in answer_for_app(db, app, question, history, collector, run=run, channel="admin_test"):
                yield chunk
        except Exception as e:
            logger.exception("admin test chat failed (run %s)", run.id)
            collector.error = str(e)
            yield f"data: {json.dumps({'type': 'error', 'content': 'Hệ thống đang gặp lỗi, vui lòng thử lại sau.'})}\n\n"
        yield "data: [DONE]\n\n"

        if collector.pending_approval:
            approval = await record_pending(db, run=run, conversation_id=conv.id, pending=collector.pending_approval)
            yield f"data: {json.dumps({'type': 'tool_approval', 'approval_id': str(approval.id), 'tool': collector.pending_approval.get('tool'), 'label': collector.pending_approval.get('label'), 'args': collector.pending_approval.get('args') or {}}, ensure_ascii=False)}\n\n"
            return

        await complete_run(run, status="blocked" if collector.blocked else ("completed" if collector.answer else "failed"),
                           answer=collector.answer or None, error=collector.error)
        if collector.answer:
            assistant_msg = Message(conversation_id=conv.id, role="assistant", content=collector.answer,
                                    sources=collector.sources[:5] if collector.sources else None, run_id=run.id)
            db.add(assistant_msg)
            conv.updated_at = datetime.now(timezone.utc)
            await db.commit()
            yield f"data: {json.dumps({'type': 'message_saved', 'message_id': str(assistant_msg.id), 'run_id': str(run.id)})}\n\n"
        else:
            await db.commit()

        if collector.answer and is_first:
            try:
                title = await generate_title(db, question, collector.answer, usage=UsageScope.of_run(run))
                if title:
                    conv.title = title
                    await db.commit()
            except Exception:
                pass

    return StreamingResponse(generate(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no",
    })


class TestApprovalDecision(BaseModel):
    approve: bool


@router.post("/{app_id}/test-tool-approvals/{approval_id}")
async def decide_test_tool_approval(
    app_id: str,
    approval_id: str,
    body: TestApprovalDecision,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject a tool the assistant wants to run, from the admin test console."""
    app = await _load_app(db, app_id, ws_ctx)
    approval = await load_pending(db, approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Yêu cầu duyệt không tồn tại hoặc đã được xử lý")
    conv = await db.get(Conversation, approval.conversation_id) if approval.conversation_id else None
    if not conv or conv.app_id != app.id or conv.user_id != ws_ctx.user.id:
        raise HTTPException(status_code=404, detail="Yêu cầu duyệt không thuộc về bạn")

    await mark_decided(db, approval, approve=body.approve, user_id=ws_ctx.user.id)
    return StreamingResponse(
        continue_after_decision(db, app=app, approval=approval, approve=body.approve, channel="admin_test"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/{app_id}/test-messages/{message_id}/feedback")
async def test_feedback(
    app_id: str,
    message_id: str,
    body: TestFeedbackRequest,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    """👍 / 👎 on a test answer — lands in the audit log like any other rating."""
    if body.rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="rating must be 'up' or 'down'")
    app = await _load_app(db, app_id, ws_ctx)
    try:
        msg_id = uuid.UUID(message_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Message not found")
    msg = (await db.execute(
        select(Message).join(Conversation, Conversation.id == Message.conversation_id).where(
            Message.id == msg_id, Message.role == "assistant",
            Conversation.app_id == app.id, Conversation.user_id == ws_ctx.user.id,
        )
    )).scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    fb = (await db.execute(select(MessageFeedback).where(MessageFeedback.message_id == msg.id))).scalar_one_or_none()
    reason = (body.reason or "").strip() or None
    if fb:
        fb.rating, fb.reason = body.rating, reason
    else:
        db.add(MessageFeedback(message_id=msg.id, run_id=msg.run_id, rating=body.rating, reason=reason))
    await db.commit()
    return {"message_id": str(msg.id), "rating": body.rating, "reason": reason}

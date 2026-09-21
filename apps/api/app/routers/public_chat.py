"""Public (customer-facing) assistant chat — authenticated by the assistant's api_key.

No login. Two front-ends use these endpoints, both served from our own web origin:
  * the full page   /kh/{app_id}#k=<api_key>
  * the embed page  /embed/{app_id}#k=<api_key>&o=<host origin>  (inside an iframe on a
    third-party website; the loader is /widget.js)

The key travels in the ``X-App-Key`` header. Only ``audience="customer"`` assistants
can chat here; staff assistants may only read their embed metadata (they chat via
/v1/staff/* with a JWT). Embedded requests add ``X-Embed-Origin`` so the audit log
knows which website the question came from; that origin must be on the assistant's
allowlist and embedding must be enabled. Browsers enforce the allowlist for real via
the CSP ``frame-ancestors`` header on /embed (see web/src/proxy.ts).
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.usage import UsageScope
from app.deps import get_db
from app.models.app import App
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.feedback import MessageFeedback
from app.services.chat import answer_for_app, generate_title, AnswerCollector
from app.services.embed import effective_widget, normalize_origin
from app.services.observability import create_run, complete_run
from app.services.ratelimit import enforce_public_limits
from app.services.pii import mask_pii, notice_for
from app.services.branding import logo_url
from app.storage import download_file

router = APIRouter(prefix="/v1/public/assistants", tags=["public"])

MAX_MESSAGE_CHARS = 2000


class PublicAssistantInfo(BaseModel):
    id: str
    name: str
    description: str | None
    workspace_id: str
    logo_url: str | None = None


class EmbedConfig(BaseModel):
    id: str
    name: str
    description: str | None
    audience: str
    embed_enabled: bool
    allowed_origins: list[str]
    widget: dict
    logo_url: str | None = None


class PublicChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CHARS)
    conversation_id: str | None = None


class PublicMessage(BaseModel):
    id: str
    role: str
    content: str
    sources: list | None
    created_at: str


class PublicFeedbackRequest(BaseModel):
    rating: str
    reason: str | None = Field(None, max_length=500)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

async def _load_app_by_key(app_id: str, x_app_key: str, db: AsyncSession) -> App:
    try:
        app_uuid = uuid.UUID(app_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Assistant not found")
    app = await db.get(App, app_uuid)
    if not app or not app.is_published or app.api_key != x_app_key:
        raise HTTPException(status_code=404, detail="Assistant not found")
    return app


async def require_public_app(
    app_id: str,
    x_app_key: str = Header(..., alias="X-App-Key"),
    db: AsyncSession = Depends(get_db),
) -> App:
    """Customer-facing assistant: full chat access with the publishable key."""
    app = await _load_app_by_key(app_id, x_app_key, db)
    if app.audience != "customer":
        raise HTTPException(status_code=404, detail="Assistant not found")
    return app


async def require_embeddable_app(
    app_id: str,
    x_app_key: str = Header(..., alias="X-App-Key"),
    db: AsyncSession = Depends(get_db),
) -> App:
    """Any published assistant (staff or customer): metadata only, for the embed page."""
    return await _load_app_by_key(app_id, x_app_key, db)


def embed_origin_or_403(app: App, request: Request) -> str | None:
    """Read X-Embed-Origin; when present it must match the assistant's allowlist.

    Returns the normalized origin, or None when the request is not from an embed.
    """
    raw = request.headers.get("x-embed-origin")
    if not raw:
        return None
    try:
        origin = normalize_origin(raw)
    except HTTPException:
        raise HTTPException(status_code=403, detail="Origin nhúng không hợp lệ")
    if not app.embed_enabled or origin not in (app.allowed_origins or []):
        raise HTTPException(status_code=403, detail="Website này không được phép nhúng trợ lý")
    return origin


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

@router.get("/{app_id}", response_model=PublicAssistantInfo)
async def get_public_assistant(app: App = Depends(require_public_app)):
    return PublicAssistantInfo(id=str(app.id), name=app.name, description=app.description,
                               workspace_id=str(app.workspace_id), logo_url=logo_url(app))


@router.get("/{app_id}/embed-config", response_model=EmbedConfig)
async def get_embed_config(app: App = Depends(require_embeddable_app)):
    """Everything the /embed page needs to render and to verify its parent origin."""
    return EmbedConfig(
        id=str(app.id), name=app.name, description=app.description, audience=app.audience,
        embed_enabled=bool(app.embed_enabled), allowed_origins=list(app.allowed_origins or []),
        widget=effective_widget(app.name, app.widget_config),
        logo_url=logo_url(app),
    )


@router.get("/{app_id}/logo")
async def get_logo(app_id: str, db: AsyncSession = Depends(get_db)):
    """The assistant's logo. No key: a logo is shown on public websites anyway, and only
    assistants that uploaded one have it. Cached for a day — the URL carries ?v=<upload time>
    (see services/branding.logo_url) so a new upload is never masked by a stale cache."""
    try:
        app = await db.get(App, uuid.UUID(app_id))
    except ValueError:
        app = None
    if not app or not app.logo_key:
        raise HTTPException(status_code=404, detail="No logo")
    try:
        data = await asyncio.to_thread(download_file, app.logo_key)
    except Exception:
        raise HTTPException(status_code=404, detail="No logo")
    content_type = app.logo_content_type or "application/octet-stream"
    headers = {
        "Cache-Control": "public, max-age=86400",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": "inline; filename=logo",
    }
    if content_type == "image/svg+xml":
        # An SVG opened directly in a tab must never run script or load anything from anywhere.
        headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
    return Response(content=data, media_type=content_type, headers=headers)


@router.get("/{app_id}/frame-ancestors")
async def get_frame_ancestors(app_id: str, db: AsyncSession = Depends(get_db)):
    """Origins allowed to frame /embed/{app_id}. No key: consumed by the web proxy to build
    the CSP header; the list is not secret (it is visible to anyone who can load the embed)."""
    try:
        app = await db.get(App, uuid.UUID(app_id))
    except ValueError:
        app = None
    if not app or not app.is_published or not app.embed_enabled or not app.allowed_origins:
        raise HTTPException(status_code=404, detail="Not embeddable")
    return {"allowed_origins": list(app.allowed_origins)}


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

@router.get("/{app_id}/conversations/{conversation_id}/messages", response_model=list[PublicMessage])
async def get_public_messages(
    conversation_id: str,
    app: App = Depends(require_public_app),
    db: AsyncSession = Depends(get_db),
):
    """Reload a customer's conversation (id kept in the browser's localStorage)."""
    conv = (await db.execute(select(Conversation).where(
        Conversation.id == uuid.UUID(conversation_id),
        Conversation.app_id == app.id,
        Conversation.employee_id.is_(None), Conversation.user_id.is_(None),
    ))).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    msgs = (await db.execute(select(Message).where(Message.conversation_id == conv.id)
                             .order_by(Message.created_at))).scalars().all()
    return [PublicMessage(id=str(m.id), role=m.role, content=m.content, sources=m.sources,
                          created_at=m.created_at.isoformat()) for m in msgs]


@router.post("/{app_id}/chat")
async def public_chat(
    body: PublicChatRequest,
    request: Request,
    app: App = Depends(require_public_app),
    db: AsyncSession = Depends(get_db),
):
    """Streamed answer for a customer. Same SSE envelope as the staff portal."""
    embed_origin = embed_origin_or_403(app, request)
    await enforce_public_limits(app.id, request)
    # PII never reaches the LLM provider, the conversation table or the audit log
    pii = mask_pii(body.message)
    question = pii.text

    if body.conversation_id:
        conv = (await db.execute(select(Conversation).where(
            Conversation.id == uuid.UUID(body.conversation_id),
            Conversation.app_id == app.id,
            Conversation.employee_id.is_(None), Conversation.user_id.is_(None),
        ))).scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conv = Conversation(workspace_id=app.workspace_id,
                            employee_id=None, app_id=app.id, title="Hội thoại khách hàng")
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
        workspace_id=app.workspace_id, channel="embed" if embed_origin else "customer",
        client_origin=embed_origin, query=question,
    )
    await db.commit()

    async def generate():
        yield f"data: {json.dumps({'type': 'conversation_id', 'conversation_id': str(conv.id)})}\n\n"
        if pii.found:
            yield f"data: {json.dumps({'type': 'notice', 'content': notice_for(pii.kinds), 'masked': pii.kinds})}\n\n"
        collector = AnswerCollector()
        try:
            async for chunk in answer_for_app(db, app, question, history, collector, run=run,
                                              channel="embed" if embed_origin else "customer"):
                yield chunk
        except Exception as e:
            collector.error = str(e)
            yield f"data: {json.dumps({'type': 'error', 'content': 'Hệ thống đang bận, vui lòng thử lại sau.'})}\n\n"
        yield "data: [DONE]\n\n"

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


@router.post("/{app_id}/messages/{message_id}/feedback")
async def public_feedback(
    message_id: str,
    body: PublicFeedbackRequest,
    request: Request,
    app: App = Depends(require_public_app),
    db: AsyncSession = Depends(get_db),
):
    """Anonymous 👍 / 👎 from a customer."""
    embed_origin_or_403(app, request)
    if body.rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="rating must be 'up' or 'down'")
    msg = (await db.execute(
        select(Message).join(Conversation, Conversation.id == Message.conversation_id).where(
            Message.id == uuid.UUID(message_id), Message.role == "assistant",
            Conversation.app_id == app.id, Conversation.employee_id.is_(None), Conversation.user_id.is_(None),
        )
    )).scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    fb = (await db.execute(select(MessageFeedback).where(MessageFeedback.message_id == msg.id))).scalar_one_or_none()
    if fb:
        fb.rating, fb.reason = body.rating, (body.reason or "").strip() or None
    else:
        db.add(MessageFeedback(message_id=msg.id, run_id=msg.run_id, rating=body.rating,
                               reason=(body.reason or "").strip() or None))
    await db.commit()
    return {"message_id": str(msg.id), "rating": body.rating}

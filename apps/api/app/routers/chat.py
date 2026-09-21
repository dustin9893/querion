"""Chat router — conversation management + message streaming."""

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.usage import UsageScope
from app.deps import get_db
from app.auth.deps import require_ws_role, WorkspaceContext
from app.models.user_workspace import WsRole
from app.models.dataset import Dataset
from app.models.conversation import Conversation
from app.models.message import Message
from app.services.chat import chat_stream, generate_title
from app.services.observability import create_run, complete_run
from app.services.chat import AnswerCollector
from app.services.pii import mask_pii

router = APIRouter(prefix="/v1", tags=["chat"])


# ---------- Schemas ----------

class ConversationCreate(BaseModel):
    title: str = Field("New Chat", max_length=256)


class ConversationResponse(BaseModel):
    id: str
    dataset_id: str
    title: str
    message_count: int
    created_at: str
    updated_at: str


class MessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    sources: list | None
    created_at: str


# ---------- Conversations ----------

@router.post("/datasets/{dataset_id}/conversations", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    dataset_id: str,
    body: ConversationCreate,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new chat conversation for a dataset."""
    ds_uuid = uuid.UUID(dataset_id)

    # Verify dataset belongs to workspace
    result = await db.execute(
        select(Dataset).where(Dataset.id == ds_uuid, Dataset.workspace_id == ws_ctx.workspace_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Dataset not found")

    conv = Conversation(
        workspace_id=ws_ctx.workspace_id,
        dataset_id=ds_uuid,
        title=body.title,
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)

    return ConversationResponse(
        id=str(conv.id), dataset_id=str(conv.dataset_id),
        title=conv.title, message_count=0,
        created_at=conv.created_at.isoformat(), updated_at=conv.updated_at.isoformat(),
    )


@router.get("/datasets/{dataset_id}/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    dataset_id: str,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    """List conversations for a dataset."""
    ds_uuid = uuid.UUID(dataset_id)

    result = await db.execute(
        select(Dataset).where(Dataset.id == ds_uuid, Dataset.workspace_id == ws_ctx.workspace_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Dataset not found")

    convs = await db.execute(
        # admin dataset-chat threads only; assistant conversations (staff, customer, test) belong to their app
        select(Conversation).where(Conversation.dataset_id == ds_uuid, Conversation.app_id.is_(None))
        .order_by(Conversation.updated_at.desc())
    )
    conversations = convs.scalars().all()

    result_list = []
    for conv in conversations:
        count = await db.execute(
            select(func.count()).select_from(Message).where(Message.conversation_id == conv.id)
        )
        result_list.append(ConversationResponse(
            id=str(conv.id), dataset_id=str(conv.dataset_id),
            title=conv.title, message_count=count.scalar() or 0,
            created_at=conv.created_at.isoformat(), updated_at=conv.updated_at.isoformat(),
        ))

    return result_list


@router.delete("/conversations/{conversation_id}", status_code=200)
async def delete_conversation(
    conversation_id: str,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a conversation and all its messages."""
    conv_uuid = uuid.UUID(conversation_id)
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_uuid,
            Conversation.workspace_id == ws_ctx.workspace_id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await db.delete(conv)
    await db.commit()
    return {"detail": "Conversation deleted"}


# ---------- Messages ----------

@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def get_messages(
    conversation_id: str,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    """Get message history for a conversation."""
    conv_uuid = uuid.UUID(conversation_id)
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_uuid,
            Conversation.workspace_id == ws_ctx.workspace_id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Conversation not found")

    msgs = await db.execute(
        select(Message).where(Message.conversation_id == conv_uuid)
        .order_by(Message.created_at)
    )

    return [
        MessageResponse(
            id=str(m.id), role=m.role, content=m.content,
            sources=m.sources, created_at=m.created_at.isoformat(),
        )
        for m in msgs.scalars().all()
    ]


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    body: MessageRequest,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    """Send a message and get a streaming AI response (SSE)."""
    conv_uuid = uuid.UUID(conversation_id)
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_uuid,
            Conversation.workspace_id == ws_ctx.workspace_id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Save user message (PII masked at the boundary)
    body.content = mask_pii(body.content).text
    user_msg = Message(
        conversation_id=conv_uuid,
        role="user",
        content=body.content,
    )
    db.add(user_msg)
    await db.commit()

    # Title will be generated after first response via LLM
    is_first_message = False
    msg_count = await db.execute(
        select(func.count()).select_from(Message).where(Message.conversation_id == conv_uuid)
    )
    if (msg_count.scalar() or 0) == 1:
        is_first_message = True

    # Get conversation history
    history_result = await db.execute(
        select(Message).where(Message.conversation_id == conv_uuid)
        .order_by(Message.created_at)
    )
    history = [
        {"role": m.role, "content": m.content}
        for m in history_result.scalars().all()
        if m.id != user_msg.id  # exclude current message (added to prompt separately)
    ]

    run = await create_run(
        db, conversation_id=conv.id, workspace_id=conv.workspace_id,
        user_id=ws_ctx.user.id, channel="admin_test", query=body.content,
    )
    await db.commit()
    collector = AnswerCollector()

    # Create streaming response that also saves assistant message after completion
    async def generate():
        full_response = ""
        sources = None

        async for chunk in chat_stream(db, body.content, conv.dataset_id, history, run=run, collector=collector):
            yield chunk
            # Parse chunk to accumulate response
            if chunk.startswith("data: ") and chunk.strip() != "data: [DONE]":
                try:
                    data = __import__("json").loads(chunk[6:])
                    if data.get("type") == "token":
                        full_response += data["content"]
                    elif data.get("type") == "sources":
                        sources = data.get("sources")
                except Exception:
                    pass

        await complete_run(run, status="completed" if full_response else "failed",
                           answer=full_response or None, error=collector.error)
        await db.commit()

        # Save assistant message after stream completes (skip errors)
        if full_response and not full_response.startswith("\n\n⚠️"):
            assistant_msg = Message(
                conversation_id=conv_uuid,
                role="assistant",
                content=full_response,
                sources=sources,
                run_id=run.id,
            )
            db.add(assistant_msg)
            conv.updated_at = datetime.now(timezone.utc)
            await db.commit()

            # Auto-generate title from first exchange
            if is_first_message:
                try:
                    title = await generate_title(db, body.content, full_response, usage=UsageScope.of_run(run, dataset_id=conv.dataset_id))
                    if title:
                        conv.title = title
                        await db.commit()
                except Exception:
                    pass

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

"""Staff (bank employee) portal — login, me, change-password, published assistants, chat."""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.usage import UsageScope
from app.deps import get_db
from app.auth.security import verify_password, hash_password, create_access_token, create_refresh_token, decode_token
from app.models.employee import Employee
from app.models.app import App
from app.models.workspace import Workspace
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.feedback import MessageFeedback
from app.models.artifact import Artifact
from app.models.memory import Memory
from app.models.schedule import Schedule
from app.models.form_template import FormTemplate
from app.services.chat import answer_for_app, generate_title, remember_after_answer, AnswerCollector
from app.services.tools.approvals import continue_after_decision, load_pending, mark_decided, record_pending
from app.services.observability import create_run, complete_run
from app.services.ratelimit import enforce_staff_limits
from app.services.embed import normalize_origin, effective_widget
from app.services.extension import CLIENTS
from app.services.pii import mask_pii, notice_for
from app.services.branding import logo_url

router = APIRouter(prefix="/v1/staff", tags=["staff"])
logger = logging.getLogger(__name__)

STAFF_ROLE = "staff"


# -- Schemas --
class StaffLoginRequest(BaseModel):
    email: str
    password: str
    # where the session will live: "portal" (default) or "extension" (the floating bubble).
    # Stamped into the JWT, so the server — not the client — decides what that surface may list.
    client: str | None = None


class EmployeeResponse(BaseModel):
    id: str
    email: str
    name: str
    employee_code: str | None
    branch: str | None
    department: str | None
    position: str | None
    must_change_password: bool
    workspace_id: str | None = None    # đơn vị of the employee (0019)
    workspace_name: str | None = None


class StaffLoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    employee: EmployeeResponse


class ChangePasswordRequest(BaseModel):
    new_password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str


class PublishedAppItem(BaseModel):
    id: str
    name: str
    description: str | None
    logo_url: str | None = None
    workspace_id: str
    share_scope: str = "unit"   # bank → shared with every unit
    own_unit: bool = True       # False → visible only because it is shared bank-wide
    suggestions: list[str] = []  # from widget_config (Admin → Trợ lý → Nhúng vào website)
    greeting: str | None = None
    extension_enabled: bool = False
    extension_hosts: list[str] = []  # the bubble opens this assistant by default on matching pages
    primary_color: str | None = None


class WorkspaceAppsGroup(BaseModel):
    workspace_name: str
    apps: list[PublishedAppItem]


def _employee_response(e: Employee, workspace_name: str | None = None) -> EmployeeResponse:
    return EmployeeResponse(
        id=str(e.id), email=e.email, name=e.name,
        employee_code=e.employee_code, branch=e.branch,
        department=e.department, position=e.position,
        must_change_password=e.must_change_password,
        workspace_id=str(e.workspace_id) if e.workspace_id else None,
        workspace_name=workspace_name,
    )


async def _unit_name(db: AsyncSession, e: Employee) -> str | None:
    if not e.workspace_id:
        return None
    ws = await db.get(Workspace, e.workspace_id)
    return ws.name if ws else None


def _staff_can_use(app: App | None, employee: Employee) -> bool:
    """Unit scoping: a published staff assistant is usable by employees of the owning unit,
    or by everyone when its owner opened it bank-wide (share_scope = 'bank')."""
    if not app or not app.is_published or app.audience == "customer":
        return False
    if (app.share_scope or "unit") == "bank":
        return True
    return employee.workspace_id is not None and app.workspace_id == employee.workspace_id


def _client_of(payload: dict | None) -> str:
    client = (payload or {}).get("client")
    return client if client in CLIENTS else "portal"


def staff_client(request: Request) -> str:
    """"portal" or "extension" — read from the JWT so the surface cannot be spoofed by a header."""
    auth = request.headers.get("Authorization", "")
    return _client_of(decode_token(auth[7:]) if auth.startswith("Bearer ") else None)


# -- Dependency --
async def require_staff(request: Request, db: AsyncSession = Depends(get_db)) -> Employee:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")

    payload = decode_token(auth[7:])
    if not payload or payload.get("type") != "access" or payload.get("role") != STAFF_ROLE:
        raise HTTPException(status_code=401, detail="Invalid staff token")

    employee = await db.get(Employee, uuid.UUID(payload["sub"]))
    if not employee or not employee.is_active:
        raise HTTPException(status_code=401, detail="Employee not found or inactive")
    return employee


# -- Auth endpoints --
@router.post("/login", response_model=StaffLoginResponse)
async def staff_login(body: StaffLoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Employee).where(Employee.email == body.email))
    employee = result.scalar_one_or_none()

    if not employee or not verify_password(body.password, employee.password_hash):
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng")
    if not employee.is_active:
        raise HTTPException(status_code=403, detail="Tài khoản đã bị vô hiệu hoá")

    client = body.client if body.client in CLIENTS else "portal"
    return StaffLoginResponse(
        access_token=create_access_token(str(employee.id), STAFF_ROLE, client=client),
        refresh_token=create_refresh_token(str(employee.id), client=client),
        employee=_employee_response(employee, await _unit_name(db, employee)),
    )


@router.post("/refresh", response_model=TokenResponse)
async def staff_refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    employee = await db.get(Employee, uuid.UUID(payload["sub"]))
    if not employee or not employee.is_active:
        raise HTTPException(status_code=401, detail="Employee not found")

    # the refreshed token keeps the surface it was issued for
    return TokenResponse(access_token=create_access_token(str(employee.id), STAFF_ROLE, client=_client_of(payload)))


@router.get("/me", response_model=EmployeeResponse)
async def staff_me(employee: Employee = Depends(require_staff), db: AsyncSession = Depends(get_db)):
    return _employee_response(employee, await _unit_name(db, employee))


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    employee: Employee = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="Mật khẩu phải có ít nhất 6 ký tự")
    employee.password_hash = hash_password(body.new_password)
    employee.must_change_password = False
    await db.commit()
    return {"detail": "Password changed successfully"}


@router.get("/apps", response_model=list[WorkspaceAppsGroup])
async def list_published_apps(
    employee: Employee = Depends(require_staff),
    client: str = Depends(staff_client),
    db: AsyncSession = Depends(get_db),
):
    """Published staff assistants the employee may use, grouped by unit — own unit first.

    Visible = owned by the employee's unit, or shared bank-wide by its owner (share_scope='bank').
    An employee without a unit sees only bank-wide assistants. A session opened from the browser
    extension additionally sees only assistants an admin opted in (`extension_enabled`)."""
    visible = App.share_scope == "bank"
    if employee.workspace_id is not None:
        visible = or_(visible, App.workspace_id == employee.workspace_id)
    conditions = [App.is_published.is_(True), App.audience != "customer", visible]
    if client == "extension":
        conditions.append(App.extension_enabled.is_(True))
    result = await db.execute(
        select(App, Workspace.name.label("ws_name"))
        .join(Workspace, App.workspace_id == Workspace.id)
        .where(*conditions)
        .order_by(Workspace.name, App.name)
    )

    groups: dict[str, list[PublishedAppItem]] = {}
    own_names: set[str] = set()
    for app, ws_name in result.all():
        own = employee.workspace_id is not None and app.workspace_id == employee.workspace_id
        if own:
            own_names.add(ws_name)
        widget = effective_widget(app.name, app.widget_config)
        groups.setdefault(ws_name, []).append(PublishedAppItem(
            id=str(app.id), name=app.name, description=app.description, logo_url=logo_url(app),
            workspace_id=str(app.workspace_id), share_scope=app.share_scope or "unit", own_unit=own,
            suggestions=list(widget.get("suggestions") or [])[:4], greeting=widget.get("greeting"),
            extension_enabled=bool(app.extension_enabled), extension_hosts=list(app.extension_hosts or []),
            primary_color=widget.get("primary_color"),
        ))

    ordered = sorted(groups.items(), key=lambda kv: (kv[0] not in own_names, kv[0]))
    return [WorkspaceAppsGroup(workspace_name=k, apps=v) for k, v in ordered]


# ---------- Conversations ----------

class StaffChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None  # if None, creates new conversation


class StaffConversationResponse(BaseModel):
    id: str
    app_id: str
    title: str
    message_count: int
    created_at: str
    updated_at: str


class StaffMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    sources: list | None
    created_at: str
    run_id: str | None = None
    feedback: str | None = None  # up | down


class FeedbackRequest(BaseModel):
    rating: str  # up | down
    reason: str | None = None


@router.get("/apps/{app_id}/conversations")
async def list_staff_conversations(
    app_id: str,
    employee: Employee = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """List the employee's conversations for an assistant."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.employee_id == employee.id,
            Conversation.app_id == uuid.UUID(app_id),
        ).order_by(Conversation.updated_at.desc())
    )
    convs = result.scalars().all()

    out = []
    for conv in convs:
        count = await db.execute(
            select(func.count()).select_from(Message).where(Message.conversation_id == conv.id)
        )
        out.append(StaffConversationResponse(
            id=str(conv.id), app_id=str(conv.app_id), title=conv.title,
            message_count=count.scalar() or 0,
            created_at=conv.created_at.isoformat(), updated_at=conv.updated_at.isoformat(),
        ))
    return out


@router.get("/conversations/{conversation_id}/messages")
async def get_staff_messages(
    conversation_id: str,
    employee: Employee = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    conv = await db.execute(
        select(Conversation).where(
            Conversation.id == uuid.UUID(conversation_id),
            Conversation.employee_id == employee.id,
        )
    )
    if not conv.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Conversation not found")

    msgs = (await db.execute(
        select(Message).where(Message.conversation_id == uuid.UUID(conversation_id))
        .order_by(Message.created_at)
    )).scalars().all()
    fb_rows = await db.execute(
        select(MessageFeedback.message_id, MessageFeedback.rating)
        .where(MessageFeedback.message_id.in_([m.id for m in msgs] or [uuid.uuid4()]))
    )
    fb = {mid: rating for mid, rating in fb_rows.all()}
    return [
        StaffMessageResponse(
            id=str(m.id), role=m.role, content=m.content,
            sources=m.sources, created_at=m.created_at.isoformat(),
            run_id=str(m.run_id) if m.run_id else None, feedback=fb.get(m.id),
        )
        for m in msgs
    ]


class ToolApprovalDecision(BaseModel):
    approve: bool


@router.post("/tool-approvals/{approval_id}")
async def decide_tool_approval(
    approval_id: str,
    body: ToolApprovalDecision,
    employee: Employee = Depends(require_staff),
    client: str = Depends(staff_client),
    db: AsyncSession = Depends(get_db),
):
    """Cán bộ duyệt hoặc từ chối một thao tác mà trợ lý muốn thực hiện.

    Streams the rest of the answer in the same SSE envelope as the chat endpoint.
    """
    approval = await load_pending(db, approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Yêu cầu duyệt không tồn tại hoặc đã được xử lý")
    conv = await db.get(Conversation, approval.conversation_id) if approval.conversation_id else None
    if not conv or conv.employee_id != employee.id:
        raise HTTPException(status_code=404, detail="Yêu cầu duyệt không thuộc về bạn")
    app = await db.get(App, conv.app_id)
    if not _staff_can_use(app, employee):
        raise HTTPException(status_code=404, detail="Assistant not found")

    await mark_decided(db, approval, approve=body.approve, employee_id=employee.id)
    return StreamingResponse(
        continue_after_decision(db, app=app, approval=approval, approve=body.approve,
                                channel="extension" if client == "extension" else "staff"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/messages/{message_id}/feedback")
async def rate_message(
    message_id: str,
    body: FeedbackRequest,
    employee: Employee = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """👍 / 👎 on an assistant answer — feeds the Compliance audit log."""
    if body.rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="rating must be 'up' or 'down'")
    msg = (await db.execute(
        select(Message).join(Conversation, Conversation.id == Message.conversation_id).where(
            Message.id == uuid.UUID(message_id),
            Message.role == "assistant",
            Conversation.employee_id == employee.id,
        )
    )).scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    fb = (await db.execute(select(MessageFeedback).where(MessageFeedback.message_id == msg.id))).scalar_one_or_none()
    if fb:
        fb.rating = body.rating
        fb.reason = (body.reason or "").strip() or None
        fb.employee_id = employee.id
    else:
        fb = MessageFeedback(message_id=msg.id, run_id=msg.run_id, employee_id=employee.id,
                             rating=body.rating, reason=(body.reason or "").strip() or None)
        db.add(fb)
    await db.commit()
    return {"message_id": str(msg.id), "rating": fb.rating, "reason": fb.reason}


@router.delete("/conversations/{conversation_id}")
async def delete_staff_conversation(
    conversation_id: str,
    employee: Employee = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == uuid.UUID(conversation_id),
            Conversation.employee_id == employee.id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await db.delete(conv)
    await db.commit()
    return {"detail": "Conversation deleted"}


def _page_origin(request: Request) -> str | None:
    """`X-Page-Origin`: the intranet page the extension bubble was opened on. Audit only —
    accepted as any well-formed origin, never used for access decisions."""
    raw = request.headers.get("x-page-origin")
    if not raw:
        return None
    try:
        return normalize_origin(raw)
    except HTTPException:
        return None


def _staff_embed_origin(app: App, request: Request) -> str | None:
    """X-Embed-Origin from the embedded widget on an intranet page; must be allowlisted."""
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


class StaffReport(BaseModel):
    id: str
    title: str | None
    filename: str
    content_type: str
    size: int
    created_at: str
    schedule_name: str | None = None
    preview: str | None = None


async def _staff_reports_stmt(employee: Employee):
    """This employee's inbox — two sources, nothing else:

    1. files they produced themselves (a form they filled, a report they asked the assistant for);
    2. files a **schedule** delivered to them, honouring its "gửi cho chức danh" list
       (an empty list means every employee of the unit).

    A report an admin ran by hand from the canvas has no delivery target, so it stays in the admin
    UI instead of appearing in everyone's inbox.
    """
    from sqlalchemy import and_

    delivered = and_(
        Artifact.schedule_id.isnot(None),
        or_(Schedule.deliver_positions == [],
            Schedule.deliver_positions.contains([employee.position])),
    )
    return (select(Artifact, Schedule.name)
            .outerjoin(Schedule, Schedule.id == Artifact.schedule_id)
            .where(Artifact.audience == "staff",
                   Artifact.workspace_id == employee.workspace_id,
                   or_(Artifact.created_by_employee_id == employee.id, delivered))
            .order_by(Artifact.created_at.desc()))


@router.get("/reports", response_model=list[StaffReport])
async def staff_reports(
    limit: int = 30,
    employee: Employee = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """This employee's own files plus the reports a schedule delivered to their position."""
    if not employee.workspace_id:
        return []
    rows = (await db.execute((await _staff_reports_stmt(employee)).limit(min(max(limit, 1), 100)))).all()
    return [StaffReport(
        id=str(a.id), title=a.title, filename=a.filename, content_type=a.content_type, size=a.size,
        created_at=a.created_at.isoformat(), schedule_name=sched_name,
        preview=(a.preview or "")[:4000] or None,
    ) for a, sched_name in rows]


@router.get("/reports/{artifact_id}/download")
async def staff_download_report(
    artifact_id: str,
    employee: Employee = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    from app.routers.artifacts import download_response

    try:
        aid = uuid.UUID(artifact_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Không tìm thấy báo cáo")
    row = (await db.execute((await _staff_reports_stmt(employee)).where(Artifact.id == aid))).first()
    if not row:
        raise HTTPException(status_code=404, detail="Báo cáo không dành cho bạn")
    return download_response(row[0])


# ---------------------------------------------------------------------------
# Biểu mẫu nghiệp vụ: cán bộ điền, điền sẵn từ hệ thống lõi, gợi ý phần tự luận, xuất .docx
# ---------------------------------------------------------------------------

class StaffFormSummary(BaseModel):
    id: str
    name: str
    description: str | None
    fields: list[dict]
    has_prefill: bool
    prefill_label: str | None = None


class PrefillRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=64)


class SuggestRequest(BaseModel):
    field: str = Field(..., min_length=1, max_length=64)
    values: dict = {}


class SubmitFormRequest(BaseModel):
    values: dict = {}


async def _staff_form(db: AsyncSession, form_id: str, employee: Employee) -> FormTemplate:
    """A published form of the employee's unit (or one shared bank-wide)."""
    from app.services.forms import visible_forms

    if not employee.workspace_id:
        raise HTTPException(status_code=404, detail="Cán bộ chưa được gán đơn vị")
    try:
        fid = uuid.UUID(form_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Không tìm thấy biểu mẫu")
    forms = await visible_forms(db, employee.workspace_id, published_only=True)
    form = next((f for f in forms if f.id == fid), None)
    if not form:
        raise HTTPException(status_code=404, detail="Biểu mẫu không dành cho đơn vị của bạn")
    return form


@router.get("/forms", response_model=list[StaffFormSummary])
async def staff_forms(
    employee: Employee = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    from app.services.forms import visible_forms

    if not employee.workspace_id:
        return []
    forms = [f for f in await visible_forms(db, employee.workspace_id, published_only=True)
             if f.template_storage_key]
    out = []
    for f in forms:
        label = None
        if f.prefill_tool_id and f.prefill_arg:
            field = next((x for x in (f.fields or []) if x.get("name") == f.prefill_arg), None)
            label = (field or {}).get("label") or f.prefill_arg
        out.append(StaffFormSummary(id=str(f.id), name=f.name, description=f.description,
                                    fields=list(f.fields or []),
                                    has_prefill=bool(f.prefill_tool_id and f.prefill_arg), prefill_label=label))
    return out


@router.post("/forms/{form_id}/prefill")
async def staff_form_prefill(
    form_id: str,
    body: PrefillRequest,
    employee: Employee = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Fill the tool-sourced fields from one business code (mã hồ sơ), audited like any tool call."""
    from app.services.forms import FormError, prefill_values

    form = await _staff_form(db, form_id, employee)
    try:
        values = await prefill_values(db, form, body.key.strip())
    except FormError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not values:
        raise HTTPException(status_code=404, detail="Không tìm thấy dữ liệu cho mã đã nhập")
    return {"values": values}


@router.post("/forms/{form_id}/suggest")
async def staff_form_suggest(
    form_id: str,
    body: SuggestRequest,
    employee: Employee = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Draft one free-text field. Fields marked PII never reach the model (services/forms.py)."""
    from app.services.forms import FormError, suggest_text

    form = await _staff_form(db, form_id, employee)
    field = next((f for f in (form.fields or []) if f.get("name") == body.field), None)
    if not field or field.get("source") != "llm":
        raise HTTPException(status_code=400, detail="Trường này không dùng gợi ý AI")

    run = await create_run(db, workspace_id=employee.workspace_id, employee_id=employee.id,
                           channel="form", query=f"Gợi ý nội dung: {field.get('label') or field['name']}")
    await db.commit()
    try:
        text = await suggest_text(db, form, field, body.values or {}, usage=UsageScope.of_run(run))
    except FormError as e:
        await complete_run(run, status="failed", error=str(e))
        await db.commit()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("form suggest failed")
        await complete_run(run, status="failed", error=str(e))
        await db.commit()
        raise HTTPException(status_code=502, detail="Không gọi được mô hình ngôn ngữ")
    await complete_run(run, status="completed", answer=text)
    await db.commit()
    return {"text": text}


@router.post("/forms/{form_id}/submit", status_code=201)
async def staff_form_submit(
    form_id: str,
    body: SubmitFormRequest,
    employee: Employee = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Render the filled form as .docx and keep it in the employee's reports."""
    from app.routers.forms import fill_form

    form = await _staff_form(db, form_id, employee)
    run = await create_run(db, workspace_id=employee.workspace_id, employee_id=employee.id,
                           channel="form", query=f"Lập biểu mẫu: {form.name}")
    await db.commit()
    try:
        artifact = await fill_form(db, form, body.values or {}, created_by_employee_id=employee.id,
                                   author=f"{employee.name} ({employee.employee_code or employee.position or ''})".strip(),
                                   audience="staff")
    except HTTPException as exc:
        await complete_run(run, status="failed", error=str(exc.detail))
        await db.commit()
        raise
    artifact.run_id = run.id
    await complete_run(run, status="completed", answer=artifact.title)
    await db.commit()
    return {"artifact_id": str(artifact.id), "filename": artifact.filename, "title": artifact.title}


@router.post("/apps/{app_id}/chat")
async def staff_app_chat(
    app_id: str,
    body: StaffChatRequest,
    request: Request,
    employee: Employee = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Chat with a published assistant — RAG/workflow + streaming + conversation persistence."""
    app = await db.get(App, uuid.UUID(app_id))
    if not _staff_can_use(app, employee):  # not published / customer-only / another unit's assistant
        raise HTTPException(status_code=404, detail="Assistant not found or not published")
    embed_origin = _staff_embed_origin(app, request)
    client = staff_client(request)
    if client == "extension":
        if not app.extension_enabled:
            raise HTTPException(status_code=403, detail="Trợ lý này chưa được mở cho browser extension")
        # the page the bubble sat on, for the audit log only (the extension reports it)
        embed_origin = _page_origin(request)
    channel = "extension" if client == "extension" else ("embed" if embed_origin else "staff")
    await enforce_staff_limits(app.id, employee.id)
    pii = mask_pii(body.message)
    question = pii.text

    # Get or create conversation
    if body.conversation_id:
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == uuid.UUID(body.conversation_id),
                Conversation.employee_id == employee.id,
            )
        )
        conv = result.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conv = Conversation(
            workspace_id=app.workspace_id,
            employee_id=employee.id,
            app_id=app.id,
            title="Hội thoại mới",
        )
        db.add(conv)
        await db.commit()
        await db.refresh(conv)

    user_msg = Message(conversation_id=conv.id, role="user", content=question)
    db.add(user_msg)
    await db.commit()

    msg_count_result = await db.execute(
        select(func.count()).select_from(Message).where(Message.conversation_id == conv.id)
    )
    is_first = (msg_count_result.scalar() or 0) == 1

    history_result = await db.execute(
        select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at)
    )
    history = [
        {"role": m.role, "content": m.content}
        for m in history_result.scalars().all()
        if m.id != user_msg.id
    ]

    # Audit run — one per answer, regardless of RAG vs workflow mode
    run = await create_run(
        db, app_id=app.id, workflow_id=app.workflow_id, conversation_id=conv.id,
        workspace_id=app.workspace_id, employee_id=employee.id,
        channel=channel, client_origin=embed_origin, query=question,
    )
    await db.commit()

    async def generate():
        yield f"data: {json.dumps({'type': 'conversation_id', 'conversation_id': str(conv.id)})}\n\n"
        if pii.found:
            yield f"data: {json.dumps({'type': 'notice', 'content': notice_for(pii.kinds), 'masked': pii.kinds})}\n\n"

        collector = AnswerCollector()
        try:
            async for chunk in answer_for_app(db, app, question, history, collector, run=run,
                                              channel=channel):
                yield chunk
        except Exception as e:  # never let an exception kill the SSE stream
            logger.exception("staff chat failed (run %s)", run.id)
            collector.error = str(e)  # kept server-side in the audit run
            yield f"data: {json.dumps({'type': 'error', 'content': 'Hệ thống đang gặp lỗi, vui lòng thử lại sau.'})}\n\n"

        yield "data: [DONE]\n\n"

        if collector.pending_approval:
            # A tool needs a human decision: park the run and hand the client the approval id.
            approval = await record_pending(db, run=run, conversation_id=conv.id, pending=collector.pending_approval)
            yield f"data: {json.dumps({'type': 'tool_approval', 'approval_id': str(approval.id), 'tool': collector.pending_approval.get('tool'), 'label': collector.pending_approval.get('label'), 'args': collector.pending_approval.get('args') or {}}, ensure_ascii=False)}\n\n"
            return

        await complete_run(
            run, status="blocked" if collector.blocked else ("completed" if collector.answer else "failed"),
            answer=collector.answer or None, error=collector.error,
        )
        if collector.answer:
            assistant_msg = Message(
                conversation_id=conv.id, role="assistant",
                content=collector.answer,
                sources=collector.sources[:5] if collector.sources else None,
                run_id=run.id,
            )
            db.add(assistant_msg)
            conv.updated_at = datetime.now(timezone.utc)
            await db.commit()
            yield f"data: {json.dumps({'type': 'message_saved', 'message_id': str(assistant_msg.id), 'run_id': str(run.id)})}\n\n"
        else:
            await db.commit()

        if collector.answer:
            # Rút bản ghi nhớ và báo ngay cho người dùng kèm nút hoàn tác. Đặt sau message_saved
            # để dòng "đã ghi nhớ" gắn đúng vào câu trả lời vừa hiện.
            saved = await remember_after_answer(db, app, question, collector.answer, run=run,
                                                collector=collector, conversation_id=conv.id)
            if saved:
                yield f"data: {json.dumps({'type': 'memory_saved', 'memories': saved}, ensure_ascii=False)}\n\n"

            if is_first:
                try:
                    title = await generate_title(db, question, collector.answer, usage=UsageScope.of_run(run))
                    if title:
                        conv.title = title
                        await db.commit()
                        yield f"data: {json.dumps({'type': 'title', 'title': title})}\n\n"
                except Exception:
                    pass

    return StreamingResponse(generate(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no",
    })

# ---------------------------------------------------------------------------
# Bộ nhớ cá nhân — "Trợ lý nhớ gì về tôi"
# ---------------------------------------------------------------------------

class MemoryPatch(BaseModel):
    text: str | None = Field(None, min_length=1, max_length=240)
    pinned: bool | None = None


class MemoryPausePatch(BaseModel):
    paused: bool


@router.post("/memory/pause")
async def pause_memory(
    body: MemoryPausePatch,
    employee: Employee = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Ngừng học thêm nhưng giữ nguyên những gì đã nhớ.

    Tách hẳn khỏi việc xoá sạch, vì phần lớn người muốn cái thứ nhất chứ không phải cái thứ hai.
    Lưu ở máy chủ để nó có hiệu lực thật và theo người qua mọi thiết bị.
    """
    employee.memory_paused = bool(body.paused)
    await db.commit()
    return {"paused": employee.memory_paused,
            "detail": "Đã tạm dừng ghi nhớ" if employee.memory_paused else "Đã bật lại ghi nhớ"}


@router.get("/memory")
async def my_memory(
    employee: Employee = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Mọi thứ trợ lý nhớ về cán bộ này, kèm hồ sơ nghề nghiệp do đơn vị quản lý.

    Người dùng không thấy được bộ nhớ thì cá nhân hoá giống rò rỉ hơn là tính năng, nên trang này
    liệt kê đủ, không tóm tắt và không giấu mục nào.
    """
    from app.models.workspace import Workspace
    from app.services.memory import CATEGORIES, to_dict

    rows = (await db.execute(select(Memory).where(Memory.employee_id == employee.id)
                             .order_by(Memory.pinned.desc(), Memory.created_at.desc()))).scalars().all()
    ws = await db.get(Workspace, employee.workspace_id) if employee.workspace_id else None
    return {
        "enabled": bool(ws is None or getattr(ws, "memory_enabled", True)),
        "paused": bool(getattr(employee, "memory_paused", False)),
        "retention_days": int(getattr(ws, "memory_retention_days", 180) or 180) if ws else 180,
        "categories": CATEGORIES,
        "items": [to_dict(m) for m in rows],
        # Hồ sơ nghề nghiệp không nằm trong bộ nhớ: nó do đơn vị quản lý, cán bộ không tự sửa.
        "profile": {
            "name": employee.name, "employee_code": employee.employee_code,
            "position": employee.position, "branch": employee.branch,
            "department": employee.department,
        },
        "never_remembers": [
            "Thông tin khách hàng: tên, số tài khoản, CIF, số tiền",
            "Kết quả nghiệp vụ của một hồ sơ cụ thể",
            "Nhận xét về đồng nghiệp",
            "Nội dung quy định; thứ đó nằm trong kho tri thức để trích dẫn được",
        ],
    }


@router.patch("/memory/{memory_id}")
async def update_memory(
    memory_id: str,
    body: MemoryPatch,
    employee: Employee = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Sửa nội dung hoặc ghim một bản ghi. Sửa xong vẫn phải qua đúng bộ lọc như lúc ghi."""
    from app.services.memory import as_uuid, rejection_reason, to_dict

    mid = as_uuid(memory_id)
    row = (await db.execute(select(Memory).where(
        Memory.id == mid, Memory.employee_id == employee.id))).scalar_one_or_none() if mid else None
    if row is None:
        raise HTTPException(404, "Không tìm thấy bản ghi nhớ")
    if body.text is not None:
        text = " ".join(body.text.split())
        reason = rejection_reason(text, row.category)
        if reason:
            raise HTTPException(400, f"Không lưu được: {reason}")
        row.text = text
        from app.services.memory import _embed

        row.embedding = await _embed(db, text)
    if body.pinned is not None:
        row.pinned = body.pinned
        if body.pinned:
            row.expires_at = None  # đã ghim thì không hết hạn
        elif row.expires_at is None:
            # Bỏ ghim mà không gán lại hạn thì bản ghi sống mãi, tức là bỏ ghim không thật sự bỏ.
            from app.services.memory import CONTEXT_TTL_DAYS, DEFAULT_TTL_DAYS

            days = CONTEXT_TTL_DAYS if row.category == "boi_canh" else DEFAULT_TTL_DAYS
            row.expires_at = datetime.now(timezone.utc) + timedelta(days=days)
    await db.commit()
    await db.refresh(row)
    return to_dict(row)


@router.delete("/memory/{memory_id}")
async def delete_memory(
    memory_id: str,
    employee: Employee = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    from app.services.memory import as_uuid

    mid = as_uuid(memory_id)
    row = (await db.execute(select(Memory).where(
        Memory.id == mid, Memory.employee_id == employee.id))).scalar_one_or_none() if mid else None
    if row is None:
        raise HTTPException(404, "Không tìm thấy bản ghi nhớ")
    await db.delete(row)
    await db.commit()
    return {"detail": "Đã xoá bản ghi nhớ"}


@router.delete("/memory")
async def clear_memory(
    employee: Employee = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Xoá sạch. Tách hẳn khỏi việc tạm dừng, vì phần lớn người dùng muốn tạm dừng chứ không xoá."""
    from app.services.memory import forget_employee

    removed = await forget_employee(db, employee.id)
    await db.commit()
    return {"detail": f"Đã xoá {removed} bản ghi nhớ", "removed": removed}


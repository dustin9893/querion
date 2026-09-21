"""Compliance audit log — who asked what, which documents were cited, how it was rated.

super_admin sees everything; an admin sees runs of workspaces where they are owner.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.auth.deps import get_current_user
from app.models.user import User, UserRole
from app.models.user_workspace import UserWorkspace, WsRole
from app.models.workspace import Workspace
from app.models.app import App
from app.models.run import Run, RunStep
from app.models.employee import Employee
from app.models.message import Message
from app.models.feedback import MessageFeedback

router = APIRouter(prefix="/v1/audit", tags=["audit"])

CHANNELS = ("staff", "customer", "admin_test", "embed", "extension", "ops", "report", "scheduled", "form")


# ---------- Schemas ----------

class AuditRunRow(BaseModel):
    id: str
    started_at: str
    latency_ms: int | None
    status: str
    channel: str
    workspace_id: str | None
    workspace_name: str | None
    app_id: str | None
    app_name: str | None
    workflow_id: str | None
    conversation_id: str | None
    asked_by: str | None          # employee name / admin email / "Khách hàng"
    asked_by_meta: str | None     # "MSB01001 · RM · CN Hà Nội"
    client_origin: str | None = None  # website that embedded the widget (channel=embed)
    query_preview: str | None
    answer_preview: str | None
    error: str | None
    feedback_rating: str | None
    feedback_reason: str | None
    step_count: int
    total_tokens: int = 0         # model tokens spent on this answer (token_usage)


class AuditStep(BaseModel):
    id: str
    node_id: str
    node_type: str
    started_at: str
    ended_at: str | None
    duration_ms: int | None
    input_json: dict[str, Any] | None
    output_json: dict[str, Any] | None


class AuditRunDetail(AuditRunRow):
    question: str | None
    answer: str | None
    sources: list[dict[str, Any]] | None
    steps: list[AuditStep]
    usage: list[dict[str, Any]] = []  # tokens per component (answer, agent, title, query_embedding…)


class AuditSummary(BaseModel):
    total_runs: int
    runs_by_channel: dict[str, int]
    avg_latency_ms: int | None
    error_count: int
    feedback_up: int
    feedback_down: int
    feedback_rate: float  # fraction of runs that received feedback
    top_documents: list[dict[str, Any]]


# ---------- Access scope ----------

async def _allowed_workspaces(db: AsyncSession, user: User) -> list[uuid.UUID] | None:
    """None = unrestricted (super_admin). Otherwise workspaces the admin owns."""
    if user.role == UserRole.super_admin:
        return None
    rows = await db.execute(
        select(UserWorkspace.workspace_id).where(
            UserWorkspace.user_id == user.id, UserWorkspace.ws_role == WsRole.owner,
        )
    )
    return [r[0] for r in rows.all()]


def _apply_scope(stmt, allowed: list[uuid.UUID] | None):
    if allowed is None:
        return stmt
    if not allowed:
        return stmt.where(Run.id.is_(None))  # no access → empty
    return stmt.where(Run.workspace_id.in_(allowed))


def _asked_by(run: Run, emp: Employee | None, user: User | None) -> tuple[str | None, str | None]:
    if run.channel == "customer" or (run.channel == "embed" and emp is None and user is None):
        return "Khách hàng (ẩn danh)", None
    if emp:
        meta = " · ".join(b for b in (emp.employee_code, emp.position, emp.branch) if b)
        return emp.name, meta or None
    if user:
        return user.name or user.email, user.email
    return None, None


# ---------- Endpoints ----------

@router.get("/runs", response_model=list[AuditRunRow])
async def list_audit_runs(
    workspace_id: str | None = None,
    app_id: str | None = None,
    channel: str | None = Query(None, pattern="^(" + "|".join(CHANNELS) + ")$"),   # one list, no drift
    rating: str | None = Query(None, pattern="^(up|down|none)$"),
    status: str | None = Query(None, pattern="^(completed|failed|running|queued|blocked|waiting)$"),
    q: str | None = Query(None, max_length=200, description="search in question / answer preview"),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    allowed = await _allowed_workspaces(db, user)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    fb = MessageFeedback
    stmt = (
        select(Run, Workspace.name, App.name, Employee, User, fb.rating, fb.reason,
               select(func.count(RunStep.id)).where(RunStep.run_id == Run.id).scalar_subquery())
        .outerjoin(Workspace, Workspace.id == Run.workspace_id)
        .outerjoin(App, App.id == Run.app_id)
        .outerjoin(Employee, Employee.id == Run.employee_id)
        .outerjoin(User, User.id == Run.user_id)
        .outerjoin(fb, fb.run_id == Run.id)
        .where(Run.started_at >= since)
        .order_by(Run.started_at.desc())
        .limit(limit)
    )
    stmt = _apply_scope(stmt, allowed)
    if workspace_id:
        stmt = stmt.where(Run.workspace_id == uuid.UUID(workspace_id))
    if app_id:
        stmt = stmt.where(Run.app_id == uuid.UUID(app_id))
    if channel:
        stmt = stmt.where(Run.channel == channel)
    if status:
        stmt = stmt.where(Run.status == status)
    if rating == "none":
        stmt = stmt.where(fb.id.is_(None))
    elif rating:
        stmt = stmt.where(fb.rating == rating)
    if q:
        like = f"%{q}%"
        stmt = stmt.where((Run.query_preview.ilike(like)) | (Run.answer_preview.ilike(like)))

    rows = (await db.execute(stmt)).all()
    from app.routers.usage import run_token_totals
    tokens = await run_token_totals(db, [r[0].id for r in rows])
    out: list[AuditRunRow] = []
    for run, ws_name, app_name, emp, u, fb_rating, fb_reason, step_count in rows:
        asked_by, meta = _asked_by(run, emp, u)
        out.append(AuditRunRow(
            id=str(run.id), started_at=run.started_at.isoformat(), latency_ms=run.latency_ms,
            status=run.status, channel=run.channel,
            workspace_id=str(run.workspace_id) if run.workspace_id else None, workspace_name=ws_name,
            app_id=str(run.app_id) if run.app_id else None, app_name=app_name,
            workflow_id=str(run.workflow_id) if run.workflow_id else None,
            conversation_id=str(run.conversation_id) if run.conversation_id else None,
            asked_by=asked_by, asked_by_meta=meta, client_origin=run.client_origin,
            query_preview=run.query_preview, answer_preview=run.answer_preview, error=run.error,
            feedback_rating=fb_rating, feedback_reason=fb_reason, step_count=step_count or 0,
            total_tokens=tokens.get(run.id, 0),
        ))
    return out


@router.get("/runs/{run_id}", response_model=AuditRunDetail)
async def get_audit_run(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    allowed = await _allowed_workspaces(db, user)
    stmt = (
        select(Run, Workspace.name, App.name, Employee, User)
        .outerjoin(Workspace, Workspace.id == Run.workspace_id)
        .outerjoin(App, App.id == Run.app_id)
        .outerjoin(Employee, Employee.id == Run.employee_id)
        .outerjoin(User, User.id == Run.user_id)
        .where(Run.id == uuid.UUID(run_id))
    )
    stmt = _apply_scope(stmt, allowed)
    row = (await db.execute(stmt)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    run, ws_name, app_name, emp, u = row

    steps = (await db.execute(
        select(RunStep).where(RunStep.run_id == run.id).order_by(RunStep.started_at)
    )).scalars().all()

    # The assistant message produced by this run (carries full answer + citations)
    answer_msg = (await db.execute(
        select(Message).where(Message.run_id == run.id, Message.role == "assistant").limit(1)
    )).scalar_one_or_none()
    question_msg = None
    if answer_msg:
        question_msg = (await db.execute(
            select(Message).where(
                Message.conversation_id == answer_msg.conversation_id,
                Message.role == "user", Message.created_at <= answer_msg.created_at,
            ).order_by(Message.created_at.desc()).limit(1)
        )).scalar_one_or_none()
    fb = None
    if answer_msg:
        fb = (await db.execute(
            select(MessageFeedback).where(MessageFeedback.message_id == answer_msg.id)
        )).scalar_one_or_none()

    from app.routers.usage import run_usage
    usage = [b.model_dump() for b in await run_usage(db, run.id)]
    asked_by, meta = _asked_by(run, emp, u)
    return AuditRunDetail(
        id=str(run.id), started_at=run.started_at.isoformat(), latency_ms=run.latency_ms,
        status=run.status, channel=run.channel,
        workspace_id=str(run.workspace_id) if run.workspace_id else None, workspace_name=ws_name,
        app_id=str(run.app_id) if run.app_id else None, app_name=app_name,
        workflow_id=str(run.workflow_id) if run.workflow_id else None,
        conversation_id=str(run.conversation_id) if run.conversation_id else None,
        asked_by=asked_by, asked_by_meta=meta, client_origin=run.client_origin,
        query_preview=run.query_preview, answer_preview=run.answer_preview, error=run.error,
        feedback_rating=fb.rating if fb else None, feedback_reason=fb.reason if fb else None,
        step_count=len(steps),
        total_tokens=sum(b["total_tokens"] for b in usage), usage=usage,
        question=question_msg.content if question_msg else run.query_preview,
        answer=answer_msg.content if answer_msg else run.answer_preview,
        sources=answer_msg.sources if answer_msg else None,
        steps=[AuditStep(
            id=str(s.id), node_id=s.node_id, node_type=s.node_type,
            started_at=s.started_at.isoformat(), ended_at=s.ended_at.isoformat() if s.ended_at else None,
            duration_ms=int((s.ended_at - s.started_at).total_seconds() * 1000) if s.ended_at else None,
            input_json=s.input_json, output_json=s.output_json,
        ) for s in steps],
    )


@router.get("/summary", response_model=AuditSummary)
async def audit_summary(
    workspace_id: str | None = None,
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    allowed = await _allowed_workspaces(db, user)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    base = select(Run).where(Run.started_at >= since)
    base = _apply_scope(base, allowed)
    if workspace_id:
        base = base.where(Run.workspace_id == uuid.UUID(workspace_id))
    runs_sq = base.subquery()

    total = (await db.execute(select(func.count()).select_from(runs_sq))).scalar() or 0
    by_channel_rows = (await db.execute(
        select(runs_sq.c.channel, func.count()).group_by(runs_sq.c.channel)
    )).all()
    avg_latency = (await db.execute(
        select(func.avg(runs_sq.c.latency_ms)).where(runs_sq.c.status == "completed")
    )).scalar()
    errors = (await db.execute(
        select(func.count()).select_from(runs_sq).where(runs_sq.c.status == "failed")
    )).scalar() or 0

    fb_rows = (await db.execute(
        select(MessageFeedback.rating, func.count())
        .join(runs_sq, runs_sq.c.id == MessageFeedback.run_id)
        .group_by(MessageFeedback.rating)
    )).all()
    fb_map = {r: c for r, c in fb_rows}
    fb_total = sum(fb_map.values())

    # Most-cited documents: unnest the citation list stored on assistant messages of these runs
    top_docs: list[dict[str, Any]] = []
    try:
        from sqlalchemy import text as sql_text
        ids = [str(r[0]) for r in (await db.execute(select(runs_sq.c.id))).all()]
        if ids:
            res = await db.execute(sql_text("""
                SELECT src->>'filename' AS filename, COUNT(*) AS cnt
                FROM messages m, jsonb_array_elements(m.sources) src
                WHERE m.run_id = ANY(CAST(:ids AS uuid[])) AND jsonb_typeof(m.sources) = 'array'
                -- (a JSON null is "NOT NULL" in SQL and made jsonb_array_elements abort the whole query)
                GROUP BY 1 ORDER BY 2 DESC LIMIT 5
            """), {"ids": ids})
            top_docs = [{"filename": r[0], "count": r[1]} for r in res.all() if r[0]]
    except Exception:
        top_docs = []

    return AuditSummary(
        total_runs=total,
        runs_by_channel={c: n for c, n in by_channel_rows},
        avg_latency_ms=int(avg_latency) if avg_latency is not None else None,
        error_count=errors,
        feedback_up=fb_map.get("up", 0),
        feedback_down=fb_map.get("down", 0),
        feedback_rate=round(fb_total / total, 3) if total else 0.0,
        top_documents=top_docs,
    )


@router.get("/filters")
async def audit_filters(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Workspaces + assistants the caller may filter by."""
    allowed = await _allowed_workspaces(db, user)
    ws_stmt = select(Workspace).order_by(Workspace.name)
    app_stmt = select(App).order_by(App.name)
    if allowed is not None:
        ws_stmt = ws_stmt.where(Workspace.id.in_(allowed)) if allowed else ws_stmt.where(Workspace.id.is_(None))
        app_stmt = app_stmt.where(App.workspace_id.in_(allowed)) if allowed else app_stmt.where(App.id.is_(None))
    wss = (await db.execute(ws_stmt)).scalars().all()
    apps = (await db.execute(app_stmt)).scalars().all()
    return {
        "workspaces": [{"id": str(w.id), "name": w.name} for w in wss],
        "apps": [{"id": str(a.id), "name": a.name, "workspace_id": str(a.workspace_id), "audience": a.audience} for a in apps],
        "channels": list(CHANNELS),
    }

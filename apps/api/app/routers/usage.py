"""Token usage statistics: how many model tokens are spent, by which component, channel,
assistant, unit and model.

Same access rule as the audit log: super_admin sees every unit; an admin sees the units they own.
Rows come from ``token_usage`` (services/usage.py in the API, the indexing task in the worker).
"""

import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import Integer, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.deps import get_db
from app.models.app import App
from app.models.usage import TokenUsage
from app.models.user import User
from app.models.workspace import Workspace
from app.routers.audit import _allowed_workspaces
from app.services.usage import COMPONENTS

router = APIRouter(prefix="/v1/usage", tags=["usage"])

LOCAL_TZ = "Asia/Ho_Chi_Minh"  # days are bucketed in bank time, not UTC
CHANNELS = ("staff", "customer", "embed", "admin_test", "retrieval_test", "indexing", "admin_edit")


class UsageBucket(BaseModel):
    key: str | None
    label: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0
    estimated_calls: int = 0


class UsageDay(BaseModel):
    day: str
    total_tokens: int
    by_component: dict[str, int]


class UsageSummary(BaseModel):
    days: int
    since: str
    totals: UsageBucket
    by_day: list[UsageDay]
    by_component: list[UsageBucket]
    by_purpose: list[UsageBucket]
    by_channel: list[UsageBucket]
    by_app: list[UsageBucket]
    by_workspace: list[UsageBucket]
    by_model: list[UsageBucket]


def _sums():
    t = TokenUsage
    return (
        func.coalesce(func.sum(t.prompt_tokens), 0),
        func.coalesce(func.sum(t.completion_tokens), 0),
        func.coalesce(func.sum(t.total_tokens), 0),
        func.coalesce(func.sum(t.calls), 0),
        func.coalesce(func.sum(case((t.estimated, t.calls), else_=0)), 0),
    )


def _bucket(key, sums, label=None) -> UsageBucket:
    p, c, total, calls, est = (int(v or 0) for v in sums)
    return UsageBucket(key=None if key is None else str(key), label=label, prompt_tokens=p,
                       completion_tokens=c, total_tokens=total, calls=calls, estimated_calls=est)


@router.get("/summary", response_model=UsageSummary)
async def usage_summary(
    days: int = Query(30, ge=1, le=365),
    workspace_id: str | None = None,
    app_id: str | None = None,
    channel: str | None = Query(None, max_length=32),
    component: str | None = Query(None, max_length=32),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    t = TokenUsage
    allowed = await _allowed_workspaces(db, user)
    today = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=7))).date()
    first_day = today - timedelta(days=days - 1)
    since = datetime.combine(first_day, datetime.min.time(), tzinfo=timezone(timedelta(hours=7)))

    conds = [t.created_at >= since]
    if allowed is not None:
        conds.append(t.workspace_id.in_(allowed) if allowed else t.id.is_(None))
    if workspace_id:
        conds.append(t.workspace_id == uuid.UUID(workspace_id))
    if app_id:
        conds.append(t.app_id == uuid.UUID(app_id))
    if channel:
        conds.append(t.channel == channel)
    if component:
        conds.append(t.component == component)

    async def grouped(*cols, order_total=True, limit=None):
        stmt = select(*cols, *_sums()).where(*conds).group_by(*cols)
        if order_total:
            stmt = stmt.order_by(func.sum(t.total_tokens).desc())
        if limit:
            stmt = stmt.limit(limit)
        return (await db.execute(stmt)).all()

    totals = _bucket("all", (await db.execute(select(*_sums()).where(*conds))).one())

    # per day × component, every day of the period present so the chart has no gaps
    day_col = cast(func.date_trunc("day", func.timezone(LOCAL_TZ, t.created_at)), type_=t.created_at.type)
    day_rows = (await db.execute(
        select(day_col, t.component, func.coalesce(func.sum(t.total_tokens), 0))
        .where(*conds).group_by(day_col, t.component)
    )).all()
    per_day: dict[date, dict[str, int]] = {}
    for day, comp, total in day_rows:
        per_day.setdefault(day.date(), {})[comp] = int(total)
    by_day = []
    for i in range(days):
        d = first_day + timedelta(days=i)
        comps = per_day.get(d, {})
        by_day.append(UsageDay(day=d.isoformat(), total_tokens=sum(comps.values()), by_component=comps))

    by_component = [_bucket(k, rest) for k, *rest in await grouped(t.component)]
    by_component.sort(key=lambda b: COMPONENTS.index(b.key) if b.key in COMPONENTS else len(COMPONENTS))
    by_purpose = [_bucket(k, rest) for k, *rest in await grouped(t.purpose)]
    by_channel = [_bucket(k, rest) for k, *rest in await grouped(t.channel)]

    app_rows = await grouped(t.app_id, limit=50)
    app_names = {a.id: a.name for a in (await db.execute(
        select(App).where(App.id.in_([r[0] for r in app_rows if r[0]])))).scalars()} if app_rows else {}
    by_app = [_bucket(k, rest, label=(app_names.get(k, "(trợ lý đã xoá)") if k else None)) for k, *rest in app_rows]

    ws_rows = await grouped(t.workspace_id)
    ws_names = {w.id: w.name for w in (await db.execute(
        select(Workspace).where(Workspace.id.in_([r[0] for r in ws_rows if r[0]])))).scalars()} if ws_rows else {}
    by_workspace = [_bucket(k, rest, label=(ws_names.get(k, "(đơn vị đã xoá)") if k else None)) for k, *rest in ws_rows]

    by_model = [_bucket(f"{prov or '?'} · {model or '?'}", rest, label=purpose)
                for prov, model, purpose, *rest in await grouped(t.provider, t.model, t.purpose)]

    return UsageSummary(
        days=days, since=since.isoformat(), totals=totals, by_day=by_day, by_component=by_component,
        by_purpose=by_purpose, by_channel=by_channel, by_app=by_app, by_workspace=by_workspace, by_model=by_model,
    )


async def run_token_totals(db: AsyncSession, run_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Total tokens per audit run (one query for a page of runs)."""
    if not run_ids:
        return {}
    rows = await db.execute(
        select(TokenUsage.run_id, cast(func.sum(TokenUsage.total_tokens), Integer))
        .where(TokenUsage.run_id.in_(run_ids)).group_by(TokenUsage.run_id)
    )
    return {rid: int(total or 0) for rid, total in rows.all()}


async def run_usage(db: AsyncSession, run_id: uuid.UUID) -> list[UsageBucket]:
    t = TokenUsage
    rows = (await db.execute(select(t.component, *_sums()).where(t.run_id == run_id).group_by(t.component))).all()
    out = [_bucket(k, rest) for k, *rest in rows]
    out.sort(key=lambda b: COMPONENTS.index(b.key) if b.key in COMPONENTS else len(COMPONENTS))
    return out

"""Report schedules: cron rows the ticker (app/scheduler.py) fires.

Unit-scoped like workflows: an editor of the unit creates and edits them, and a schedule may
only point at a workflow of the same unit.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import WorkspaceContext, require_ws_role
from app.config import settings
from app.deps import get_db
from app.models.run import Run
from app.models.schedule import Schedule
from app.models.user_workspace import WsRole
from app.models.workflow import Workflow
from app.services.jobs import enqueue_workflow_run
from app.services.observability import create_run
from app.services.scheduling import DEFAULT_TZ, ScheduleError, describe_cron, next_runs, validate_cron

router = APIRouter(prefix="/v1", tags=["schedules"])

POSITIONS = ("RM", "CA", "GDV", "OPS", "CCO", "KSV")


class ScheduleCreate(BaseModel):
    workflow_id: str
    name: str = Field(..., min_length=1, max_length=256)
    cron: str = Field(..., min_length=1, max_length=64)
    timezone: str = DEFAULT_TZ
    inputs: dict[str, Any] = {}
    enabled: bool = True
    deliver_positions: list[str] = []
    retention_days: int = Field(30, ge=1, le=365)


class ScheduleUpdate(BaseModel):
    name: str | None = None
    cron: str | None = None
    timezone: str | None = None
    inputs: dict[str, Any] | None = None
    enabled: bool | None = None
    deliver_positions: list[str] | None = None
    retention_days: int | None = Field(None, ge=1, le=365)


class ScheduleResponse(BaseModel):
    id: str
    workspace_id: str
    workflow_id: str
    workflow_name: str | None
    name: str
    cron: str
    cron_label: str
    timezone: str
    inputs: dict[str, Any]
    enabled: bool
    deliver_positions: list[str]
    retention_days: int
    next_run_at: str | None
    last_enqueued_at: str | None
    last_run_id: str | None
    last_status: str | None
    created_at: str
    updated_at: str


class SchedulerStatus(BaseModel):
    """Whether the ticker process is alive — otherwise nothing fires and the UI should say so."""
    running: bool
    last_heartbeat: str | None


def _to_response(s: Schedule, workflow_name: str | None = None, last_status: str | None = None) -> ScheduleResponse:
    return ScheduleResponse(
        id=str(s.id), workspace_id=str(s.workspace_id), workflow_id=str(s.workflow_id),
        workflow_name=workflow_name, name=s.name, cron=s.cron, cron_label=describe_cron(s.cron),
        timezone=s.timezone, inputs=dict(s.inputs or {}), enabled=s.enabled,
        deliver_positions=list(s.deliver_positions or []), retention_days=s.retention_days,
        next_run_at=s.next_run_at.isoformat() if s.next_run_at else None,
        last_enqueued_at=s.last_enqueued_at.isoformat() if s.last_enqueued_at else None,
        last_run_id=str(s.last_run_id) if s.last_run_id else None, last_status=last_status,
        created_at=s.created_at.isoformat(), updated_at=s.updated_at.isoformat(),
    )


async def _workflow_of_unit(db: AsyncSession, workflow_id: str, workspace_id) -> Workflow:
    try:
        wf_id = uuid.UUID(workflow_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="workflow_id không hợp lệ")
    wf = (await db.execute(select(Workflow).where(
        Workflow.id == wf_id, Workflow.workspace_id == workspace_id))).scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Luồng xử lý không thuộc đơn vị này")
    return wf


async def _get_schedule(db: AsyncSession, schedule_id: str, workspace_id) -> Schedule:
    try:
        sid = uuid.UUID(schedule_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch chạy")
    schedule = (await db.execute(select(Schedule).where(
        Schedule.id == sid, Schedule.workspace_id == workspace_id))).scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch chạy trong đơn vị này")
    return schedule


def _check_positions(positions: list[str]) -> list[str]:
    bad = [p for p in positions if p not in POSITIONS]
    if bad:
        raise HTTPException(status_code=400, detail=f"Chức danh không hợp lệ: {', '.join(bad)}")
    return positions


async def _last_statuses(db: AsyncSession, schedules: list[Schedule]) -> dict[uuid.UUID, str]:
    ids = [s.last_run_id for s in schedules if s.last_run_id]
    if not ids:
        return {}
    rows = (await db.execute(select(Run.id, Run.status).where(Run.id.in_(ids)))).all()
    return {rid: status for rid, status in rows}


@router.get("/schedules", response_model=list[ScheduleResponse])
async def list_schedules(
    workflow_id: str | None = None,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Schedule).where(Schedule.workspace_id == ws_ctx.workspace_id).order_by(Schedule.created_at.desc())
    if workflow_id:
        stmt = stmt.where(Schedule.workflow_id == uuid.UUID(workflow_id))
    rows = list((await db.execute(stmt)).scalars().all())
    names = {w.id: w.name for w in (await db.execute(
        select(Workflow).where(Workflow.workspace_id == ws_ctx.workspace_id))).scalars()}
    statuses = await _last_statuses(db, rows)
    return [_to_response(s, names.get(s.workflow_id), statuses.get(s.last_run_id)) for s in rows]


@router.get("/schedules/status", response_model=SchedulerStatus)
async def scheduler_status():
    """Heartbeat of the ticker process (app/scheduler.py), refreshed every tick."""
    from app.scheduler import HEARTBEAT_KEY

    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.REDIS_URL)
        raw = await client.get(HEARTBEAT_KEY)
        await client.aclose()
    except Exception:
        return SchedulerStatus(running=False, last_heartbeat=None)
    beat = raw.decode() if isinstance(raw, bytes) else raw
    return SchedulerStatus(running=bool(beat), last_heartbeat=beat)


@router.post("/schedules", response_model=ScheduleResponse, status_code=201)
async def create_schedule(
    body: ScheduleCreate,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    wf = await _workflow_of_unit(db, body.workflow_id, ws_ctx.workspace_id)
    try:
        cron = validate_cron(body.cron)
        first = next_runs(cron, body.timezone, 1)[0]
    except ScheduleError as e:
        raise HTTPException(status_code=400, detail=str(e))

    schedule = Schedule(
        workspace_id=ws_ctx.workspace_id, workflow_id=wf.id, name=body.name, cron=cron,
        timezone=body.timezone or DEFAULT_TZ, inputs=body.inputs or {}, enabled=body.enabled,
        deliver_positions=_check_positions(body.deliver_positions or []),
        retention_days=body.retention_days, next_run_at=first if body.enabled else None,
        created_by_user_id=ws_ctx.user.id,
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    return _to_response(schedule, wf.name)


@router.patch("/schedules/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: str,
    body: ScheduleUpdate,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    schedule = await _get_schedule(db, schedule_id, ws_ctx.workspace_id)
    data = body.model_dump(exclude_unset=True)

    if "cron" in data or "timezone" in data:
        try:
            cron = validate_cron(data.get("cron", schedule.cron))
            tz = data.get("timezone") or schedule.timezone
            schedule.cron, schedule.timezone = cron, tz
            schedule.next_run_at = next_runs(cron, tz, 1)[0]
        except ScheduleError as e:
            raise HTTPException(status_code=400, detail=str(e))
    for key in ("name", "inputs", "retention_days"):
        if key in data and data[key] is not None:
            setattr(schedule, key, data[key])
    if data.get("deliver_positions") is not None:
        schedule.deliver_positions = _check_positions(data["deliver_positions"])
    if "enabled" in data and data["enabled"] is not None:
        schedule.enabled = data["enabled"]
        # Turning it back on must not fire every slot missed while it was off.
        schedule.next_run_at = next_runs(schedule.cron, schedule.timezone, 1)[0] if schedule.enabled else None

    schedule.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(schedule)
    wf = await db.get(Workflow, schedule.workflow_id)
    return _to_response(schedule, wf.name if wf else None)


@router.delete("/schedules/{schedule_id}", status_code=204)
async def delete_schedule(
    schedule_id: str,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    schedule = await _get_schedule(db, schedule_id, ws_ctx.workspace_id)
    await db.delete(schedule)
    await db.commit()


@router.post("/schedules/{schedule_id}/run-now", status_code=202)
async def run_schedule_now(
    schedule_id: str,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    """Queue the schedule immediately, with the same inputs and delivery as the cron run."""
    schedule = await _get_schedule(db, schedule_id, ws_ctx.workspace_id)
    wf = await db.get(Workflow, schedule.workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Luồng xử lý đã bị xoá")

    run = await create_run(db, workflow_id=wf.id, workspace_id=schedule.workspace_id,
                           user_id=ws_ctx.user.id, channel="scheduled", query=schedule.name)
    run.status = "queued"
    await db.flush()
    try:
        job_id = enqueue_workflow_run(run.id, wf.id, dict(schedule.inputs or {}), schedule_id=schedule.id)
    except Exception:
        run.status = "failed"
        run.error = "Không xếp được hàng đợi"
        await db.commit()
        raise HTTPException(status_code=503, detail="Hàng đợi công việc không sẵn sàng (Redis)")
    schedule.last_run_id = run.id
    schedule.last_enqueued_at = datetime.now(timezone.utc)
    await db.commit()
    return {"run_id": str(run.id), "job_id": job_id, "status": "queued"}


@router.get("/schedules/preview")
async def preview_schedule(
    cron: str = Query(..., max_length=64),
    timezone_name: str = Query(DEFAULT_TZ, alias="timezone", max_length=64),
    _: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
):
    """Next fire times for a cron expression, so the editor can show them before saving."""
    try:
        return {"cron_label": describe_cron(cron),
                "next_runs": [d.isoformat() for d in next_runs(cron, timezone_name, 5)]}
    except ScheduleError as e:
        raise HTTPException(status_code=400, detail=str(e))

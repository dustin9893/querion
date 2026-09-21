"""Apps CRUD router + embedded Runs read endpoints."""

import uuid
import secrets
from typing import Any

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.auth.deps import require_ws_role, WorkspaceContext
from app.models.user_workspace import WsRole
from app.models.app import App, AppDataset
from app.models.dataset import Dataset
from app.models.tool import AppTool, Tool
from app.models.skill import AppSkill, Skill
from app.models.run import Run, RunStep
from app.services.embed import validate_origins, validate_widget_config
from app.services.extension import validate_hosts
from app.services.branding import MAX_LOGO_BYTES, logo_url, remove_logo, store_logo

router = APIRouter(prefix="/v1", tags=["apps"])


# ---------- Schemas ----------

class AppCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    workflow_id: str | None = None
    dataset_ids: list[str] = []   # knowledge bases for RAG, in priority order
    model_config_json: dict[str, Any] | None = None
    system_prompt: str | None = ""
    audience: str = "staff"  # staff | customer
    description: str | None = ""
    tool_ids: list[str] = []      # bound at creation like on update, instead of being dropped
    skill_ids: list[str] = []     # playbooks the assistant may load on demand
    memory_enabled: bool | None = None   # personal staff memory on this assistant
    agent_enabled: bool | None = None


class AppUpdate(BaseModel):
    name: str | None = None
    workflow_id: str | None = None
    dataset_ids: list[str] | None = None   # replaces the whole set of bound knowledge bases
    model_config_json: dict[str, Any] | None = None
    system_prompt: str | None = None
    description: str | None = None
    is_published: bool | None = None
    audience: str | None = None
    embed_enabled: bool | None = None
    allowed_origins: list[str] | None = None
    extension_enabled: bool | None = None   # browser extension may offer this assistant (staff only)
    extension_hosts: list[str] | None = None  # intranet host patterns where the bubble opens it by default
    widget_config: dict[str, Any] | None = None
    share_scope: str | None = None  # unit | bank — owner only
    agent_enabled: bool | None = None
    tool_ids: list[str] | None = None   # replaces the whole set of bound tools
    skill_ids: list[str] | None = None  # replaces the whole set of bound skills
    skill_match_threshold: float | None = None
    memory_enabled: bool | None = None


class AppResponse(BaseModel):
    id: str
    name: str
    workflow_id: str | None
    dataset_ids: list[str] = []
    model_config_json: dict[str, Any] | None
    system_prompt: str | None
    api_key: str
    description: str | None
    is_published: bool
    audience: str
    embed_enabled: bool = False
    allowed_origins: list[str] = []
    extension_enabled: bool = False
    extension_hosts: list[str] = []
    widget_config: dict[str, Any] = {}
    logo_url: str | None = None  # API-relative; POST /apps/{id}/logo sets it
    share_scope: str = "unit"    # unit (staff of this unit only) | bank (every employee)
    agent_enabled: bool = False
    tool_ids: list[str] = []
    skill_ids: list[str] = []
    skill_match_threshold: float = 0.32
    memory_enabled: bool = True
    created_at: str
    updated_at: str


class RunResponse(BaseModel):
    id: str
    app_id: str | None
    workflow_id: str | None
    conversation_id: str | None
    status: str
    started_at: str
    ended_at: str | None
    latency_ms: int | None


class RunStepResponse(BaseModel):
    id: str
    node_id: str
    node_type: str
    started_at: str
    ended_at: str | None
    duration_ms: int | None
    input_json: dict[str, Any] | None
    output_json: dict[str, Any] | None


# ---------- Helpers ----------
MAX_DATASETS = 10


async def _dataset_ids(db: AsyncSession, app_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    """Bound knowledge bases per assistant, in admin-chosen order (one query for a whole list)."""
    out: dict[uuid.UUID, list[str]] = {a: [] for a in app_ids}
    if app_ids:
        rows = await db.execute(select(AppDataset.app_id, AppDataset.dataset_id)
                                .where(AppDataset.app_id.in_(app_ids)).order_by(AppDataset.position))
        for app_id, dataset_id in rows.all():
            out[app_id].append(str(dataset_id))
    return out


def _parse_dataset_ids(raw: list[str]) -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []
    for value in raw:
        try:
            ds_id = uuid.UUID(value)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="dataset_ids không hợp lệ")
        if ds_id not in ids:
            ids.append(ds_id)
    if len(ids) > MAX_DATASETS:
        raise HTTPException(status_code=400, detail=f"Một trợ lý gắn tối đa {MAX_DATASETS} kho tri thức")
    return ids


async def _set_datasets(db: AsyncSession, app: App, wanted: list[uuid.UUID]) -> None:
    """Replace the assistant's knowledge bases. Each must belong to the assistant's own unit."""
    if wanted:
        rows = await db.execute(select(Dataset.id).where(Dataset.id.in_(wanted), Dataset.workspace_id == app.workspace_id))
        if len({r[0] for r in rows.all()}) != len(wanted):
            raise HTTPException(status_code=400, detail="Kho tri thức không tồn tại hoặc không thuộc đơn vị này")
    await db.execute(delete(AppDataset).where(AppDataset.app_id == app.id))
    for position, ds_id in enumerate(wanted):
        db.add(AppDataset(app_id=app.id, dataset_id=ds_id, position=position))


async def _full_response(db: AsyncSession, app: App) -> AppResponse:
    return _to_response(app, await _tool_ids(db, app), (await _dataset_ids(db, [app.id]))[app.id],
                        await _skill_ids(db, app))


async def _tool_ids(db: AsyncSession, app: App) -> list[str]:
    rows = await db.execute(select(AppTool.tool_id).where(AppTool.app_id == app.id))
    return [str(r[0]) for r in rows.all()]


async def _set_tools(db: AsyncSession, app: App, tool_ids: list[str]) -> None:
    """Replace the assistant's tool set. A tool must belong to this unit or be shared bank-wide."""
    wanted: set = set()
    for raw in tool_ids[:20]:
        try:
            wanted.add(uuid.UUID(raw))
        except ValueError:
            raise HTTPException(status_code=400, detail="tool_ids không hợp lệ")
    if wanted:
        rows = await db.execute(select(Tool).where(Tool.id.in_(wanted)))
        found = {t.id: t for t in rows.scalars().all()}
        for tid in wanted:
            tool = found.get(tid)
            if not tool or (tool.workspace_id != app.workspace_id and (tool.share_scope or "unit") != "bank"):
                raise HTTPException(status_code=400, detail="Công cụ không thuộc đơn vị này và chưa được chia sẻ toàn ngân hàng")
            if app.audience == "customer" and not tool.allow_customer:
                raise HTTPException(status_code=400, detail=f"Công cụ '{tool.name}' chưa được phép dùng ở kênh khách hàng")
    current = {r[0] for r in (await db.execute(select(AppTool.tool_id).where(AppTool.app_id == app.id))).all()}
    for tid in current - wanted:
        await db.execute(delete(AppTool).where(AppTool.app_id == app.id, AppTool.tool_id == tid))
    for tid in wanted - current:
        db.add(AppTool(app_id=app.id, tool_id=tid))


async def _skill_ids(db: AsyncSession, app: App) -> list[str]:
    rows = await db.execute(select(AppSkill.skill_id).where(AppSkill.app_id == app.id)
                            .order_by(AppSkill.position))
    return [str(r[0]) for r in rows.all()]


async def _set_skills(db: AsyncSession, app: App, skill_ids: list[str]) -> None:
    """Replace the assistant's skill set.

    Same rule as tools: own unit, or published and shared bank-wide. A customer assistant may only
    bind skills an owner explicitly opened to the customer channel, because a playbook shapes what
    the assistant says to people outside the bank.
    """
    wanted: list[uuid.UUID] = []
    for raw in skill_ids[:20]:
        try:
            value = uuid.UUID(raw)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="skill_ids không hợp lệ")
        if value not in wanted:
            wanted.append(value)
    if wanted:
        rows = await db.execute(select(Skill).where(Skill.id.in_(wanted)))
        found = {s.id: s for s in rows.scalars().all()}
        for sid in wanted:
            skill = found.get(sid)
            if not skill or (skill.workspace_id != app.workspace_id
                             and not (skill.share_scope == "bank" and skill.status == "published")):
                raise HTTPException(status_code=400,
                                    detail="Kỹ năng không thuộc đơn vị này và chưa được chia sẻ toàn ngân hàng")
            if app.audience == "customer" and not skill.allow_customer:
                raise HTTPException(status_code=400,
                                    detail=f"Kỹ năng '{skill.name}' chưa được phép dùng ở kênh khách hàng")
    await db.execute(delete(AppSkill).where(AppSkill.app_id == app.id))
    for position, sid in enumerate(wanted):
        db.add(AppSkill(app_id=app.id, skill_id=sid, position=position))


def _to_response(app: App, tool_ids: list[str] | None = None, dataset_ids: list[str] | None = None,
                 skill_ids: list[str] | None = None) -> AppResponse:
    return AppResponse(
        id=str(app.id),
        name=app.name,
        workflow_id=str(app.workflow_id) if app.workflow_id else None,
        dataset_ids=dataset_ids or [],
        model_config_json=app.model_config_json,
        system_prompt=app.system_prompt,
        api_key=app.api_key,
        audience=app.audience,
        embed_enabled=bool(app.embed_enabled),
        allowed_origins=list(app.allowed_origins or []),
        extension_enabled=bool(getattr(app, "extension_enabled", False)),
        extension_hosts=list(getattr(app, "extension_hosts", None) or []),
        widget_config=dict(app.widget_config or {}),
        logo_url=logo_url(app),
        share_scope=app.share_scope or "unit",
        agent_enabled=bool(getattr(app, "agent_enabled", False)),
        tool_ids=tool_ids or [],
        skill_ids=skill_ids or [],
        skill_match_threshold=float(getattr(app, "skill_match_threshold", 0.32) or 0.32),
        memory_enabled=bool(getattr(app, "memory_enabled", True)),
        description=app.description,
        is_published=app.is_published,
        created_at=app.created_at.isoformat(),
        updated_at=app.updated_at.isoformat(),
    )


def _run_to_response(run: Run) -> RunResponse:
    return RunResponse(
        id=str(run.id),
        app_id=str(run.app_id) if run.app_id else None,
        workflow_id=str(run.workflow_id) if run.workflow_id else None,
        conversation_id=str(run.conversation_id) if run.conversation_id else None,
        status=run.status,
        started_at=run.started_at.isoformat(),
        ended_at=run.ended_at.isoformat() if run.ended_at else None,
        latency_ms=run.latency_ms,
    )


def _step_to_response(step: RunStep) -> RunStepResponse:
    duration = None
    if step.started_at and step.ended_at:
        duration = int((step.ended_at - step.started_at).total_seconds() * 1000)
    return RunStepResponse(
        id=str(step.id),
        node_id=step.node_id,
        node_type=step.node_type,
        started_at=step.started_at.isoformat(),
        ended_at=step.ended_at.isoformat() if step.ended_at else None,
        duration_ms=duration,
        input_json=step.input_json,
        output_json=step.output_json,
    )


# ---------- App CRUD ----------

AUDIENCES = {"staff", "customer"}


async def _check_chat_workflow(db: AsyncSession, workflow_id: str | None, workspace_id,
                               *, current=None) -> None:
    """A chat assistant runs its workflow on every message, so a report workflow does not belong
    here — it is a scheduled job that writes files. Reports reach chat through a report tool.

    ``current`` is what the assistant already points at: an assistant bound before this rule
    existed must still be editable, otherwise every save on it fails and the owner cannot even
    unbind the workflow or add a tool. Only a *new* report workflow is refused.
    """
    from app.models.workflow import Workflow

    if not workflow_id:
        return
    if current is not None and str(current) == str(workflow_id):
        return
    try:
        wf = await db.get(Workflow, uuid.UUID(workflow_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="workflow_id không hợp lệ")
    if wf is None or wf.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Luồng xử lý không thuộc đơn vị này")
    if wf.type == "report":
        raise HTTPException(
            status_code=400,
            detail="Luồng báo cáo chạy nền và xuất tệp, không gắn trực tiếp vào trợ lý. "
                   "Hãy tạo Công cụ loại 'Báo cáo' trỏ tới luồng này rồi gắn công cụ cho trợ lý.",
        )


async def _validate_audience(db: AsyncSession, audience: str, dataset_ids: list[uuid.UUID]) -> None:
    """Customer-facing assistants may only read datasets marked public — every one of them."""
    if audience not in AUDIENCES:
        raise HTTPException(status_code=400, detail=f"audience must be one of {sorted(AUDIENCES)}")
    if audience == "customer" and dataset_ids:
        rows = await db.execute(select(Dataset.name).where(Dataset.id.in_(dataset_ids), Dataset.visibility != "public"))
        internal = [r[0] for r in rows.all()]
        if internal:
            raise HTTPException(
                status_code=400,
                detail="Trợ lý dành cho khách hàng chỉ được gắn kho tri thức có visibility = public "
                       f"(kho nội bộ: {', '.join(internal)})",
            )


@router.post("/apps", response_model=AppResponse, status_code=201)
async def create_app(
    body: AppCreate,
    db: AsyncSession = Depends(get_db),
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
):
    dataset_ids = _parse_dataset_ids(body.dataset_ids)
    await _validate_audience(db, body.audience, dataset_ids)
    await _check_chat_workflow(db, body.workflow_id, ws_ctx.workspace_id)
    app = App(
        workspace_id=ws_ctx.workspace_id,
        name=body.name,
        workflow_id=uuid.UUID(body.workflow_id) if body.workflow_id else None,
        model_config_json=body.model_config_json or {},
        system_prompt=body.system_prompt or "",
        audience=body.audience,
        description=body.description or "",
        # binding a tool is only meaningful with the agent on, so default to it when tools are given
        agent_enabled=bool(body.agent_enabled if body.agent_enabled is not None else body.tool_ids),
    )
    db.add(app)
    await db.flush()
    await _set_datasets(db, app, dataset_ids)
    if body.tool_ids:
        await _set_tools(db, app, body.tool_ids)
    if body.skill_ids:
        await _set_skills(db, app, body.skill_ids)
    if body.memory_enabled is not None:
        app.memory_enabled = bool(body.memory_enabled)
    await db.commit()
    await db.refresh(app)
    return await _full_response(db, app)


@router.get("/apps", response_model=list[AppResponse])
async def list_apps(
    db: AsyncSession = Depends(get_db),
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
):
    result = await db.execute(
        select(App)
        .where(App.workspace_id == ws_ctx.workspace_id)
        .order_by(App.created_at.desc())
    )
    apps = list(result.scalars().all())
    datasets = await _dataset_ids(db, [a.id for a in apps])
    return [_to_response(a, dataset_ids=datasets[a.id]) for a in apps]


@router.get("/apps/{app_id}", response_model=AppResponse)
async def get_app(
    app_id: str,
    db: AsyncSession = Depends(get_db),
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
):
    app = await db.get(App, uuid.UUID(app_id))
    if not app or app.workspace_id != ws_ctx.workspace_id:
        raise HTTPException(status_code=404, detail="App not found")
    return await _full_response(db, app)


@router.patch("/apps/{app_id}", response_model=AppResponse)
async def update_app(
    app_id: str,
    body: AppUpdate,
    db: AsyncSession = Depends(get_db),
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
):
    app = await db.get(App, uuid.UUID(app_id))
    if not app or app.workspace_id != ws_ctx.workspace_id:
        raise HTTPException(status_code=404, detail="App not found")

    if body.name is not None:
        app.name = body.name
    if body.workflow_id is not None:
        await _check_chat_workflow(db, body.workflow_id, ws_ctx.workspace_id, current=app.workflow_id)
        app.workflow_id = uuid.UUID(body.workflow_id) if body.workflow_id else None
    if body.dataset_ids is not None:
        dataset_ids = _parse_dataset_ids(body.dataset_ids)
        await _set_datasets(db, app, dataset_ids)
    else:
        dataset_ids = [uuid.UUID(d) for d in (await _dataset_ids(db, [app.id]))[app.id]]
    if body.model_config_json is not None:
        app.model_config_json = body.model_config_json
    if body.system_prompt is not None:
        app.system_prompt = body.system_prompt
    if body.description is not None:
        app.description = body.description
    if body.is_published is not None:
        app.is_published = body.is_published
    if body.audience is not None:
        app.audience = body.audience
    if body.allowed_origins is not None:
        app.allowed_origins = validate_origins(body.allowed_origins)
    if body.widget_config is not None:
        app.widget_config = validate_widget_config(body.widget_config)
    if body.embed_enabled is not None:
        if body.embed_enabled and not (app.allowed_origins or []):
            raise HTTPException(status_code=400, detail="Thêm ít nhất một website được phép (origin) trước khi bật nhúng")
        app.embed_enabled = body.embed_enabled
    if body.extension_hosts is not None:
        app.extension_hosts = validate_hosts(body.extension_hosts)
    if body.extension_enabled is not None:
        # the bubble is a staff surface: a customer assistant has no business there
        if body.extension_enabled and app.audience == "customer":
            raise HTTPException(status_code=400, detail="Trợ lý khách hàng không dùng được trong browser extension của cán bộ")
        app.extension_enabled = body.extension_enabled
    if app.audience == "customer" and app.extension_enabled and body.audience is not None:
        app.extension_enabled = False   # switching to customer audience drops the extension surface
    if body.agent_enabled is not None:
        app.agent_enabled = body.agent_enabled
    if body.skill_ids is not None:
        await _set_skills(db, app, body.skill_ids)
    if body.skill_match_threshold is not None:
        if not 0.0 <= body.skill_match_threshold <= 1.0:
            raise HTTPException(status_code=400, detail="Ngưỡng khớp kỹ năng phải nằm trong khoảng 0 đến 1")
        app.skill_match_threshold = body.skill_match_threshold
    if body.memory_enabled is not None:
        app.memory_enabled = bool(body.memory_enabled)
    if body.tool_ids is not None:
        await _set_tools(db, app, body.tool_ids)
    if body.share_scope is not None and body.share_scope != (app.share_scope or "unit"):
        # Opening an assistant to the whole bank is a cross-unit decision → workspace owner only
        if body.share_scope not in ("unit", "bank"):
            raise HTTPException(status_code=400, detail="share_scope must be 'unit' or 'bank'")
        if not ws_ctx.has_role(WsRole.owner):
            raise HTTPException(status_code=403, detail="Chỉ chủ đơn vị (owner) mới được đổi phạm vi hiển thị của trợ lý")
        app.share_scope = body.share_scope

    await _validate_audience(db, app.audience, dataset_ids)

    await db.commit()
    await db.refresh(app)
    return await _full_response(db, app)


@router.delete("/apps/{app_id}", status_code=204)
async def delete_app(
    app_id: str,
    db: AsyncSession = Depends(get_db),
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
):
    app = await db.get(App, uuid.UUID(app_id))
    if not app or app.workspace_id != ws_ctx.workspace_id:
        raise HTTPException(status_code=404, detail="App not found")
    remove_logo(app)  # best effort: drop the stored image with the assistant
    await db.delete(app)
    await db.commit()


@router.post("/apps/{app_id}/regenerate-key", response_model=AppResponse)
async def regenerate_api_key(
    app_id: str,
    db: AsyncSession = Depends(get_db),
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
):
    app = await db.get(App, uuid.UUID(app_id))
    if not app or app.workspace_id != ws_ctx.workspace_id:
        raise HTTPException(status_code=404, detail="App not found")
    app.api_key = f"app-{secrets.token_urlsafe(32)}"
    await db.commit()
    await db.refresh(app)
    return await _full_response(db, app)


@router.post("/apps/{app_id}/logo", response_model=AppResponse)
async def upload_app_logo(
    app_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
):
    """Upload the assistant's logo / avatar (PNG, JPG, WebP, GIF, ICO ≤ 1 MB, or a script-free SVG).

    Rasters are re-encoded as PNG ≤ 512 px; the result is shown on the chat bubble, the chat
    header, the customer page and the staff portal. Replaces any previous logo."""
    app = await db.get(App, uuid.UUID(app_id))
    if not app or app.workspace_id != ws_ctx.workspace_id:
        raise HTTPException(status_code=404, detail="App not found")
    data = await file.read(MAX_LOGO_BYTES + 1)  # one extra byte lets the validator detect oversize
    store_logo(app, data)                       # 400 with a Vietnamese message on invalid input
    await db.commit()
    await db.refresh(app)
    return await _full_response(db, app)


@router.delete("/apps/{app_id}/logo", response_model=AppResponse)
async def delete_app_logo(
    app_id: str,
    db: AsyncSession = Depends(get_db),
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
):
    app = await db.get(App, uuid.UUID(app_id))
    if not app or app.workspace_id != ws_ctx.workspace_id:
        raise HTTPException(status_code=404, detail="App not found")
    remove_logo(app)
    await db.commit()
    await db.refresh(app)
    return await _full_response(db, app)


# ---------- Runs (read-only, nested under app) ----------

@router.get("/apps/{app_id}/runs", response_model=list[RunResponse])
async def list_runs(
    app_id: str,
    db: AsyncSession = Depends(get_db),
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
):
    # Verify app belongs to workspace
    app = await db.get(App, uuid.UUID(app_id))
    if not app or app.workspace_id != ws_ctx.workspace_id:
        raise HTTPException(status_code=404, detail="App not found")

    result = await db.execute(
        select(Run)
        .where(Run.app_id == uuid.UUID(app_id))
        .order_by(Run.started_at.desc())
        .limit(50)
    )
    return [_run_to_response(r) for r in result.scalars().all()]


@router.get("/runs/{run_id}/steps", response_model=list[RunStepResponse])
async def get_run_steps(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
):
    result = await db.execute(
        select(RunStep)
        .where(RunStep.run_id == uuid.UUID(run_id))
        .order_by(RunStep.started_at)
    )
    return [_step_to_response(s) for s in result.scalars().all()]

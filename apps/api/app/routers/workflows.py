"""Workflows router — CRUD + test run."""

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.auth.deps import require_ws_role, WorkspaceContext
from app.models.user_workspace import WsRole
from app.models.workflow import Workflow
from app.services.workflow_validator import validate_graph, ValidationError
from app.services.workflow_runtime import run_workflow
from app.services.observability import create_run, complete_run
from app.services.pii import mask_pii
from app.models.artifact import Artifact
from app.models.run import Run
from app.routers.artifacts import ArtifactResponse, to_response as artifact_to_response
from app.services.jobs import enqueue_workflow_run
from app.services.reports import ReportError, docx_variables, template_storage_key
from app.storage import upload_file

router = APIRouter(prefix="/v1", tags=["workflows"])

MAX_TEMPLATE_BYTES = 5 * 1024 * 1024


# ---------- Schemas ----------

class WorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    type: str = "chatflow"  # chatflow | workflow
    description: str | None = ""
    dataset_id: str | None = None
    graph_json: dict[str, Any] = Field(default_factory=lambda: {"nodes": [], "edges": []})


class WorkflowUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    description: str | None = None
    dataset_id: str | None = None
    graph_json: dict[str, Any] | None = None


class WorkflowResponse(BaseModel):
    id: str
    type: str
    name: str
    description: str | None
    dataset_id: str | None
    graph_json: dict[str, Any]
    node_count: int
    created_at: str
    updated_at: str


class RunRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=10000)
    inputs: dict[str, Any] | None = None


class JobResponse(BaseModel):
    run_id: str
    job_id: str
    status: str


class WorkflowRunRow(BaseModel):
    """One past run of this workflow, with the files it produced."""
    id: str
    status: str
    channel: str
    started_at: str
    ended_at: str | None
    latency_ms: int | None
    error: str | None
    answer_preview: str | None
    schedule_id: str | None = None
    artifacts: list[ArtifactResponse] = []


class TemplateUploadResponse(BaseModel):
    template_key: str
    filename: str
    variables: list[str]


class RunResponse(BaseModel):
    answer: str
    extracted_params: dict[str, Any] = {}
    retriever_resources: list[dict[str, Any]]
    artifacts: list[dict[str, Any]] = []


def _to_response(wf: Workflow) -> WorkflowResponse:
    graph = wf.graph_json or {}
    return WorkflowResponse(
        id=str(wf.id),
        type=wf.type,
        name=wf.name,
        description=wf.description,
        dataset_id=str(wf.dataset_id) if wf.dataset_id else None,
        graph_json=graph,
        node_count=len(graph.get("nodes", [])),
        created_at=wf.created_at.isoformat(),
        updated_at=wf.updated_at.isoformat(),
    )


# ---------- CRUD ----------

@router.post("/workflows", response_model=WorkflowResponse, status_code=201)
async def create_workflow(
    body: WorkflowCreate,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new workflow."""
    # Validate graph if provided
    if body.graph_json.get("nodes"):
        try:
            validate_graph(body.graph_json)
        except ValidationError as e:
            raise HTTPException(status_code=400, detail=str(e))

    wf = Workflow(
        workspace_id=ws_ctx.workspace_id,
        type=body.type,
        name=body.name,
        description=body.description,
        dataset_id=uuid.UUID(body.dataset_id) if body.dataset_id else None,
        graph_json=body.graph_json,
    )
    db.add(wf)
    await db.commit()
    await db.refresh(wf)
    return _to_response(wf)


@router.get("/workflows", response_model=list[WorkflowResponse])
async def list_workflows(
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    """List workflows for the current workspace."""
    result = await db.execute(
        select(Workflow)
        .where(Workflow.workspace_id == ws_ctx.workspace_id)
        .order_by(Workflow.updated_at.desc())
    )
    return [_to_response(wf) for wf in result.scalars().all()]


@router.get("/workflows/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: str,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    """Get a workflow by ID."""
    wf = await _get_workflow(db, workflow_id, ws_ctx.workspace_id)
    return _to_response(wf)


@router.patch("/workflows/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: str,
    body: WorkflowUpdate,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    """Update a workflow."""
    wf = await _get_workflow(db, workflow_id, ws_ctx.workspace_id)

    if body.name is not None:
        wf.name = body.name
    if body.type is not None:
        wf.type = body.type
    if body.description is not None:
        wf.description = body.description
    if body.dataset_id is not None:
        wf.dataset_id = uuid.UUID(body.dataset_id) if body.dataset_id else None
    if body.graph_json is not None:
        # Validate new graph
        if body.graph_json.get("nodes"):
            try:
                validate_graph(body.graph_json)
            except ValidationError as e:
                raise HTTPException(status_code=400, detail=str(e))
        wf.graph_json = body.graph_json

    wf.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(wf)
    return _to_response(wf)


@router.delete("/workflows/{workflow_id}", status_code=200)
async def delete_workflow(
    workflow_id: str,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a workflow."""
    wf = await _get_workflow(db, workflow_id, ws_ctx.workspace_id)
    await db.delete(wf)
    await db.commit()
    return {"detail": "Workflow deleted"}


# ---------- Run ----------

@router.post("/workflows/{workflow_id}/run", response_model=RunResponse)
async def run_workflow_endpoint(
    workflow_id: str,
    body: RunRequest,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    """Test run a workflow with a query."""
    wf = await _get_workflow(db, workflow_id, ws_ctx.workspace_id)

    # Validate before running
    try:
        validate_graph(wf.graph_json)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"Invalid workflow graph: {e}")

    body.query = mask_pii(body.query).text
    run = await create_run(
        db, workflow_id=wf.id, workspace_id=wf.workspace_id, user_id=ws_ctx.user.id,
        channel="admin_test", query=body.query,
    )
    await db.commit()
    try:
        result = await run_workflow(db, wf.graph_json, body.query, body.inputs, run=run,
                                    workspace_id=wf.workspace_id)
    except Exception as e:
        await complete_run(run, status="failed", error=str(e))
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Workflow execution failed: {e}")
    await complete_run(run, status="completed", answer=result.get("answer"))
    await db.commit()

    return RunResponse(
        answer=result["answer"],
        extracted_params=result.get("extracted_params", {}),
        retriever_resources=result["retriever_resources"],
        artifacts=result.get("artifacts", []),
    )


@router.post("/workflows/{workflow_id}/jobs", response_model=JobResponse, status_code=202)
async def run_workflow_in_background(
    workflow_id: str,
    body: RunRequest,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    """Queue a report run. Returns immediately; follow it on the workflow's "Lần chạy" tab.

    Reports call other systems and the LLM and can take minutes, so they never run inside the
    request. The `runs` row is created here so the audit log shows the attempt even if the
    worker is down.
    """
    wf = await _get_workflow(db, workflow_id, ws_ctx.workspace_id)
    try:
        validate_graph(wf.graph_json)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"Luồng xử lý chưa hợp lệ: {e}")

    run = await create_run(
        db, workflow_id=wf.id, workspace_id=wf.workspace_id, user_id=ws_ctx.user.id,
        channel="report", query=wf.name,
    )
    run.status = "queued"
    await db.commit()
    try:
        job_id = enqueue_workflow_run(run.id, wf.id, body.inputs or {})
    except Exception as e:
        await complete_run(run, status="failed", error=f"Không xếp được hàng đợi: {e}")
        await db.commit()
        raise HTTPException(status_code=503, detail="Hàng đợi công việc không sẵn sàng (Redis)")
    return JobResponse(run_id=str(run.id), job_id=job_id, status="queued")


@router.get("/workflows/{workflow_id}/runs", response_model=list[WorkflowRunRow])
async def list_workflow_runs(
    workflow_id: str,
    limit: int = Query(30, ge=1, le=200),
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    """Recent runs of this workflow (test, report and scheduled) with their output files."""
    wf = await _get_workflow(db, workflow_id, ws_ctx.workspace_id)
    runs = list((await db.execute(
        select(Run).where(Run.workflow_id == wf.id, Run.workspace_id == wf.workspace_id)
        .order_by(Run.started_at.desc()).limit(limit)
    )).scalars().all())
    by_run: dict[Any, list[ArtifactResponse]] = {}
    if runs:
        rows = (await db.execute(
            select(Artifact).where(Artifact.run_id.in_([r.id for r in runs]))
            .order_by(Artifact.created_at)
        )).scalars().all()
        for a in rows:
            by_run.setdefault(a.run_id, []).append(artifact_to_response(a))
    return [WorkflowRunRow(
        id=str(r.id), status=r.status, channel=r.channel,
        started_at=r.started_at.isoformat(), ended_at=r.ended_at.isoformat() if r.ended_at else None,
        latency_ms=r.latency_ms, error=r.error, answer_preview=r.answer_preview,
        artifacts=by_run.get(r.id, []),
    ) for r in runs]


@router.post("/workflows/{workflow_id}/template", response_model=TemplateUploadResponse)
async def upload_workflow_template(
    workflow_id: str,
    file: UploadFile = File(...),
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    """Upload a .docx template for a `render_document` node and report its placeholders."""
    wf = await _get_workflow(db, workflow_id, ws_ctx.workspace_id)
    name = file.filename or "mau.docx"
    if not name.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Chỉ nhận tệp .docx")
    data = await file.read(MAX_TEMPLATE_BYTES + 1)
    if len(data) > MAX_TEMPLATE_BYTES:
        raise HTTPException(status_code=400, detail="Mẫu tối đa 5MB")
    try:
        variables = sorted(docx_variables(data))
    except ReportError as e:
        raise HTTPException(status_code=400, detail=str(e))
    key = template_storage_key(wf.workspace_id, wf.id, name)
    upload_file(key, data, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    return TemplateUploadResponse(template_key=key, filename=name, variables=variables)


# ---------- Helpers ----------

async def _get_workflow(db: AsyncSession, workflow_id: str, workspace_id: uuid.UUID) -> Workflow:
    wf_uuid = uuid.UUID(workflow_id)
    result = await db.execute(
        select(Workflow).where(
            Workflow.id == wf_uuid,
            Workflow.workspace_id == workspace_id,
        )
    )
    wf = result.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf

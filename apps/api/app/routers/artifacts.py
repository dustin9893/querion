"""Files produced by report / form runs: list, read, download, delete.

Access is unit-scoped like everything else: an admin sees the artifacts of the unit in the
`X-Workspace-Id` header. Staff read theirs through `/v1/staff/reports` (same rows, audience
"staff"). The bytes never leave MinIO except through here, so the object store stays private.
"""

import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import WorkspaceContext, require_ws_role
from app.deps import get_db
from app.models.artifact import Artifact
from app.models.user_workspace import WsRole
from app.storage import delete_file, download_file

router = APIRouter(prefix="/v1", tags=["artifacts"])


class ArtifactResponse(BaseModel):
    id: str
    workspace_id: str
    run_id: str | None
    workflow_id: str | None
    schedule_id: str | None
    kind: str
    audience: str
    title: str | None
    filename: str
    content_type: str
    size: int
    created_at: str
    expires_at: str | None


class ArtifactDetail(ArtifactResponse):
    preview: str | None = None


def to_response(a: Artifact) -> ArtifactResponse:
    return ArtifactResponse(
        id=str(a.id), workspace_id=str(a.workspace_id),
        run_id=str(a.run_id) if a.run_id else None,
        workflow_id=str(a.workflow_id) if a.workflow_id else None,
        schedule_id=str(a.schedule_id) if a.schedule_id else None,
        kind=a.kind, audience=a.audience, title=a.title, filename=a.filename,
        content_type=a.content_type, size=a.size, created_at=a.created_at.isoformat(),
        expires_at=a.expires_at.isoformat() if a.expires_at else None,
    )


def download_response(artifact: Artifact) -> Response:
    """Stream the stored bytes back with a filename that survives Vietnamese characters."""
    try:
        data = download_file(artifact.storage_key)
    except Exception:
        raise HTTPException(status_code=410, detail="Tệp không còn trên hệ thống lưu trữ")
    ascii_name = artifact.filename.encode("ascii", "ignore").decode() or "report"
    disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(artifact.filename)}"
    return Response(content=data, media_type=artifact.content_type, headers={
        "Content-Disposition": disposition,
        "Content-Length": str(len(data)),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
    })


async def _get_artifact(db: AsyncSession, artifact_id: str, workspace_id) -> Artifact:
    try:
        aid = uuid.UUID(artifact_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp")
    artifact = (await db.execute(
        select(Artifact).where(Artifact.id == aid, Artifact.workspace_id == workspace_id)
    )).scalar_one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp trong đơn vị này")
    return artifact


@router.get("/artifacts", response_model=list[ArtifactResponse])
async def list_artifacts(
    workflow_id: str | None = None,
    run_id: str | None = None,
    schedule_id: str | None = None,
    kind: str | None = Query(None, pattern="^(report|form|export)$"),
    days: int = Query(90, ge=1, le=365),
    limit: int = Query(100, ge=1, le=500),
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    stmt = (select(Artifact)
            .where(Artifact.workspace_id == ws_ctx.workspace_id,
                   Artifact.created_at >= datetime.now(timezone.utc) - timedelta(days=days))
            .order_by(Artifact.created_at.desc()).limit(limit))
    if workflow_id:
        stmt = stmt.where(Artifact.workflow_id == uuid.UUID(workflow_id))
    if run_id:
        stmt = stmt.where(Artifact.run_id == uuid.UUID(run_id))
    if schedule_id:
        stmt = stmt.where(Artifact.schedule_id == uuid.UUID(schedule_id))
    if kind:
        stmt = stmt.where(Artifact.kind == kind)
    return [to_response(a) for a in (await db.execute(stmt)).scalars().all()]


@router.get("/artifacts/{artifact_id}", response_model=ArtifactDetail)
async def get_artifact(
    artifact_id: str,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    artifact = await _get_artifact(db, artifact_id, ws_ctx.workspace_id)
    return ArtifactDetail(**to_response(artifact).model_dump(), preview=artifact.preview)


@router.get("/artifacts/{artifact_id}/download")
async def download_artifact(
    artifact_id: str,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    return download_response(await _get_artifact(db, artifact_id, ws_ctx.workspace_id))


@router.delete("/artifacts/{artifact_id}", status_code=204)
async def delete_artifact(
    artifact_id: str,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    artifact = await _get_artifact(db, artifact_id, ws_ctx.workspace_id)
    try:
        delete_file(artifact.storage_key)
    except Exception:
        pass  # the row goes either way; a missing object must not block cleanup
    await db.delete(artifact)
    await db.commit()

"""Datasets CRUD router."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.auth.deps import require_ws_role, WorkspaceContext
from app.models.user_workspace import WsRole
from app.models.dataset import Dataset
from app.models.document import Document
from app.schemas.datasets import (
    DatasetCreate,
    DatasetUpdate,
    DatasetResponse,
    DatasetDetailResponse,
)
from app.routers.documents import _doc_to_response

router = APIRouter(prefix="/v1/datasets", tags=["datasets"])


# -- Helpers --
def _dataset_to_response(ds: Dataset, doc_count: int = 0) -> DatasetResponse:
    return DatasetResponse(
        id=str(ds.id),
        workspace_id=str(ds.workspace_id),
        name=ds.name,
        description=ds.description,
        visibility=ds.visibility,
        document_count=doc_count,
        created_at=ds.created_at.isoformat(),
        updated_at=ds.updated_at.isoformat(),
    )


# -- Endpoints --
@router.post("", response_model=DatasetResponse, status_code=status.HTTP_201_CREATED)
async def create_dataset(
    body: DatasetCreate,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new dataset in the current workspace."""
    dataset = Dataset(
        workspace_id=ws_ctx.workspace_id,
        name=body.name,
        description=body.description,
        visibility=body.visibility,
    )
    db.add(dataset)
    await db.commit()
    await db.refresh(dataset)
    return _dataset_to_response(dataset)


@router.get("", response_model=list[DatasetResponse])
async def list_datasets(
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    """List all datasets in the current workspace."""
    stmt = (
        select(Dataset, func.count(Document.id).label("doc_count"))
        .outerjoin(Document, Document.dataset_id == Dataset.id)
        .where(Dataset.workspace_id == ws_ctx.workspace_id)
        .group_by(Dataset.id)
        .order_by(Dataset.created_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()
    return [_dataset_to_response(ds, doc_count) for ds, doc_count in rows]


@router.get("/{dataset_id}", response_model=DatasetDetailResponse)
async def get_dataset(
    dataset_id: str,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    """Get dataset detail with list of documents."""
    ds_uuid = uuid.UUID(dataset_id)
    result = await db.execute(
        select(Dataset).where(
            Dataset.id == ds_uuid,
            Dataset.workspace_id == ws_ctx.workspace_id,
        )
    )
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

    docs_result = await db.execute(
        select(Document)
        .where(Document.dataset_id == ds_uuid)
        .order_by(Document.created_at.desc())
    )
    documents = docs_result.scalars().all()

    return DatasetDetailResponse(
        id=str(dataset.id),
        workspace_id=str(dataset.workspace_id),
        name=dataset.name,
        description=dataset.description,
        visibility=dataset.visibility,
        document_count=len(documents),
        created_at=dataset.created_at.isoformat(),
        updated_at=dataset.updated_at.isoformat(),
        documents=[_doc_to_response(doc) for doc in documents],
    )


@router.patch("/{dataset_id}", response_model=DatasetResponse)
async def update_dataset(
    dataset_id: str,
    body: DatasetUpdate,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    """Update name / description / visibility of a knowledge base."""
    ds_uuid = uuid.UUID(dataset_id)
    result = await db.execute(
        select(Dataset).where(
            Dataset.id == ds_uuid,
            Dataset.workspace_id == ws_ctx.workspace_id,
        )
    )
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

    if body.name is not None:
        dataset.name = body.name
    if body.description is not None:
        dataset.description = body.description
    if body.visibility is not None:
        if body.visibility not in ("internal", "public"):
            raise HTTPException(status_code=400, detail="visibility must be 'internal' or 'public'")
        dataset.visibility = body.visibility

    await db.commit()
    await db.refresh(dataset)
    count = await db.execute(select(func.count(Document.id)).where(Document.dataset_id == ds_uuid))
    return _dataset_to_response(dataset, count.scalar() or 0)


@router.delete("/{dataset_id}", status_code=status.HTTP_200_OK)
async def delete_dataset(
    dataset_id: str,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a dataset and all its documents."""
    ds_uuid = uuid.UUID(dataset_id)
    result = await db.execute(
        select(Dataset).where(
            Dataset.id == ds_uuid,
            Dataset.workspace_id == ws_ctx.workspace_id,
        )
    )
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

    # Delete MinIO files for all documents
    from app.storage import delete_file
    for doc in dataset.documents:
        try:
            delete_file(doc.storage_key)
        except Exception:
            pass  # best-effort cleanup

    await db.delete(dataset)
    await db.commit()
    return {"detail": "Dataset deleted"}

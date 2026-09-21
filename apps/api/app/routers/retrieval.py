"""Retrieval router — search for relevant chunks across datasets."""

from uuid import UUID
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.auth.deps import require_ws_role, WorkspaceContext
from app.models.user_workspace import WsRole
from app.services.retrieval import retrieve
from app.services.usage import UsageScope

router = APIRouter(prefix="/v1", tags=["retrieval"])


class RetrievalRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    dataset_ids: list[UUID]
    top_k: int = Field(5, ge=1, le=50)


class ChunkResult(BaseModel):
    chunk_id: str
    content: str
    content_preview: str
    chunk_index: int
    document_id: str
    dataset_id: str
    filename: str
    score: float


class RetrievalResponse(BaseModel):
    results: list[ChunkResult]


@router.post("/retrieval", response_model=RetrievalResponse)
async def retrieval_search(
    body: RetrievalRequest,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    """Search for relevant chunks across datasets using semantic similarity."""
    if not body.dataset_ids:
        raise HTTPException(status_code=400, detail="At least one dataset_id is required")

    results = await retrieve(
        db=db,
        query=body.query,
        dataset_ids=body.dataset_ids,
        top_k=body.top_k,
        usage=UsageScope(workspace_id=ws_ctx.workspace_id, channel="retrieval_test"),
    )

    return RetrievalResponse(results=[ChunkResult(**r) for r in results])

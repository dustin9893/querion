"""Documents router — upload, detail, delete, index, chunks."""

import uuid
from datetime import datetime, timezone

import redis
from rq import Queue
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.auth.deps import require_ws_role, WorkspaceContext
from app.models.user_workspace import WsRole
from app.models.dataset import Dataset
from app.models.document import Document, DocumentStatus
from app.models.chunk import Chunk
from app.schemas.datasets import DocumentResponse
from app.storage import upload_file, make_storage_key, delete_file
from app.config import settings

router = APIRouter(prefix="/v1", tags=["documents"])

ALLOWED_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".xlsx"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


def _doc_to_response(doc: Document) -> DocumentResponse:
    return DocumentResponse(
        id=str(doc.id),
        dataset_id=str(doc.dataset_id),
        filename=doc.filename,
        content_type=doc.content_type,
        size=doc.size,
        status=doc.status.value,
        chunk_count=doc.chunk_count,
        error_message=doc.error_message,
        doc_type=doc.doc_type,
        version=doc.version,
        effective_from=doc.effective_from,
        enabled=doc.enabled,
        disabled_at=doc.disabled_at.isoformat() if doc.disabled_at else None,
        created_at=doc.created_at.isoformat(),
        updated_at=doc.updated_at.isoformat(),
    )


def _upload_extension(filename: str | None) -> str:
    """Lower-cased extension of an uploadable knowledge-base file, or 400."""
    filename = filename or "unnamed"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    return ext


@router.post(
    "/datasets/{dataset_id}/documents/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    dataset_id: str,
    file: UploadFile = File(...),
    doc_type: str | None = Form(None),
    version: str | None = Form(None),
    effective_from: str | None = Form(None),
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document (văn bản) to a dataset, with optional banking metadata."""
    ds_uuid = uuid.UUID(dataset_id)

    # Verify dataset belongs to workspace
    result = await db.execute(
        select(Dataset).where(
            Dataset.id == ds_uuid,
            Dataset.workspace_id == ws_ctx.workspace_id,
        )
    )
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

    # Validate file extension
    filename = file.filename or "unnamed"
    _upload_extension(file.filename)

    # Read file content
    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Max size: {MAX_FILE_SIZE // (1024*1024)}MB",
        )

    content_type = file.content_type or "application/octet-stream"
    doc_id = uuid.uuid4()
    storage_key = make_storage_key(
        str(ws_ctx.workspace_id), str(ds_uuid), str(doc_id), filename
    )

    # Upload to MinIO
    upload_file(storage_key, data, content_type)

    # Create DB record
    document = Document(
        id=doc_id,
        dataset_id=ds_uuid,
        filename=filename,
        content_type=content_type,
        size=len(data),
        storage_key=storage_key,
        status=DocumentStatus.uploaded,
        doc_type=(doc_type or "").strip() or None,
        version=(version or "").strip() or None,
        effective_from=(effective_from or "").strip() or None,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    # Auto-trigger indexing
    try:
        document.status = DocumentStatus.indexing
        await db.commit()

        conn = redis.from_url(settings.REDIS_URL)
        q = Queue("querion-indexing", connection=conn)
        q.enqueue("worker.tasks.index_document.index_document", str(doc_id))
    except Exception:
        # If queue fails, keep as "uploaded" so user can retry manually
        document.status = DocumentStatus.uploaded
        await db.commit()

    return _doc_to_response(document)


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    """Get document detail."""
    doc_uuid = uuid.UUID(document_id)
    result = await db.execute(
        select(Document)
        .join(Dataset, Dataset.id == Document.dataset_id)
        .where(
            Document.id == doc_uuid,
            Dataset.workspace_id == ws_ctx.workspace_id,
        )
    )
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return _doc_to_response(document)


@router.delete("/documents/{document_id}", status_code=status.HTTP_200_OK)
async def delete_document(
    document_id: str,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a document and its MinIO file."""
    doc_uuid = uuid.UUID(document_id)
    result = await db.execute(
        select(Document)
        .join(Dataset, Dataset.id == Document.dataset_id)
        .where(
            Document.id == doc_uuid,
            Dataset.workspace_id == ws_ctx.workspace_id,
        )
    )
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Delete from MinIO
    try:
        delete_file(document.storage_key)
    except Exception:
        pass  # best-effort

    await db.delete(document)
    await db.commit()
    return {"detail": "Document deleted"}


# ---------- Index endpoint ----------

@router.post("/documents/{document_id}/index", status_code=status.HTTP_202_ACCEPTED)
async def index_document(
    document_id: str,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    """Trigger indexing for a document. Enqueues an RQ job."""
    doc_uuid = uuid.UUID(document_id)
    result = await db.execute(
        select(Document)
        .join(Dataset, Dataset.id == Document.dataset_id)
        .where(
            Document.id == doc_uuid,
            Dataset.workspace_id == ws_ctx.workspace_id,
        )
    )
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.status == DocumentStatus.indexing:
        raise HTTPException(status_code=400, detail="Document is already being indexed")

    # Update status to indexing
    document.status = DocumentStatus.indexing
    document.error_message = None
    await db.commit()

    # Enqueue RQ job
    conn = redis.from_url(settings.REDIS_URL)
    q = Queue("querion-indexing", connection=conn)
    job = q.enqueue("worker.tasks.index_document.index_document", str(doc_uuid))

    return {"status": "indexing", "job_id": job.id}


# ---------- Chunks endpoint ----------

@router.get("/documents/{document_id}/chunks")
async def get_document_chunks(
    document_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    """List chunks of a document with pagination."""
    doc_uuid = uuid.UUID(document_id)

    # Verify document access
    result = await db.execute(
        select(Document)
        .join(Dataset, Dataset.id == Document.dataset_id)
        .where(
            Document.id == doc_uuid,
            Dataset.workspace_id == ws_ctx.workspace_id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Document not found")

    # Count total
    count_result = await db.execute(
        select(func.count()).select_from(Chunk).where(Chunk.document_id == doc_uuid)
    )
    total = count_result.scalar() or 0

    # Fetch page
    offset = (page - 1) * page_size
    chunks_result = await db.execute(
        select(Chunk)
        .where(Chunk.document_id == doc_uuid)
        .order_by(Chunk.chunk_index)
        .offset(offset)
        .limit(page_size)
    )
    chunks = chunks_result.scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "chunks": [
            {
                "id": str(c.id),
                "chunk_index": c.chunk_index,
                "content": c.content,
                "content_preview": c.content[:200] if c.content else "",
            }
            for c in chunks
        ],
    }


# ---------- Update chunk endpoint ----------



class ChunkUpdateBody(BaseModel):
    content: str


@router.patch("/chunks/{chunk_id}", status_code=status.HTTP_200_OK)
async def update_chunk(
    chunk_id: str,
    body: ChunkUpdateBody,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    """Update chunk content and re-embed it."""
    from sqlalchemy import text as sql_text
    from app.models.ai_provider import AiProvider

    chunk_uuid = uuid.UUID(chunk_id)

    # Verify chunk access through workspace
    result = await db.execute(
        select(Chunk)
        .join(Document, Document.id == Chunk.document_id)
        .join(Dataset, Dataset.id == Document.dataset_id)
        .where(
            Chunk.id == chunk_uuid,
            Dataset.workspace_id == ws_ctx.workspace_id,
        )
    )
    chunk = result.scalar_one_or_none()
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

    # Update content
    chunk.content = body.content.strip()
    await db.commit()

    # Re-embed: find active embedding provider
    provider_result = await db.execute(
        select(AiProvider).where(
            AiProvider.is_active,
            AiProvider.purpose == "embedding",
        ).order_by(AiProvider.created_at).limit(1)
    )
    provider = provider_result.scalar_one_or_none()

    if provider:
        try:
            from app.services.retrieval import embed_query
            from app.services.usage import UsageScope

            model_name = provider.model_name
            # Same embedding path as retrieval (honours base_url, pads to 1536) and metered as indexing work
            doc = await db.get(Document, chunk.document_id)
            vec = await embed_query(chunk.content, provider, component="document_embedding", usage=UsageScope(
                workspace_id=ws_ctx.workspace_id, dataset_id=doc.dataset_id if doc else None,
                document_id=chunk.document_id, channel="admin_edit"))

            vec_str = "[" + ",".join(str(v) for v in vec) + "]"
            await db.execute(
                sql_text("""
                    INSERT INTO embeddings (chunk_id, embedding, model_name, created_at)
                    VALUES (:chunk_id, :embedding, :model_name, now())
                    ON CONFLICT (chunk_id) DO UPDATE
                    SET embedding = :embedding, model_name = :model_name, created_at = now()
                """),
                {"chunk_id": chunk_uuid, "embedding": vec_str, "model_name": model_name},
            )
            await db.commit()
        except Exception:
            # Don't fail the update if re-embedding fails
            pass

    return {
        "id": str(chunk.id),
        "chunk_index": chunk.chunk_index,
        "content": chunk.content,
        "re_embedded": provider is not None,
    }


# ---------- Document metadata ----------

class DocumentMetaUpdate(BaseModel):
    doc_type: str | None = None
    version: str | None = None
    effective_from: str | None = None
    enabled: bool | None = None


@router.patch("/documents/{document_id}", response_model=DocumentResponse)
async def update_document_meta(
    document_id: str,
    body: DocumentMetaUpdate,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    """Update banking metadata shown in citations, or enable / disable the document for AI retrieval."""
    result = await db.execute(
        select(Document)
        .join(Dataset, Dataset.id == Document.dataset_id)
        .where(Document.id == uuid.UUID(document_id), Dataset.workspace_id == ws_ctx.workspace_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    if body.doc_type is not None:
        doc.doc_type = body.doc_type.strip() or None
    if body.version is not None:
        doc.version = body.version.strip() or None
    if body.effective_from is not None:
        doc.effective_from = body.effective_from.strip() or None
    if body.enabled is not None and body.enabled != doc.enabled:
        doc.enabled = body.enabled
        doc.disabled_at = None if body.enabled else datetime.now(timezone.utc)
        doc.disabled_by = None if body.enabled else ws_ctx.user.id

    await db.commit()
    await db.refresh(doc)
    return _doc_to_response(doc)

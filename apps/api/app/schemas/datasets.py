"""Pydantic schemas for datasets (kho tri thức) and documents (văn bản)."""

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------
class DatasetCreate(BaseModel):
    name: str
    description: str | None = None
    visibility: str = Field(default="internal", pattern="^(internal|public)$")


class DatasetUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    visibility: str | None = None


class DatasetResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    description: str | None
    visibility: str = "internal"
    document_count: int = 0
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------
class DocumentResponse(BaseModel):
    id: str
    dataset_id: str
    filename: str
    content_type: str
    size: int
    status: str
    chunk_count: int
    error_message: str | None
    doc_type: str | None = None
    version: str | None = None
    effective_from: str | None = None
    enabled: bool = True
    disabled_at: str | None = None
    created_at: str
    updated_at: str


class DatasetDetailResponse(DatasetResponse):
    """Dataset with embedded documents list."""
    documents: list[DocumentResponse] = []

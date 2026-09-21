import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, String, DateTime, ForeignKey, Text, Integer, BigInteger, Enum, true
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db import Base


class DocumentStatus(str, enum.Enum):
    uploaded = "uploaded"
    indexing = "indexing"
    ready = "ready"
    failed = "failed"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status", create_constraint=True),
        default=DocumentStatus.uploaded,
        nullable=False,
    )
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Banking metadata surfaced in citations
    doc_type: Mapped[str | None] = mapped_column(String(64), nullable=True)  # quy_trinh | quy_dinh | huong_dan | san_pham | bieu_phi | mau_bieu | faq
    version: Mapped[str | None] = mapped_column(String(32), nullable=True)  # e.g. "v3.2"
    effective_from: Mapped[str | None] = mapped_column(String(32), nullable=True)  # e.g. "01/01/2026"
    # Disabled documents keep their index but retrieval skips them (services/retrieval.py)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disabled_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    dataset = relationship("Dataset", back_populates="documents")

    def __repr__(self) -> str:
        return f"<Document id={self.id} filename={self.filename!r} status={self.status.value}>"

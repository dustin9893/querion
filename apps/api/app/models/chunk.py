import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Text, Integer
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db import Base


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    # DB rows cascade on delete; tell the ORM so deleting a document never tries to NULL chunks.document_id
    document = relationship("Document", backref=backref("chunks", cascade="all, delete-orphan", passive_deletes=True))
    embedding = relationship("Embedding", back_populates="chunk", uselist=False, cascade="all, delete-orphan", passive_deletes=True)

    def __repr__(self) -> str:
        return f"<Chunk id={self.id} doc={self.document_id} idx={self.chunk_index}>"

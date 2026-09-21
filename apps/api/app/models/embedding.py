import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector

from app.db import Base


class Embedding(Base):
    __tablename__ = "embeddings"

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    embedding = mapped_column(Vector(1536), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    chunk = relationship("Chunk", back_populates="embedding")

    def __repr__(self) -> str:
        return f"<Embedding chunk_id={self.chunk_id} model={self.model_name}>"

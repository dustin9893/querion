import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Artifact(Base):
    """A file a workflow run produced: a report or a filled form (0024).

    No foreign keys: reports are records of what was sent out and outlive the workflow,
    schedule or unit that produced them. The bytes live in MinIO under ``storage_key`` and
    are only served through ``GET /v1/artifacts/{id}/download`` (unit-scoped).
    """

    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="report", server_default="report")
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "staff" reports also show up in the staff portal ("Báo cáo của tôi"); "admin" stays in the admin UI.
    audience: Mapped[str] = mapped_column(String(16), nullable=False, default="admin", server_default="admin")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by_employee_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Artifact {self.id} {self.filename}>"

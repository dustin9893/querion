import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class FormTemplate(Base):
    """A business form staff fill in and export as .docx (0026).

    Three kinds of field, declared in ``fields``: ``user`` (typed by the employee), ``tool``
    (filled from one registry tool keyed by a business code) and ``llm`` (free text the model
    drafts). Fields flagged ``pii`` are never sent to the model — that is why filling a form is a
    UI form and not a chat: chat masks CIF / account numbers and the form would come out wrong.
    """

    __tablename__ = "form_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    fields: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    template_storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    prefill_tool_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    prefill_arg: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prefill_mapping: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    share_scope: Mapped[str] = mapped_column(String(16), nullable=False, default="unit", server_default="unit")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )

    def __repr__(self) -> str:
        return f"<FormTemplate {self.id} {self.name}>"

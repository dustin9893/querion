"""Tools an assistant may call — scoped to a business unit, like datasets and assistants."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, Boolean, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db import Base

TOOL_KINDS = ("http", "builtin", "mcp", "report", "export")
# "report" runs a report workflow and returns its files; "export" builds an .xlsx from what the
# model saw in the conversation (no workflow, no lookup of its own)


class Tool(Base):
    """One callable exposed to the LLM (kind http/builtin), or one MCP server (kind mcp).

    An MCP row is a *server*: its tools are discovered at run time and exposed as
    ``<slug>__<tool name>``, so two servers can never collide.
    """

    __tablename__ = "tools"
    __table_args__ = (UniqueConstraint("workspace_id", "slug", name="uq_tools_workspace_slug"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False)      # function name sent to the LLM
    name: Mapped[str] = mapped_column(String(128), nullable=False)     # label for humans
    description: Mapped[str] = mapped_column(Text, nullable=False)     # what the LLM reads to decide
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="http", server_default="http")
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    params_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    # Fernet ciphertext (same key as provider keys). Never leaves the server.
    secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    allow_customer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    share_scope: Mapped[str] = mapped_column(String(16), nullable=False, default="unit", server_default="unit")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    timeout_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=10, server_default="10")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Tool {self.slug} kind={self.kind} ws={self.workspace_id}>"


class AppTool(Base):
    """Link table: which tools an assistant may call."""

    __tablename__ = "app_tools"

    app_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("apps.id", ondelete="CASCADE"), primary_key=True,
    )
    tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tools.id", ondelete="CASCADE"), primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False,
    )

    tool = relationship("Tool", lazy="joined")


class ToolApproval(Base):
    """A tool marked ``requires_approval`` paused the agent and a human decided.

    The agent state itself lives in the LangGraph checkpointer; this table is the
    compliance record of who decided what, and it is what the audit log reads.
    """

    __tablename__ = "tool_approvals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True,
    )
    tool_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tools.id", ondelete="SET NULL"), nullable=True,
    )
    tool_slug: Mapped[str] = mapped_column(String(128), nullable=False)
    args_preview: Mapped[str | None] = mapped_column(Text, nullable=True)   # PII-masked
    decision: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", server_default="pending")
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<ToolApproval {self.tool_slug} {self.decision}>"

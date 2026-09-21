import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db import Base


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    app_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("apps.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="SET NULL"),
        nullable=True,
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="running",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    latency_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
    )
    # --- audit context (0014) ---
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True,
    )
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    channel: Mapped[str] = mapped_column(
        String(16), nullable=False, default="staff", server_default="staff",
    )  # staff | customer | admin_test
    client_origin: Mapped[str | None] = mapped_column(String(255), nullable=True)  # embedding website (channel=embed)
    query_preview: Mapped[str | None] = mapped_column(String(500), nullable=True)
    answer_preview: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    steps = relationship("RunStep", back_populates="run", cascade="all, delete-orphan", order_by="RunStep.started_at")

    def __repr__(self) -> str:
        return f"<Run {self.id} status={self.status}>"


class RunStep(Base):
    __tablename__ = "run_steps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    node_id: Mapped[str] = mapped_column(
        String(128), nullable=False,
    )
    node_type: Mapped[str] = mapped_column(
        String(64), nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    input_json: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
    )
    output_json: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
    )

    # Relationships
    run = relationship("Run", back_populates="steps")

    def __repr__(self) -> str:
        return f"<RunStep {self.id} node={self.node_id} type={self.node_type}>"

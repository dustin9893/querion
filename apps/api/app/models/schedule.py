import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Schedule(Base):
    """A report workflow that runs on a cron schedule (0025).

    The database is the source of truth, not Redis: ``app/scheduler.py`` polls for rows whose
    ``next_run_at`` has passed, claims them with ``FOR UPDATE SKIP LOCKED`` (so two tickers never
    double-fire), queues the run and moves ``next_run_at`` to the next slot. A ticker that was
    down for a while therefore skips the missed slots instead of firing them all at once.
    """

    __tablename__ = "schedules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False,
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    cron: Mapped[str] = mapped_column(String(64), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Ho_Chi_Minh",
                                          server_default="Asia/Ho_Chi_Minh")
    inputs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    # Which staff see the report in "Báo cáo của tôi"; [] = every employee of the unit.
    deliver_positions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30, server_default="30")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_enqueued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Schedule {self.id} {self.name} {self.cron}>"

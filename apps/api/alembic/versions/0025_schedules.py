"""Run a report workflow on a cron schedule: schedules

Revision ID: 0025
Revises: 0024
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "schedules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workflow_id", UUID(as_uuid=True), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("cron", sa.String(64), nullable=False),                 # 5-field cron, in `timezone`
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Ho_Chi_Minh"),
        sa.Column("inputs", JSONB, nullable=False, server_default="{}"),  # the workflow's input fields
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deliver_positions", JSONB, nullable=False, server_default="[]"),  # [] = every employee of the unit
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("last_enqueued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_schedules_workspace", "schedules", ["workspace_id"])
    # The ticker claims due rows with FOR UPDATE SKIP LOCKED, so this is the hot path.
    op.create_index("ix_schedules_due", "schedules", ["enabled", "next_run_at"])


def downgrade() -> None:
    op.drop_table("schedules")

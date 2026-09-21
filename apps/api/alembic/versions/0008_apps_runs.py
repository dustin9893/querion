"""Create apps, runs, run_steps tables

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- apps ---
    op.create_table(
        "apps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("workflow_id", UUID(as_uuid=True), sa.ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True),
        sa.Column("model_config_json", JSONB, nullable=True),
        sa.Column("system_prompt", sa.Text, nullable=True),
        sa.Column("api_key", sa.String(128), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_apps_workspace_id", "apps", ["workspace_id"])
    op.create_index("ix_apps_api_key", "apps", ["api_key"], unique=True)

    # --- runs ---
    op.create_table(
        "runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("app_id", UUID(as_uuid=True), sa.ForeignKey("apps.id", ondelete="SET NULL"), nullable=True),
        sa.Column("workflow_id", UUID(as_uuid=True), sa.ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True),
        sa.Column("conversation_id", UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
    )
    op.create_index("ix_runs_app_id", "runs", ["app_id"])

    # --- run_steps ---
    op.create_table(
        "run_steps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", sa.String(128), nullable=False),
        sa.Column("node_type", sa.String(64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_json", JSONB, nullable=True),
        sa.Column("output_json", JSONB, nullable=True),
    )
    op.create_index("ix_run_steps_run_id", "run_steps", ["run_id"])


def downgrade() -> None:
    op.drop_table("run_steps")
    op.drop_table("runs")
    op.drop_table("apps")

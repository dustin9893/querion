"""Files produced by a workflow run (reports, filled forms): artifacts

Revision ID: 0024
Revises: 0023
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Like token_usage, this is history: no FK to runs/workflows so a deleted workflow does not
    # take its reports with it. The file itself lives in MinIO under storage_key.
    op.create_table(
        "artifacts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", UUID(as_uuid=True), nullable=True),
        sa.Column("workflow_id", UUID(as_uuid=True), nullable=True),
        sa.Column("schedule_id", UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False, server_default="report"),  # report | form
        sa.Column("title", sa.String(256), nullable=True),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("preview", sa.Text(), nullable=True),          # markdown/text preview shown in the UI
        sa.Column("audience", sa.String(16), nullable=False, server_default="admin"),  # admin | staff
        sa.Column("created_by_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_employee_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_artifacts_workspace_created", "artifacts", ["workspace_id", "created_at"])
    op.create_index("ix_artifacts_run_id", "artifacts", ["run_id"])
    op.create_index("ix_artifacts_workflow_id", "artifacts", ["workflow_id"])


def downgrade() -> None:
    op.drop_table("artifacts")

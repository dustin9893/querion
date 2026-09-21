"""Add type and dataset_id to workflows

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workflows", sa.Column("type", sa.String(32), nullable=False, server_default="chatflow"))
    op.add_column("workflows", sa.Column("dataset_id", UUID(as_uuid=True), sa.ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_workflows_dataset_id", "workflows", ["dataset_id"])


def downgrade() -> None:
    op.drop_index("ix_workflows_dataset_id", table_name="workflows")
    op.drop_column("workflows", "dataset_id")
    op.drop_column("workflows", "type")

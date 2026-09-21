"""Enable / disable a document for AI retrieval: documents.enabled, disabled_at, disabled_by

Revision ID: 0021
Revises: 0020
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A disabled document keeps its file and index but is skipped by retrieval on every channel.
    # Existing documents stay enabled.
    op.add_column("documents", sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("documents", sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column(
        "disabled_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    ))


def downgrade() -> None:
    op.drop_column("documents", "disabled_by")
    op.drop_column("documents", "disabled_at")
    op.drop_column("documents", "enabled")

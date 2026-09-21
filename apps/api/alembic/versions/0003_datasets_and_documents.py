"""Create datasets and documents tables.

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ENUM

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

# Declare the enum type outside of create_table to control lifecycle
document_status_enum = ENUM(
    "uploaded", "indexing", "ready", "failed",
    name="document_status",
    create_type=False,
)


def upgrade() -> None:
    # Create enum type first
    document_status_enum.create(op.get_bind(), checkfirst=True)

    # datasets table
    op.create_table(
        "datasets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_datasets_workspace_id", "datasets", ["workspace_id"])

    # documents table
    op.create_table(
        "documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "dataset_id",
            UUID(as_uuid=True),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("size", sa.BigInteger, nullable=False),
        sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column(
            "status",
            document_status_enum,
            nullable=False,
            server_default="uploaded",
        ),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_documents_dataset_id", "documents", ["dataset_id"])


def downgrade() -> None:
    op.drop_table("documents")
    op.drop_table("datasets")
    document_status_enum.drop(op.get_bind(), checkfirst=True)

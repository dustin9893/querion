"""add dataset_id to apps

Revision ID: 0010_app_dataset
Revises: 0009_students_publish
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("apps", sa.Column("dataset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True))


def downgrade() -> None:
    op.drop_column("apps", "dataset_id")

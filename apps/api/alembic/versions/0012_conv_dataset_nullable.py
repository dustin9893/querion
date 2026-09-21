"""make conversations.dataset_id nullable

Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("conversations", "dataset_id", nullable=True)


def downgrade() -> None:
    op.alter_column("conversations", "dataset_id", nullable=False)

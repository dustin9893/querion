"""add student_id and app_id to conversations

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=True))
    op.add_column("conversations", sa.Column("app_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("apps.id", ondelete="CASCADE"), nullable=True))
    op.create_index("ix_conversations_student_app", "conversations", ["student_id", "app_id"])


def downgrade() -> None:
    op.drop_index("ix_conversations_student_app")
    op.drop_column("conversations", "app_id")
    op.drop_column("conversations", "student_id")

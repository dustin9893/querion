"""conversations.user_id — admin test-console conversations belong to an admin user

Revision ID: 0018
Revises: 0017
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Staff conversations carry employee_id, customer ones neither; admin "Thử nghiệm hỏi đáp"
    # conversations carry user_id so the public/customer endpoints can exclude them.
    op.add_column("conversations", sa.Column(
        "user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True,
    ))
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_column("conversations", "user_id")

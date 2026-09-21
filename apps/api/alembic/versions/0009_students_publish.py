"""Create students table + add is_published/description to apps

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- students ---
    op.create_table(
        "students",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("student_id", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("must_change_password", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_students_email", "students", ["email"], unique=True)
    op.create_index("ix_students_student_id", "students", ["student_id"])

    # --- apps: add publishing columns ---
    op.add_column("apps", sa.Column("description", sa.Text, nullable=True, server_default=""))
    op.add_column("apps", sa.Column("is_published", sa.Boolean, nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("apps", "is_published")
    op.drop_column("apps", "description")
    op.drop_table("students")

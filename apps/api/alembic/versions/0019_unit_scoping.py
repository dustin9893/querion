"""Unit-scoped staff access: employees.workspace_id, apps.share_scope

Revision ID: 0019
Revises: 0018
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Which business unit (workspace) an employee belongs to. NULL = not assigned yet → the
    # employee only sees assistants shared bank-wide (restrictive default).
    op.add_column("employees", sa.Column(
        "workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True,
    ))
    op.create_index("ix_employees_workspace_id", "employees", ["workspace_id"])
    # "unit": only staff of the owning unit see the assistant; "bank": every employee.
    # Changing it requires the workspace owner role (routers/apps.py).
    op.add_column("apps", sa.Column("share_scope", sa.String(16), nullable=False, server_default="unit"))


def downgrade() -> None:
    op.drop_column("apps", "share_scope")
    op.drop_index("ix_employees_workspace_id", table_name="employees")
    op.drop_column("employees", "workspace_id")

"""add users and user_workspaces tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enums via raw SQL (avoids double-create from SQLAlchemy)
    op.execute("CREATE TYPE user_role AS ENUM ('super_admin', 'admin')")
    op.execute("CREATE TYPE ws_role AS ENUM ('owner', 'editor', 'viewer')")

    # Users table
    op.execute("""
        CREATE TABLE users (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            email VARCHAR(255) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            name VARCHAR(255) NOT NULL,
            role user_role NOT NULL DEFAULT 'admin',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE UNIQUE INDEX ix_users_email ON users (email)")

    # User-Workspaces join table
    op.execute("""
        CREATE TABLE user_workspaces (
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            ws_role ws_role NOT NULL DEFAULT 'viewer',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, workspace_id)
        )
    """)
    op.execute("CREATE INDEX ix_user_workspaces_user_id ON user_workspaces (user_id)")
    op.execute("CREATE INDEX ix_user_workspaces_workspace_id ON user_workspaces (workspace_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_workspaces")
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP TYPE IF EXISTS ws_role")
    op.execute("DROP TYPE IF EXISTS user_role")

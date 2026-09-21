"""Browser extension as a fourth surface for staff assistants: apps.extension_enabled / extension_hosts

Revision ID: 0027
Revises: 0026
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Opt-in: nothing shows up in the floating bubble until an admin turns it on per assistant.
    op.add_column("apps", sa.Column("extension_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    # Intranet host patterns ("bpm.msb.local", "*.ttqt.msb.local", "localhost:8092"): on a matching page
    # the bubble opens this assistant by default. Empty → only offered in the picker.
    op.add_column("apps", sa.Column("extension_hosts", JSONB, nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("apps", "extension_hosts")
    op.drop_column("apps", "extension_enabled")

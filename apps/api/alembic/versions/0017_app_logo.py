"""Assistant logo / avatar: apps.logo_key, logo_content_type, logo_updated_at

Revision ID: 0017
Revises: 0016
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The image itself lives in MinIO (workspaces/<ws>/apps/<app>/logo.<ext>) and is served by
    # GET /v1/public/assistants/{id}/logo; logo_updated_at feeds the ?v= cache-buster.
    op.add_column("apps", sa.Column("logo_key", sa.String(512), nullable=True))
    op.add_column("apps", sa.Column("logo_content_type", sa.String(64), nullable=True))
    op.add_column("apps", sa.Column("logo_updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("apps", "logo_updated_at")
    op.drop_column("apps", "logo_content_type")
    op.drop_column("apps", "logo_key")

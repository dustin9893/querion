"""Embeddable chat widget: apps.embed_enabled / allowed_origins / widget_config, runs.client_origin

Revision ID: 0016
Revises: 0015
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("apps", sa.Column("embed_enabled", sa.Boolean, nullable=False, server_default=sa.text("false")))
    op.add_column("apps", sa.Column("allowed_origins", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("apps", sa.Column("widget_config", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")))
    # Which website embedded the widget that produced this answer (audit / compliance)
    op.add_column("runs", sa.Column("client_origin", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "client_origin")
    op.drop_column("apps", "widget_config")
    op.drop_column("apps", "allowed_origins")
    op.drop_column("apps", "embed_enabled")

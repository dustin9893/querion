"""ai_providers.base_url — OpenAI-compatible gateways (OpenRouter, VNG Cloud MaaS, vLLM…)

Revision ID: 0015
Revises: 0014
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_providers", sa.Column("base_url", sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_providers", "base_url")

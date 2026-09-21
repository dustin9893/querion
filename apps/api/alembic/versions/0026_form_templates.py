"""Business forms staff fill and export as .docx: form_templates

Revision ID: 0026
Revises: 0025
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "form_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        # [{name, label, type, required, default, options, source: user|tool|llm, pii, description, llm_prompt}]
        sa.Column("fields", JSONB, nullable=False, server_default="[]"),
        sa.Column("template_storage_key", sa.Text(), nullable=True),
        sa.Column("template_filename", sa.String(512), nullable=True),
        # optional "điền sẵn": call one registry tool with a single business key, map its result into fields
        sa.Column("prefill_tool_id", UUID(as_uuid=True), nullable=True),
        sa.Column("prefill_arg", sa.String(64), nullable=True),
        sa.Column("prefill_mapping", JSONB, nullable=False, server_default="{}"),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("share_scope", sa.String(16), nullable=False, server_default="unit"),  # unit | bank
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_form_templates_workspace", "form_templates", ["workspace_id"])


def downgrade() -> None:
    op.drop_table("form_templates")

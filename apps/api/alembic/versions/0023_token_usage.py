"""Token usage metering: one row per model call

Revision ID: 0023
Revises: 0022
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No foreign keys on purpose: usage is accounting history and must survive deleting an
    # assistant, a knowledge base or a unit. Names are joined at read time.
    op.create_table(
        "token_usage",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=True),
        sa.Column("app_id", UUID(as_uuid=True), nullable=True),
        sa.Column("run_id", UUID(as_uuid=True), nullable=True),
        sa.Column("dataset_id", UUID(as_uuid=True), nullable=True),
        sa.Column("document_id", UUID(as_uuid=True), nullable=True),
        sa.Column("channel", sa.String(32), nullable=True),     # staff | customer | embed | admin_test | retrieval_test | indexing
        sa.Column("component", sa.String(32), nullable=False),  # answer | agent | workflow_llm | workflow_extract | title | query_embedding | document_embedding
        sa.Column("purpose", sa.String(16), nullable=False),    # llm | embedding
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("model", sa.String(256), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("calls", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("estimated", sa.Boolean(), nullable=False, server_default=sa.false()),  # provider sent no usage
    )
    op.create_index("ix_token_usage_created_at", "token_usage", ["created_at"])
    op.create_index("ix_token_usage_workspace_created", "token_usage", ["workspace_id", "created_at"])
    op.create_index("ix_token_usage_app_id", "token_usage", ["app_id"])
    op.create_index("ix_token_usage_run_id", "token_usage", ["run_id"])


def downgrade() -> None:
    op.drop_table("token_usage")

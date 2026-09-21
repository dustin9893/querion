"""Tools per workspace: tools, app_tools, tool_approvals; apps.agent_enabled

Revision ID: 0020
Revises: 0019
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A tool belongs to a business unit, exactly like datasets / assistants. `share_scope`
    # follows apps: "unit" (only this unit's assistants may bind it) or "bank" (any unit).
    op.create_table(
        "tools",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True),
        # the function name the LLM sees; unique per unit
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        # http = configurable REST call · builtin = pure local computation · mcp = an MCP server (many tools)
        sa.Column("kind", sa.String(16), nullable=False, server_default="http"),
        sa.Column("config", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        # JSON Schema for the arguments; ignored for kind=mcp (the server declares its own)
        sa.Column("params_schema", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        # Fernet ciphertext, injected server-side into the request; never returned by the API
        sa.Column("secret_encrypted", sa.Text, nullable=True),
        sa.Column("requires_approval", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("allow_customer", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("share_scope", sa.String(16), nullable=False, server_default="unit"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("timeout_sec", sa.Integer, nullable=False, server_default="10"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("workspace_id", "slug", name="uq_tools_workspace_slug"),
    )

    # Which tools an assistant may call.
    op.create_table(
        "app_tools",
        sa.Column("app_id", UUID(as_uuid=True), sa.ForeignKey("apps.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tool_id", UUID(as_uuid=True), sa.ForeignKey("tools.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Compliance trail for tools that need a human decision before they run.
    op.create_table(
        "tool_approvals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("conversation_id", UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("tool_id", UUID(as_uuid=True), sa.ForeignKey("tools.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tool_slug", sa.String(128), nullable=False),
        sa.Column("args_preview", sa.Text, nullable=True),      # PII-masked
        sa.Column("decision", sa.String(16), nullable=False, server_default="pending"),  # pending|approved|rejected
        sa.Column("employee_id", UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Assistant-level switch: when on (and tools are bound) answers go through the agent runtime.
    op.add_column("apps", sa.Column("agent_enabled", sa.Boolean, nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("apps", "agent_enabled")
    op.drop_table("tool_approvals")
    op.drop_table("app_tools")
    op.drop_table("tools")

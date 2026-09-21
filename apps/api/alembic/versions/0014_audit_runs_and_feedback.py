"""Audit log: runs carry who/where/what for every chat channel; message feedback (👍/👎)

Revision ID: 0014
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- runs: audit context ---
    op.add_column("runs", sa.Column("workspace_id", UUID(as_uuid=True),
                                    sa.ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True))
    op.add_column("runs", sa.Column("employee_id", UUID(as_uuid=True),
                                    sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True))
    op.add_column("runs", sa.Column("user_id", UUID(as_uuid=True),
                                    sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    op.add_column("runs", sa.Column("channel", sa.String(16), nullable=False, server_default="staff"))
    op.add_column("runs", sa.Column("query_preview", sa.String(500), nullable=True))
    op.add_column("runs", sa.Column("answer_preview", sa.String(500), nullable=True))
    op.add_column("runs", sa.Column("error", sa.Text, nullable=True))
    op.create_index("ix_runs_workspace_started", "runs", ["workspace_id", "started_at"])
    op.create_index("ix_runs_channel", "runs", ["channel"])

    # --- messages → run link (so feedback and citations join back to the audit row) ---
    op.add_column("messages", sa.Column("run_id", UUID(as_uuid=True),
                                        sa.ForeignKey("runs.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_messages_run_id", "messages", ["run_id"])

    # --- message_feedback ---
    op.create_table(
        "message_feedback",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("message_id", UUID(as_uuid=True), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("employee_id", UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("rating", sa.String(8), nullable=False),  # up | down
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("message_id", name="uq_message_feedback_message"),
    )
    op.create_index("ix_message_feedback_run_id", "message_feedback", ["run_id"])
    op.create_index("ix_message_feedback_rating", "message_feedback", ["rating"])


def downgrade() -> None:
    op.drop_index("ix_message_feedback_rating")
    op.drop_index("ix_message_feedback_run_id")
    op.drop_table("message_feedback")
    op.drop_index("ix_messages_run_id")
    op.drop_column("messages", "run_id")
    op.drop_index("ix_runs_channel")
    op.drop_index("ix_runs_workspace_started")
    for col in ("error", "answer_preview", "query_preview", "channel", "user_id", "employee_id", "workspace_id"):
        op.drop_column("runs", col)

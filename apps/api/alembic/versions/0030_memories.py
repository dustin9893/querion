"""Bộ nhớ cá nhân của cán bộ: bảng memories, công tắc theo trợ lý và theo đơn vị

Revision ID: 0030
Revises: 0029
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import UUID

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Bộ nhớ thuộc về **cán bộ**, không thuộc về trợ lý: người ta không muốn dạy lại "tôi thích
    # ngắn gọn" cho từng trợ lý. Không có khoá ngoại tới employees để việc xoá cán bộ là một hành
    # động có chủ đích trong mã (xem routers/employees.py) chứ không phải hiệu ứng phụ của cascade.
    op.create_table(
        "memories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("employee_id", UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=True),
        # trinh_bay | vai_tro | boi_canh | thuat_ngu — xem services/memory.py:CATEGORIES
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("text", sa.String(240), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("pinned", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("source_run_id", UUID(as_uuid=True), nullable=True),
        sa.Column("source_conversation_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True, index=True),
    )

    # Hội thoại dài: tóm tắt phần cũ thay vì cắt phăng ở tin thứ 10, để một hội thoại theo suốt
    # một hồ sơ không còn quên đầu quên đuôi.
    op.add_column("conversations", sa.Column("summary", sa.Text(), nullable=True))

    # Công tắc theo từng trợ lý. Một trợ lý tra cứu quy định thuần thì không cần nhớ gì về người hỏi.
    op.add_column("apps", sa.Column("memory_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))

    # Công tắc và thời hạn lưu theo đơn vị: quản trị đơn vị quyết định cho cả khối của mình.
    op.add_column("workspaces", sa.Column("memory_enabled", sa.Boolean(), nullable=False,
                                          server_default=sa.true()))
    op.add_column("workspaces", sa.Column("memory_retention_days", sa.Integer(), nullable=False,
                                          server_default="180"))


def downgrade() -> None:
    op.drop_column("workspaces", "memory_retention_days")
    op.drop_column("workspaces", "memory_enabled")
    op.drop_column("apps", "memory_enabled")
    op.drop_column("conversations", "summary")
    op.drop_table("memories")

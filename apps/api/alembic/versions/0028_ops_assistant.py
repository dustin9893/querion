"""Trợ lý Vận hành cho quản trị viên: apps.system_key, workspaces.is_system, bảng ops_config

Revision ID: 0028
Revises: 0027
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Trợ lý hệ thống là một dòng `apps` bình thường, chỉ khác ở chỗ được đánh dấu. Nhờ vậy nó
    # thừa hưởng nguyên đường trả lời: gắn kho tri thức, RAG có trích dẫn, che PII, bộ lọc đầu
    # ra, nhật ký truy vấn, đo token, công cụ, agent. Không có bản sao pipeline thứ hai.
    op.add_column("apps", sa.Column("system_key", sa.String(32), nullable=True))
    op.create_index("ix_apps_system_key", "apps", ["system_key"], unique=True)

    # Đơn vị "Hệ thống" chứa trợ lý vận hành và kho cẩm nang. Nó không phải đơn vị kinh doanh
    # nên phải nằm ngoài bộ chọn đơn vị, nếu không super admin đăng nhập có thể bị tự chọn vào
    # đây rồi thấy mọi trang đều trống.
    op.add_column("workspaces", sa.Column("is_system", sa.Boolean(), nullable=False,
                                          server_default=sa.false()))

    # Các nút bấm của riêng bong bóng vận hành. Tách khỏi `apps` để màn hình cấu hình của super
    # admin không phải mượn `widget_config` vốn dành cho bong bóng nhúng vào website đối tác.
    op.create_table(
        "ops_config",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        # Vai trò được nhìn thấy bong bóng. Mặc định cả hai: quản trị đơn vị cũng cần hỏi cách làm.
        sa.Column("audience_roles", JSONB, nullable=False, server_default='["admin", "super_admin"]'),
        sa.Column("tips", JSONB, nullable=False, server_default="[]"),
        sa.Column("tip_interval_sec", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("max_tips_per_session", sa.Integer(), nullable=False, server_default="3"),
        # Cho phép trợ lý soạn luồng xử lý. Tắt được vì nó là phần tốn token nhất.
        sa.Column("workflow_gen_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_by", UUID(as_uuid=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("ops_config")
    op.drop_column("workspaces", "is_system")
    op.drop_index("ix_apps_system_key", table_name="apps")
    op.drop_column("apps", "system_key")

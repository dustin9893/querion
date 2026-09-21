"""Tạm dừng ghi nhớ là lựa chọn của cán bộ, phải nằm ở máy chủ chứ không phải trình duyệt

Revision ID: 0031
Revises: 0030
"""
from alembic import op
import sqlalchemy as sa

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Bản đầu để công tắc này trong localStorage, nên nó không chặn gì cả: máy chủ vẫn ghi nhớ
    # như thường, và đổi máy là mất lựa chọn. Một công tắc quyền riêng tư không chặn được gì thì
    # tệ hơn là không có công tắc, vì người dùng tin là mình đã tắt.
    op.add_column("employees", sa.Column("memory_paused", sa.Boolean(), nullable=False,
                                         server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("employees", "memory_paused")

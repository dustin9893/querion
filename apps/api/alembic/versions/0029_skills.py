"""Kỹ năng của trợ lý: bảng skills + app_skills, theo chuẩn mở Agent Skills

Revision ID: 0029
Revises: 0028
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Một kỹ năng là bí kíp nghiệp vụ nạp *khi cần*, khác với system_prompt luôn nạp cho mọi câu
    # hỏi. Mô hình chỉ thấy `name` + `description` của mọi kỹ năng (~80 token mỗi dòng) và chỉ đọc
    # `body` của kỹ năng khớp câu hỏi.
    op.create_table(
        "skills",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True),
        # Ràng buộc của chuẩn agentskills.io, để xuất ra thư mục SKILL.md và nhập ngược lại được.
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        # Trường quyết định kích hoạt đúng hay nhầm. Chuẩn giới hạn 1024 ký tự.
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=False, server_default=""),
        sa.Column("version", sa.String(32), nullable=False, server_default="v1.0"),
        sa.Column("effective_from", sa.String(32), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),  # draft | published
        sa.Column("share_scope", sa.String(16), nullable=False, server_default="unit"),  # unit | bank
        sa.Column("allow_customer", sa.Boolean, nullable=False, server_default=sa.false()),
        # Kỹ năng đang mở thu hẹp ngữ cảnh: ưu tiên kho này, chỉ mời công cụ này.
        sa.Column("preferred_dataset_ids", JSONB, nullable=False, server_default="[]"),
        sa.Column("allowed_tool_ids", JSONB, nullable=False, server_default="[]"),
        # Kỹ năng phải dựa trên văn bản có thật; Compliance xem được nó dựa trên gì.
        sa.Column("reference_document_ids", JSONB, nullable=False, server_default="[]"),
        # Embedding của `description`: dùng để chọn trước cho trợ lý RAG thuần, và để cảnh báo hai
        # kỹ năng quá giống nhau ngay lúc soạn.
        sa.Column("description_embedding", Vector(1536), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column("approved_by", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("workspace_id", "slug", name="uq_skills_workspace_slug"),
    )

    op.create_table(
        "app_skills",
        sa.Column("app_id", UUID(as_uuid=True), sa.ForeignKey("apps.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("skill_id", UUID(as_uuid=True), sa.ForeignKey("skills.id", ondelete="CASCADE"),
                  primary_key=True, index=True),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Dưới ngưỡng này thì không kích hoạt: thà không dùng kỹ năng còn hơn dùng nhầm kỹ năng.
    op.add_column("apps", sa.Column("skill_match_threshold", sa.Float(), nullable=False,
                                    server_default="0.32"))


def downgrade() -> None:
    op.drop_column("apps", "skill_match_threshold")
    op.drop_table("app_skills")
    op.drop_table("skills")

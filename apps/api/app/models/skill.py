"""Kỹ năng: bí kíp nghiệp vụ trợ lý nạp **khi cần** (0029).

Ba cách dạy trợ lý trước đây đều có chỗ hở. `system_prompt` luôn nạp toàn bộ, nên mỗi bí kíp thêm
vào là mọi câu hỏi phải gánh, kể cả câu không liên quan. Công cụ chỉ trả dữ liệu, không dạy được
cách suy nghĩ. Luồng xử lý thì cứng, lệch khỏi kịch bản là hỏng.

Kỹ năng lấp chỗ hở đầu tiên, theo đúng cách chuẩn mở Agent Skills gọi là nạp dần: mô hình luôn thấy
`name` và `description` của mọi kỹ năng, chỉ khoảng 80 token mỗi dòng, và chỉ đọc `body` của kỹ năng
khớp câu hỏi. Trợ lý "biết" ba mươi kỹ năng với chi phí ít hơn một kỹ năng đang mở.

Quan hệ với văn bản: kỹ năng dạy **cách làm việc với văn bản**, không chứa nội dung quy định. Câu
"tỉ lệ cho vay tối đa 70%" phải nằm trong kho tri thức để trích dẫn được; kỹ năng chỉ nói "tra tỉ lệ
cho vay tối đa trong Quy định TSBĐ rồi so với hồ sơ". Nếu không, đổi quy định là kỹ năng sai âm thầm
mà không ai biết.
"""

import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

SKILL_STATUSES = ("draft", "published")

#: Giới hạn của chuẩn agentskills.io, giữ nguyên để xuất nhập SKILL.md không phải cắt gọt.
MAX_SLUG = 64
MAX_DESCRIPTION = 1024
#: Chuẩn khuyến nghị thân bài dưới 5000 token và 500 dòng.
MAX_BODY_LINES = 500


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (UniqueConstraint("workspace_id", "slug", name="uq_skills_workspace_slug"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    #: tên kỹ thuật theo chuẩn: chữ thường, số, gạch nối; là tên thư mục khi xuất SKILL.md
    slug: Mapped[str] = mapped_column(String(MAX_SLUG), nullable=False)
    #: nhãn tiếng Việt cho người đọc
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    #: "dùng khi nào" — thứ duy nhất mô hình đọc để quyết định kích hoạt
    description: Mapped[str] = mapped_column(Text, nullable=False)
    #: toàn văn bí kíp, markdown
    body: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1.0", server_default="v1.0")
    effective_from: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", server_default="draft")
    share_scope: Mapped[str] = mapped_column(String(16), nullable=False, default="unit", server_default="unit")
    allow_customer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    preferred_dataset_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    allowed_tool_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    reference_document_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    description_embedding: Mapped[list | None] = mapped_column(Vector(1536), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self) -> str:
        return f"<Skill {self.slug} status={self.status} ws={self.workspace_id}>"


class AppSkill(Base):
    """Kỹ năng nào được gắn vào trợ lý nào."""

    __tablename__ = "app_skills"

    app_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("apps.id", ondelete="CASCADE"), primary_key=True)
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


#: ngưỡng khớp mặc định cho việc chọn trước; thấp hơn thì không kích hoạt kỹ năng nào
DEFAULT_SKILL_THRESHOLD = 0.32

__all__ = ["Skill", "AppSkill", "SKILL_STATUSES", "MAX_SLUG", "MAX_DESCRIPTION",
           "MAX_BODY_LINES", "DEFAULT_SKILL_THRESHOLD"]

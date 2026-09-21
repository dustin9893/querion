"""Bộ nhớ cá nhân của cán bộ (0030).

Bộ nhớ ở đây **chỉ nhớ người hỏi làm việc thế nào**, không nhớ khách hàng, không nhớ quy định.
Lý do không phải kỹ thuật mà là nghiệp vụ, và có hai vế.

Vế thứ nhất, không có bộ nhớ tổ chức tự học. Nếu trợ lý học từ mọi cán bộ rồi dùng lại cho mọi
người thì một câu nói sai của một người sẽ thành "sự thật" cho người khác vào hôm sau, không trích
dẫn, không ai duyệt. Điều cả đơn vị muốn trợ lý nhớ đã có hai chỗ đúng để đặt: văn bản trong kho
tri thức, và kỹ năng. Cả hai đều có phiên bản và người duyệt.

Vế thứ hai, không nhớ dữ liệu khách hàng. Luật Bảo vệ dữ liệu cá nhân số 91/2025/QH15 hiệu lực từ
01/01/2026 cho chủ thể dữ liệu quyền được biết, đồng ý, truy cập, chỉnh sửa và yêu cầu xoá. Khách
hàng của kênh công khai không có tài khoản nên không thể thực thi các quyền đó, vì vậy kênh khách
hàng **không có bộ nhớ dài hạn** và mọi bản ghi chứa dữ liệu khách đều bị từ chối ngay khi ghi.

Bốn loại được phép nhớ nằm ở `services/memory.py:CATEGORIES`.
"""

import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    #: chủ sở hữu là cán bộ; quản trị viên dùng `user_id` cho Trợ lý Vận hành
    employee_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(String(240), nullable=False)
    embedding: Mapped[list | None] = mapped_column(Vector(1536), nullable=True)
    #: ghim thì luôn được nạp, không phụ thuộc độ gần nghĩa và không hết hạn
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    def __repr__(self) -> str:
        return f"<Memory {self.category} {self.text[:40]!r}>"


__all__ = ["Memory"]

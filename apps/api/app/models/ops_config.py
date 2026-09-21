"""Cấu hình bong bóng Trợ lý Vận hành — đúng một dòng trong bảng (0028).

Trợ lý vận hành bản thân nó là một dòng `apps` có `system_key = "ops_assistant"`, nên mọi thứ
thuộc về *trợ lý* (system prompt, model, kho tri thức, công cụ, logo, lời chào) nằm ở đó. Bảng
này chỉ giữ các nút bấm của riêng *bong bóng*: bật tắt, ai nhìn thấy, gợi ý hiện thế nào.

Tách ra thay vì nhét vào `apps.widget_config` vì trường đó đang phục vụ bong bóng nhúng lên
website đối tác. Trộn hai thứ vào nhau thì mỗi lần sửa một bên phải đọc lại luật của bên kia.

Super admin vẫn chỉ thấy một màn hình; `PUT /v1/ops/config` ghi cả hai bảng trong một lần.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

#: khoá nhận diện trợ lý hệ thống trong bảng `apps`
OPS_SYSTEM_KEY = "ops_assistant"

#: dòng cấu hình duy nhất, id cố định để `get_or_create` không bao giờ tạo ra dòng thứ hai
OPS_CONFIG_ID = uuid.UUID("00000000-0000-0000-0000-0000000000a1")


class OpsConfig(Base):
    __tablename__ = "ops_config"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=OPS_CONFIG_ID)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    #: vai trò quản trị được nhìn thấy bong bóng
    audience_roles: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=lambda: ["admin", "super_admin"],
        server_default='["admin", "super_admin"]')
    #: danh sách gợi ý hiện trong tooltip, xem `services/ops.py:validate_tips`
    tips: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    tip_interval_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=300, server_default="300")
    max_tips_per_session: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default="3")
    workflow_gen_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true")
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<OpsConfig enabled={self.enabled} tips={len(self.tips or [])}>"

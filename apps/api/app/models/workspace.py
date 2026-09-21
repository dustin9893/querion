import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db import Base


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Đơn vị "Hệ thống" (0028) chứa Trợ lý Vận hành và kho cẩm nang. Không phải đơn vị kinh
    # doanh, nên GET /v1/workspaces phải loại nó ra: web tự chọn đơn vị đầu tiên cho super
    # admin, chọn nhầm vào đây là mọi trang đều trống.
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                            server_default="false")
    # Bộ nhớ cá nhân của cán bộ (0030): quản trị đơn vị bật tắt và đặt thời hạn lưu cho cả khối.
    memory_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True,
                                                 server_default="true")
    memory_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=180,
                                                       server_default="180")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    # DB has ON DELETE CASCADE; tell the ORM so deleting a workspace removes memberships
    # instead of trying to NULL the composite primary key.
    members = relationship("UserWorkspace", back_populates="workspace", lazy="selectin",
                           cascade="all, delete-orphan", passive_deletes=True)

    def __repr__(self) -> str:
        return f"<Workspace id={self.id} name={self.name!r}>"


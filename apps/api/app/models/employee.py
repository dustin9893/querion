import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.db import Base


class Employee(Base):
    """Bank staff account (RM / CA / GDV / OPS) — separate identity tier from admin users."""

    __tablename__ = "employees"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    employee_code: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True,
    )  # Mã cán bộ, e.g. "MSB01234"
    branch: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
    )  # Chi nhánh / đơn vị kinh doanh
    department: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
    )  # Phòng / khối
    position: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
    )  # RM | CA | GDV | OPS | CCO ...
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True,
    )  # Đơn vị (workspace) the employee belongs to (0019); None → only bank-wide assistants are visible
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    # Cán bộ tự tắt việc học thêm mà vẫn giữ những gì đã nhớ (0031). Đặt ở máy chủ chứ không
    # phải trình duyệt: một công tắc quyền riêng tư chỉ nằm ở máy khách thì không chặn được gì,
    # và đổi máy là mất lựa chọn.
    memory_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                                server_default="false")
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Employee {self.id} code={self.employee_code!r} email={self.email!r}>"

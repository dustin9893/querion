import uuid
import secrets
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, DateTime, Float, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db import Base


def _generate_api_key() -> str:
    return f"app-{secrets.token_urlsafe(32)}"


class App(Base):
    __tablename__ = "apps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(256), nullable=False,
    )
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="SET NULL"),
        nullable=True,
    )
    model_config_json: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=dict,
    )
    system_prompt: Mapped[str | None] = mapped_column(
        Text, nullable=True, default="",
    )
    api_key: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, default=_generate_api_key,
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, default="",
    )
    is_published: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    audience: Mapped[str] = mapped_column(
        String(16), nullable=False, default="staff", server_default="staff",
    )  # "staff" (internal portal) | "customer" (public page via api_key)
    share_scope: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unit", server_default="unit",
    )  # "unit": only staff of this workspace see it | "bank": every employee (owner-only setting, 0019)
    # --- embeddable widget (0016) ---
    embed_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false",
    )
    allowed_origins: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]",
    )  # exact origins allowed to frame /embed/{id}; feeds CSP frame-ancestors
    widget_config: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}",
    )  # title, greeting, primary_color, position, launcher_text, suggestions, show_powered_by, theme
    # --- browser extension (0027): the floating bubble only offers assistants an admin opted in ---
    extension_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false",
    )
    extension_hosts: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]",
    )  # intranet host patterns where the bubble opens this assistant by default
    # --- tools (0020): when on and tools are bound, answers go through the agent runtime ---
    agent_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false",
    )
    # --- bộ nhớ (0030): trợ lý này có được dùng bộ nhớ cá nhân của cán bộ hay không.
    # Trợ lý tra cứu quy định thuần thì không cần nhớ gì về người hỏi.
    memory_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true")
    # --- kỹ năng (0029): dưới ngưỡng khớp này thì không kích hoạt kỹ năng nào.
    # Thà trả lời không có bí kíp còn hơn trả lời theo bí kíp sai.
    skill_match_threshold: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.32, server_default="0.32")
    # --- trợ lý hệ thống (0028): "ops_assistant" là Trợ lý Vận hành cho quản trị viên ---
    # Đánh dấu thay vì tạo bảng riêng, để nó đi đúng pipeline của mọi trợ lý khác.
    system_key: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True, index=True)
    # --- logo / avatar (0017): image in MinIO, served by GET /v1/public/assistants/{id}/logo ---
    logo_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    logo_content_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    logo_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
        return f"<App {self.id} name={self.name}>"


class AppDataset(Base):
    """Knowledge bases an assistant retrieves from (0022). Several per assistant, same unit only."""

    __tablename__ = "app_datasets"

    app_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("apps.id", ondelete="CASCADE"), primary_key=True,
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="CASCADE"), primary_key=True, index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False,
    )

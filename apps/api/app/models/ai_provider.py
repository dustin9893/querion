import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.db import Base


class AiProvider(Base):
    __tablename__ = "ai_providers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    provider_name: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # e.g. "openai", "anthropic"
    display_name: Mapped[str] = mapped_column(
        String(128), nullable=False
    )  # e.g. "OpenAI GPT"
    api_key_encrypted: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # Fernet encrypted
    model_name: Mapped[str] = mapped_column(
        String(128), nullable=False
    )  # e.g. "text-embedding-3-small"
    purpose: Mapped[str] = mapped_column(
        String(32), nullable=False, default="embedding"
    )  # "embedding" or "llm"
    base_url: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )  # OpenAI-compatible gateway, e.g. https://openrouter.ai/api/v1 or VNG Cloud MaaS
    is_active: Mapped[bool] = mapped_column(
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
        return f"<AiProvider {self.provider_name}/{self.model_name} active={self.is_active}>"

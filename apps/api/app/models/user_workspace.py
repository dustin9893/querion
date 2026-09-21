import uuid
from datetime import datetime, timezone
import enum

from sqlalchemy import ForeignKey, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db import Base


class WsRole(str, enum.Enum):
    owner = "owner"
    editor = "editor"
    viewer = "viewer"


# Role hierarchy for permission checks
WS_ROLE_HIERARCHY = {
    WsRole.viewer: 0,
    WsRole.editor: 1,
    WsRole.owner: 2,
}


def has_min_role(user_role: WsRole, min_role: WsRole) -> bool:
    """Check if user_role meets the minimum required role."""
    return WS_ROLE_HIERARCHY[user_role] >= WS_ROLE_HIERARCHY[min_role]


class UserWorkspace(Base):
    __tablename__ = "user_workspaces"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    ws_role: Mapped[WsRole] = mapped_column(
        SAEnum(WsRole, name="ws_role", create_constraint=True),
        nullable=False,
        default=WsRole.viewer,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    user = relationship("User", back_populates="workspace_memberships", lazy="selectin")
    workspace = relationship("Workspace", back_populates="members", lazy="selectin")

    def __repr__(self) -> str:
        return f"<UserWorkspace user={self.user_id} ws={self.workspace_id} role={self.ws_role}>"

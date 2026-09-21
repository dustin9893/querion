"""Auth dependencies for FastAPI — JWT extraction, role checks, workspace context."""

import uuid

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.auth.security import decode_token
from app.models.user import User, UserRole
from app.models.user_workspace import UserWorkspace, WsRole, has_min_role

bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Get current user from JWT
# ---------------------------------------------------------------------------
async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate JWT, return the User object."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_token(credentials.credentials)
    if payload is None or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return user


# ---------------------------------------------------------------------------
# Role checks
# ---------------------------------------------------------------------------
async def require_super_admin(
    user: User = Depends(get_current_user),
) -> User:
    """Only super_admin can access."""
    if user.role != UserRole.super_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin access required")
    return user


# ---------------------------------------------------------------------------
# Workspace context
# ---------------------------------------------------------------------------
class WorkspaceContext:
    """Holds the current workspace membership info for the request."""
    def __init__(self, workspace_id: uuid.UUID, user: User, membership: UserWorkspace | None):
        self.workspace_id = workspace_id
        self.user = user
        self.membership = membership
        # super_admin has implicit full access
        self.ws_role: WsRole | None = membership.ws_role if membership else None
        self.is_super_admin = user.role == UserRole.super_admin

    def has_role(self, min_role: WsRole) -> bool:
        if self.is_super_admin:
            return True
        if self.ws_role is None:
            return False
        return has_min_role(self.ws_role, min_role)


async def get_workspace_context(
    x_workspace_id: str | None = Header(None, alias="X-Workspace-Id"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceContext:
    """Extract workspace from header, validate membership."""
    if not x_workspace_id:
        # A missing header used to surface as a raw 422 "Field required" — say what to do instead.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chưa chọn đơn vị làm việc (thiếu header X-Workspace-Id). Hãy chọn đơn vị ở thanh bên.",
        )
    try:
        ws_id = uuid.UUID(x_workspace_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid workspace ID")

    # Super admin bypasses membership check
    if user.role == UserRole.super_admin:
        return WorkspaceContext(workspace_id=ws_id, user=user, membership=None)

    # Check membership
    result = await db.execute(
        select(UserWorkspace).where(
            UserWorkspace.user_id == user.id,
            UserWorkspace.workspace_id == ws_id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this workspace")

    return WorkspaceContext(workspace_id=ws_id, user=user, membership=membership)


def require_ws_role(min_role: WsRole):
    """Factory for workspace role dependency — checks ws_role >= min_role."""
    async def _check(ws_ctx: WorkspaceContext = Depends(get_workspace_context)) -> WorkspaceContext:
        if not ws_ctx.has_role(min_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires workspace role: {min_role.value} or higher",
            )
        return ws_ctx
    return _check

"""Auth router — login, refresh, me."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.auth.security import verify_password, create_access_token, create_refresh_token, decode_token
from app.auth.deps import get_current_user
from app.models.user import User
from app.models.user_workspace import UserWorkspace

router = APIRouter(prefix="/v1/auth", tags=["auth"])


# -- Schemas --
class LoginRequest(BaseModel):
    email: str
    password: str


class WorkspaceMembership(BaseModel):
    workspace_id: str
    workspace_name: str
    ws_role: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    workspaces: list[WorkspaceMembership] = []


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: UserResponse


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str


# -- Endpoints --
@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate user and return tokens + user info."""
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")

    # Get workspace memberships
    ws_result = await db.execute(
        select(UserWorkspace).where(UserWorkspace.user_id == user.id)
    )
    memberships = ws_result.scalars().all()

    workspaces = [
        WorkspaceMembership(
            workspace_id=str(m.workspace_id),
            workspace_name=m.workspace.name if m.workspace else "Unknown",
            ws_role=m.ws_role.value,
        )
        for m in memberships
    ]

    access_token = create_access_token(str(user.id), user.role.value)
    refresh_token = create_refresh_token(str(user.id))

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            name=user.name,
            role=user.role.value,
            workspaces=workspaces,
        ),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Refresh the access token using a refresh token."""
    payload = decode_token(body.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    new_access = create_access_token(str(user.id), user.role.value)
    return TokenResponse(access_token=new_access)


@router.get("/me", response_model=UserResponse)
async def get_me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return current authenticated user info."""
    ws_result = await db.execute(
        select(UserWorkspace).where(UserWorkspace.user_id == user.id)
    )
    memberships = ws_result.scalars().all()

    workspaces = [
        WorkspaceMembership(
            workspace_id=str(m.workspace_id),
            workspace_name=m.workspace.name if m.workspace else "Unknown",
            ws_role=m.ws_role.value,
        )
        for m in memberships
    ]

    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name,
        role=user.role.value,
        workspaces=workspaces,
    )

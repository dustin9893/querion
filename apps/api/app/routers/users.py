"""Users CRUD router — super_admin only."""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.auth.deps import require_super_admin
from app.auth.security import hash_password
from app.models.user import User, UserRole
from app.models.user_workspace import UserWorkspace
from app.models.workspace import Workspace

router = APIRouter(prefix="/v1/users", tags=["users"])


# -- Schemas --
class CreateUserRequest(BaseModel):
    email: str
    password: str
    name: str


class UpdateUserRequest(BaseModel):
    name: str | None = None
    is_active: bool | None = None


class UserItem(BaseModel):
    id: str
    email: str
    name: str
    role: str
    is_active: bool
    workspaces: list[dict] = []


# -- Endpoints --
@router.post("", response_model=UserItem, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create an admin user (super_admin only)."""
    # Check duplicate email
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        name=body.name,
        role=UserRole.admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return UserItem(
        id=str(user.id), email=user.email, name=user.name,
        role=user.role.value, is_active=user.is_active,
    )


@router.get("", response_model=list[UserItem])
async def list_users(
    workspace_id: str | None = Query(None),
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all users, optionally filtered by workspace membership."""
    if workspace_id:
        ws_uuid = uuid.UUID(workspace_id)
        result = await db.execute(
            select(User)
            .join(UserWorkspace, User.id == UserWorkspace.user_id)
            .where(UserWorkspace.workspace_id == ws_uuid)
        )
    else:
        result = await db.execute(select(User).order_by(User.created_at))

    users = result.scalars().all()
    ws_names = {w.id: w.name for w in (await db.execute(select(Workspace))).scalars().all()}
    items = []
    for u in users:
        ws_list = [
            {"workspace_id": str(m.workspace_id), "ws_role": m.ws_role.value,
             "workspace_name": ws_names.get(m.workspace_id)}
            for m in u.workspace_memberships
        ]
        items.append(UserItem(
            id=str(u.id), email=u.email, name=u.name,
            role=u.role.value, is_active=u.is_active, workspaces=ws_list,
        ))
    return items


@router.patch("/{user_id}", response_model=UserItem)
async def update_user(
    user_id: str,
    body: UpdateUserRequest,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update user name or active status (super_admin only)."""
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if body.name is not None:
        user.name = body.name
    if body.is_active is not None:
        user.is_active = body.is_active

    await db.commit()
    await db.refresh(user)

    return UserItem(
        id=str(user.id), email=user.email, name=user.name,
        role=user.role.value, is_active=user.is_active,
    )


@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
async def deactivate_user(
    user_id: str,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete (deactivate) a user."""
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_active = False
    await db.commit()
    return {"detail": "User deactivated"}

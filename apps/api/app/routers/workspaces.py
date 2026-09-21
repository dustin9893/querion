"""Workspaces CRUD router."""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.auth.deps import get_current_user, require_super_admin
from app.models.user import User, UserRole
from app.models.workspace import Workspace
from app.models.user_workspace import UserWorkspace, WsRole

router = APIRouter(prefix="/v1/workspaces", tags=["workspaces"])


# -- Schemas --
class CreateWorkspaceRequest(BaseModel):
    name: str
    owner_user_id: str


class UpdateWorkspaceRequest(BaseModel):
    name: str | None = None
    # Bộ nhớ cá nhân của cán bộ trong đơn vị này (0030). Không có đường sửa thì cột chỉ là trang
    # trí: quản trị đơn vị không tắt được cho khối mình dù tài liệu nói là tắt được.
    memory_enabled: bool | None = None
    memory_retention_days: int | None = None


class WorkspaceItem(BaseModel):
    id: str
    name: str
    created_at: str
    member_count: int = 0
    memory_enabled: bool = True
    memory_retention_days: int = 180


# -- Endpoints --
@router.post("", response_model=WorkspaceItem, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: CreateWorkspaceRequest,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a workspace and assign owner (super_admin only)."""
    # Validate owner exists and is admin
    owner_result = await db.execute(select(User).where(User.id == uuid.UUID(body.owner_user_id)))
    owner = owner_result.scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner user not found")
    if owner.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Owner must be an admin user")

    workspace = Workspace(name=body.name)
    db.add(workspace)
    await db.flush()

    # Assign owner
    membership = UserWorkspace(
        user_id=owner.id,
        workspace_id=workspace.id,
        ws_role=WsRole.owner,
    )
    db.add(membership)
    await db.commit()
    await db.refresh(workspace)

    return WorkspaceItem(
        id=str(workspace.id), name=workspace.name,
        created_at=workspace.created_at.isoformat(), member_count=1,
    )


@router.get("", response_model=list[WorkspaceItem])
async def list_workspaces(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List business units. Super admin sees all; admin sees only their memberships.

    The "Hệ thống" unit (0028) holds the Trợ lý Vận hành and its manual, and is filtered out
    here on purpose: the web picks the first unit in this list as the super admin's active one,
    so leaving it in would land them in a unit with no datasets and make every page look empty.
    """
    if user.role == UserRole.super_admin:
        result = await db.execute(
            select(Workspace).where(Workspace.is_system.is_(False)).order_by(Workspace.created_at))
        workspaces = result.scalars().all()
    else:
        result = await db.execute(
            select(Workspace)
            .join(UserWorkspace, Workspace.id == UserWorkspace.workspace_id)
            .where(UserWorkspace.user_id == user.id, Workspace.is_system.is_(False))
            .order_by(Workspace.created_at)
        )
        workspaces = result.scalars().all()

    return [
        WorkspaceItem(
            id=str(ws.id), name=ws.name,
            memory_enabled=bool(getattr(ws, "memory_enabled", True)),
            memory_retention_days=int(getattr(ws, "memory_retention_days", 180) or 180),
            created_at=ws.created_at.isoformat(),
            member_count=len(ws.members) if ws.members else 0,
        )
        for ws in workspaces
    ]


@router.patch("/{workspace_id}", response_model=WorkspaceItem)
async def update_workspace(
    workspace_id: str,
    body: UpdateWorkspaceRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update workspace (super_admin or owner)."""
    ws_uuid = uuid.UUID(workspace_id)
    result = await db.execute(select(Workspace).where(Workspace.id == ws_uuid))
    workspace = result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    # Permission check: super_admin or owner
    if user.role != UserRole.super_admin:
        mem_result = await db.execute(
            select(UserWorkspace).where(
                UserWorkspace.user_id == user.id,
                UserWorkspace.workspace_id == ws_uuid,
                UserWorkspace.ws_role == WsRole.owner,
            )
        )
        if mem_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owner can update workspace")

    if body.name is not None:
        workspace.name = body.name
    if body.memory_enabled is not None:
        workspace.memory_enabled = bool(body.memory_enabled)
    if body.memory_retention_days is not None:
        if not 7 <= body.memory_retention_days <= 730:
            raise HTTPException(status_code=400,
                                detail="Thời hạn lưu bộ nhớ phải từ 7 đến 730 ngày")
        workspace.memory_retention_days = body.memory_retention_days

    await db.commit()
    await db.refresh(workspace)

    return WorkspaceItem(
        id=str(workspace.id), name=workspace.name,
        memory_enabled=bool(getattr(workspace, "memory_enabled", True)),
        memory_retention_days=int(getattr(workspace, "memory_retention_days", 180) or 180),
        created_at=workspace.created_at.isoformat(),
        member_count=len(workspace.members) if workspace.members else 0,
    )


@router.delete("/{workspace_id}", status_code=status.HTTP_200_OK)
async def delete_workspace(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete workspace (super_admin or owner)."""
    ws_uuid = uuid.UUID(workspace_id)
    result = await db.execute(select(Workspace).where(Workspace.id == ws_uuid))
    workspace = result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    if user.role != UserRole.super_admin:
        mem_result = await db.execute(
            select(UserWorkspace).where(
                UserWorkspace.user_id == user.id,
                UserWorkspace.workspace_id == ws_uuid,
                UserWorkspace.ws_role == WsRole.owner,
            )
        )
        if mem_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owner can delete workspace")

    await db.delete(workspace)
    await db.commit()
    return {"detail": "Workspace deleted"}

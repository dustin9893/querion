"""Workspace Members router — invite, list, change role, remove."""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.auth.deps import WorkspaceContext, get_workspace_context
from app.models.user import User, UserRole
from app.models.user_workspace import UserWorkspace, WsRole

router = APIRouter(prefix="/v1/workspaces/{workspace_id}/members", tags=["members"])


# -- Schemas --
class AddMemberRequest(BaseModel):
    user_id: str
    ws_role: str  # "owner" | "editor" | "viewer"


class UpdateMemberRequest(BaseModel):
    ws_role: str  # "owner" | "editor" | "viewer"


class MemberItem(BaseModel):
    user_id: str
    email: str
    name: str
    ws_role: str
    created_at: str


# -- Helpers --
def _require_manage_permission(ws_ctx: WorkspaceContext):
    """Check that user is super_admin or owner."""
    if not ws_ctx.is_super_admin:
        if ws_ctx.ws_role != WsRole.owner:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only workspace owner or super_admin can manage members",
            )


async def _count_owners(db: AsyncSession, workspace_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count()).select_from(UserWorkspace).where(
            UserWorkspace.workspace_id == workspace_id,
            UserWorkspace.ws_role == WsRole.owner,
        )
    )
    return result.scalar() or 0


# -- Endpoints --
@router.post("", response_model=MemberItem, status_code=status.HTTP_201_CREATED)
async def add_member(
    workspace_id: str,
    body: AddMemberRequest,
    ws_ctx: WorkspaceContext = Depends(get_workspace_context),
    db: AsyncSession = Depends(get_db),
):
    """Invite an admin user to the workspace (super_admin or owner)."""
    _require_manage_permission(ws_ctx)

    ws_uuid = uuid.UUID(workspace_id)
    user_uuid = uuid.UUID(body.user_id)

    # Validate user exists and is admin
    user_result = await db.execute(select(User).where(User.id == user_uuid))
    target_user = user_result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if target_user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Can only add admin users to workspaces")

    # Check not already a member
    existing = await db.execute(
        select(UserWorkspace).where(
            UserWorkspace.user_id == user_uuid,
            UserWorkspace.workspace_id == ws_uuid,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already a member")

    try:
        role = WsRole(body.ws_role)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ws_role")

    membership = UserWorkspace(
        user_id=user_uuid,
        workspace_id=ws_uuid,
        ws_role=role,
    )
    db.add(membership)
    await db.commit()
    await db.refresh(membership)

    return MemberItem(
        user_id=str(target_user.id), email=target_user.email, name=target_user.name,
        ws_role=membership.ws_role.value, created_at=membership.created_at.isoformat(),
    )


@router.get("", response_model=list[MemberItem])
async def list_members(
    workspace_id: str,
    ws_ctx: WorkspaceContext = Depends(get_workspace_context),
    db: AsyncSession = Depends(get_db),
):
    """List workspace members (any member can view)."""
    ws_uuid = uuid.UUID(workspace_id)
    result = await db.execute(
        select(UserWorkspace).where(UserWorkspace.workspace_id == ws_uuid)
    )
    memberships = result.scalars().all()

    items = []
    for m in memberships:
        user = m.user
        items.append(MemberItem(
            user_id=str(user.id), email=user.email, name=user.name,
            ws_role=m.ws_role.value, created_at=m.created_at.isoformat(),
        ))
    return items


@router.patch("/{user_id}", response_model=MemberItem)
async def update_member_role(
    workspace_id: str,
    user_id: str,
    body: UpdateMemberRequest,
    ws_ctx: WorkspaceContext = Depends(get_workspace_context),
    db: AsyncSession = Depends(get_db),
):
    """Change a member's ws_role (super_admin or owner)."""
    _require_manage_permission(ws_ctx)

    ws_uuid = uuid.UUID(workspace_id)
    user_uuid = uuid.UUID(user_id)

    result = await db.execute(
        select(UserWorkspace).where(
            UserWorkspace.user_id == user_uuid,
            UserWorkspace.workspace_id == ws_uuid,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    try:
        new_role = WsRole(body.ws_role)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ws_role")

    # Prevent demoting last owner
    if membership.ws_role == WsRole.owner and new_role != WsRole.owner:
        owner_count = await _count_owners(db, ws_uuid)
        if owner_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the last owner of the workspace",
            )

    membership.ws_role = new_role
    await db.commit()
    await db.refresh(membership)

    user = membership.user
    return MemberItem(
        user_id=str(user.id), email=user.email, name=user.name,
        ws_role=membership.ws_role.value, created_at=membership.created_at.isoformat(),
    )


@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
async def remove_member(
    workspace_id: str,
    user_id: str,
    ws_ctx: WorkspaceContext = Depends(get_workspace_context),
    db: AsyncSession = Depends(get_db),
):
    """Remove a member from the workspace (super_admin or owner)."""
    _require_manage_permission(ws_ctx)

    ws_uuid = uuid.UUID(workspace_id)
    user_uuid = uuid.UUID(user_id)

    result = await db.execute(
        select(UserWorkspace).where(
            UserWorkspace.user_id == user_uuid,
            UserWorkspace.workspace_id == ws_uuid,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    # Prevent removing last owner
    if membership.ws_role == WsRole.owner:
        owner_count = await _count_owners(db, ws_uuid)
        if owner_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the last owner of the workspace",
            )

    await db.delete(membership)
    await db.commit()
    return {"detail": "Member removed"}

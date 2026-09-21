"""Employees CRUD — super admin manages every unit's staff; a unit admin (workspace owner)
manages only the staff of units they own.

Scoping: the unit comes from ``?workspace_id=`` or the ``X-Workspace-Id`` header. For a
workspace owner it must be one of their owned units (403 otherwise) and employees of other
units are invisible (404). Super admin may omit it (all employees) or use it as a filter.
"""

import csv
import io
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.auth.deps import get_current_user
from app.auth.security import hash_password
from app.models.user import User, UserRole
from app.models.user_workspace import UserWorkspace, WsRole
from app.models.employee import Employee
from app.models.workspace import Workspace

router = APIRouter(prefix="/v1/employees", tags=["employees"])
logger = logging.getLogger(__name__)

DEFAULT_PASSWORD = "msb@123"

POSITIONS = ["RM", "CA", "GDV", "OPS", "CCO", "KSV", "Other"]


# -- Auth / scope dependency --
class StaffScope:
    """Which units the caller may manage staff for. ``owned is None`` → super admin (all)."""

    def __init__(self, user: User, owned: set[uuid.UUID] | None, requested: uuid.UUID | None):
        self.user = user
        self.owned = owned
        self.requested = requested  # unit named by ?workspace_id= or X-Workspace-Id (may be None)

    @property
    def is_super(self) -> bool:
        return self.owned is None

    def can_manage(self, ws_id: uuid.UUID | None) -> bool:
        if self.is_super:
            return True
        return ws_id is not None and ws_id in self.owned

    def unit_or_403(self, ws_id: uuid.UUID | None) -> uuid.UUID | None:
        """Unit a new / moved employee may be put in. Super admin: anything (incl. none)."""
        if self.is_super:
            return ws_id
        if ws_id is None:
            raise HTTPException(status_code=400, detail="Chọn đơn vị cho cán bộ")
        if ws_id not in self.owned:
            raise HTTPException(status_code=403, detail="Chỉ được quản lý cán bộ của đơn vị mình là chủ (owner)")
        return ws_id

    def default_unit(self) -> uuid.UUID | None:
        """Unit used when none is given: the requested one, else the only owned one."""
        if self.requested is not None:
            return self.requested
        if self.owned and len(self.owned) == 1:
            return next(iter(self.owned))
        return None


def _parse_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workspace ID")


async def staff_scope(
    request: Request,
    workspace_id: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StaffScope:
    requested = _parse_uuid(workspace_id) or _parse_uuid(request.headers.get("x-workspace-id"))
    if user.role == UserRole.super_admin:
        return StaffScope(user, None, requested)
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    rows = await db.execute(select(UserWorkspace.workspace_id).where(
        UserWorkspace.user_id == user.id, UserWorkspace.ws_role == WsRole.owner))
    owned = {r[0] for r in rows.all()}
    if not owned:
        raise HTTPException(status_code=403, detail="Chỉ chủ đơn vị (owner) hoặc super admin mới quản lý cán bộ")
    if requested is not None and requested not in owned:
        raise HTTPException(status_code=403, detail="Bạn không phải chủ (owner) của đơn vị này")
    return StaffScope(user, owned, requested)


# -- Schemas --
class CreateEmployeeRequest(BaseModel):
    email: str
    name: str
    employee_code: str | None = None
    branch: str | None = None
    department: str | None = None
    position: str | None = None
    password: str | None = None  # optional, defaults to DEFAULT_PASSWORD
    workspace_id: str | None = None  # đơn vị; None → sees only bank-wide assistants


class UpdateEmployeeRequest(BaseModel):
    name: str | None = None
    employee_code: str | None = None
    branch: str | None = None
    department: str | None = None
    position: str | None = None
    workspace_id: str | None = None   # "" clears the unit
    is_active: bool | None = None


class EmployeeItem(BaseModel):
    id: str
    email: str
    name: str
    employee_code: str | None
    branch: str | None
    department: str | None
    position: str | None
    is_active: bool
    must_change_password: bool
    created_at: str
    workspace_id: str | None = None
    workspace_name: str | None = None


class ImportResult(BaseModel):
    created: int
    skipped: int
    errors: list[str]


def _to_item(e: Employee, workspace_name: str | None = None) -> EmployeeItem:
    return EmployeeItem(
        id=str(e.id),
        email=e.email,
        name=e.name,
        employee_code=e.employee_code,
        branch=e.branch,
        department=e.department,
        position=e.position,
        is_active=e.is_active,
        must_change_password=e.must_change_password,
        created_at=e.created_at.isoformat(),
        workspace_id=str(e.workspace_id) if e.workspace_id else None,
        workspace_name=workspace_name,
    )


async def _resolve_workspace(db: AsyncSession, workspace_id: str | None) -> Workspace | None:
    """'' / None → no unit; otherwise the workspace must exist (400)."""
    if not workspace_id:
        return None
    try:
        ws = await db.get(Workspace, uuid.UUID(workspace_id))
    except ValueError:
        ws = None
    if not ws:
        raise HTTPException(status_code=400, detail="Đơn vị (workspace) không tồn tại")
    return ws


# -- Endpoints --
@router.post("", response_model=EmployeeItem, status_code=201)
async def create_employee(
    body: CreateEmployeeRequest,
    scope: StaffScope = Depends(staff_scope),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(Employee).where(Employee.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    ws = await _resolve_workspace(db, body.workspace_id)
    target = scope.unit_or_403(ws.id if ws else scope.default_unit())  # unit admin → must be an owned unit
    if target and (not ws or ws.id != target):
        ws = await db.get(Workspace, target)
    pwd = body.password or DEFAULT_PASSWORD
    employee = Employee(
        email=body.email,
        password_hash=hash_password(pwd),
        name=body.name,
        employee_code=body.employee_code,
        branch=body.branch,
        department=body.department,
        position=body.position,
        workspace_id=target,
        must_change_password=(pwd == DEFAULT_PASSWORD),
    )
    db.add(employee)
    await db.commit()
    await db.refresh(employee)
    return _to_item(employee, ws.name if ws else None)


@router.get("", response_model=list[EmployeeItem])
async def list_employees(
    scope: StaffScope = Depends(staff_scope),
    db: AsyncSession = Depends(get_db),
):
    """Super admin: everyone (``?workspace_id=`` filters). Unit admin: only their unit's staff."""
    q = (select(Employee, Workspace.name)
         .outerjoin(Workspace, Workspace.id == Employee.workspace_id)
         .order_by(Employee.created_at.desc()))
    if scope.is_super:
        if scope.requested is not None:
            q = q.where(Employee.workspace_id == scope.requested)
    else:
        unit = scope.default_unit()
        if unit is None:
            raise HTTPException(status_code=400, detail="Chọn đơn vị (X-Workspace-Id) để xem cán bộ")
        q = q.where(Employee.workspace_id == unit)
    result = await db.execute(q)
    return [_to_item(e, ws_name) for e, ws_name in result.all()]


@router.patch("/{employee_id}", response_model=EmployeeItem)
async def update_employee(
    employee_id: str,
    body: UpdateEmployeeRequest,
    scope: StaffScope = Depends(staff_scope),
    db: AsyncSession = Depends(get_db),
):
    """Update profile fields — mainly to assign the employee to a unit (workspace)."""
    employee = await db.get(Employee, uuid.UUID(employee_id))
    if not employee or not scope.can_manage(employee.workspace_id):  # other units' staff are invisible
        raise HTTPException(status_code=404, detail="Employee not found")
    data = body.model_dump(exclude_unset=True)
    if "workspace_id" in data:
        ws = await _resolve_workspace(db, data.pop("workspace_id"))
        employee.workspace_id = scope.unit_or_403(ws.id if ws else None)
    for k, v in data.items():
        setattr(employee, k, v)
    await db.commit()
    await db.refresh(employee)
    ws_name = (await db.get(Workspace, employee.workspace_id)).name if employee.workspace_id else None
    return _to_item(employee, ws_name)


@router.post("/import-csv", response_model=ImportResult)
async def import_csv(
    request: Request,
    file: UploadFile = File(...),
    scope: StaffScope = Depends(staff_scope),
    db: AsyncSession = Depends(get_db),
):
    """Import employees from CSV.

    Columns: email, name, employee_code, branch, department, position, unit
    (all but email/name optional). `unit` is the workspace name (case-insensitive) or id;
    rows without it fall back to the admin's active unit (X-Workspace-Id header), else no unit.
    """
    content = await file.read()
    text = content.decode("utf-8-sig")  # handle BOM
    reader = csv.DictReader(io.StringIO(text))

    created = 0
    skipped = 0
    errors: list[str] = []
    hashed_default = hash_password(DEFAULT_PASSWORD)

    workspaces = (await db.execute(select(Workspace))).scalars().all()
    by_name = {w.name.strip().lower(): w for w in workspaces}
    by_id = {str(w.id): w for w in workspaces}
    default_unit = scope.default_unit()
    default_ws = by_id.get(str(default_unit)) if default_unit else None

    def _col(row: dict, *names: str) -> str | None:
        for n in names:
            v = (row.get(n) or "").strip()
            if v:
                return v
        return None

    for i, row in enumerate(reader, start=2):
        email = _col(row, "email") or ""
        name = _col(row, "name") or ""

        if not email or not name:
            errors.append(f"Row {i}: missing email or name")
            continue

        existing = await db.execute(select(Employee.id).where(Employee.email == email))
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        unit = _col(row, "unit", "workspace", "workspace_id")
        if unit:
            ws = by_id.get(unit) or by_name.get(unit.lower())
            if not ws:
                errors.append(f"Row {i}: unknown unit '{unit}'")
                continue
        else:
            ws = default_ws
        if not scope.is_super and not scope.can_manage(ws.id if ws else None):
            errors.append(f"Row {i}: unit '{unit or '(none)'}' is not one you manage")
            continue

        db.add(Employee(
            email=email,
            password_hash=hashed_default,
            name=name,
            employee_code=_col(row, "employee_code"),
            branch=_col(row, "branch"),
            department=_col(row, "department"),
            position=_col(row, "position"),
            workspace_id=ws.id if ws else None,
            must_change_password=True,
        ))
        created += 1

    await db.commit()
    return ImportResult(created=created, skipped=skipped, errors=errors)


@router.delete("/{employee_id}", status_code=200)
async def deactivate_employee(
    employee_id: str,
    scope: StaffScope = Depends(staff_scope),
    db: AsyncSession = Depends(get_db),
):
    employee = await db.get(Employee, uuid.UUID(employee_id))
    if not employee or not scope.can_manage(employee.workspace_id):
        raise HTTPException(status_code=404, detail="Employee not found")
    employee.is_active = False
    # Bộ nhớ cá nhân đi theo người. Quyền xoá của Luật Bảo vệ dữ liệu cá nhân, và không để lại dữ
    # liệu mồ côi không ai còn quyền xem hay sửa.
    from app.services.memory import forget_employee

    forgotten = await forget_employee(db, employee.id)
    await db.commit()
    if forgotten:
        logger.info("deactivated employee %s and removed %d memories", employee.id, forgotten)
    return {"detail": "Employee deactivated", "memories_removed": forgotten}

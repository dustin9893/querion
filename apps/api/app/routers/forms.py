"""Business forms — admin side: define the fields, upload the .docx, wire prefill, publish.

Staff fill them through /v1/staff/forms/* (routers/staff_auth.py); both sides share
services/forms.py so the validation and the PII rule are defined once.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import WorkspaceContext, require_ws_role
from app.deps import get_db
from app.models.form_template import FormTemplate
from app.models.user_workspace import WsRole
from app.services.forms import FormError, coerce_values, validate_fields, visible_forms
from app.services.reports import (
    DOCX_MIME, ReportError, docx_variables, render_docx, safe_filename, store_artifact,
    template_storage_key,
)
from app.storage import download_file, upload_file

router = APIRouter(prefix="/v1", tags=["forms"])

MAX_TEMPLATE_BYTES = 5 * 1024 * 1024


class FormCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: str | None = ""
    fields: list[dict[str, Any]] = []
    prefill_tool_id: str | None = None
    prefill_arg: str | None = None
    prefill_mapping: dict[str, str] = {}
    is_published: bool = False
    share_scope: str = "unit"


class FormUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    fields: list[dict[str, Any]] | None = None
    prefill_tool_id: str | None = None
    prefill_arg: str | None = None
    prefill_mapping: dict[str, str] | None = None
    is_published: bool | None = None
    share_scope: str | None = None


class FormResponse(BaseModel):
    id: str
    workspace_id: str
    own_unit: bool
    name: str
    description: str | None
    fields: list[dict[str, Any]]
    template_filename: str | None
    has_template: bool
    prefill_tool_id: str | None
    prefill_arg: str | None
    prefill_mapping: dict[str, str]
    is_published: bool
    share_scope: str
    created_at: str
    updated_at: str


def to_response(f: FormTemplate, workspace_id=None) -> FormResponse:
    return FormResponse(
        id=str(f.id), workspace_id=str(f.workspace_id), own_unit=(workspace_id is None or f.workspace_id == workspace_id),
        name=f.name, description=f.description, fields=list(f.fields or []),
        template_filename=f.template_filename, has_template=bool(f.template_storage_key),
        prefill_tool_id=str(f.prefill_tool_id) if f.prefill_tool_id else None,
        prefill_arg=f.prefill_arg, prefill_mapping=dict(f.prefill_mapping or {}),
        is_published=f.is_published, share_scope=f.share_scope,
        created_at=f.created_at.isoformat(), updated_at=f.updated_at.isoformat(),
    )


async def _own_form(db: AsyncSession, form_id: str, workspace_id) -> FormTemplate:
    """Editing stays with the owning unit, even for a form shared bank-wide."""
    try:
        fid = uuid.UUID(form_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Không tìm thấy biểu mẫu")
    form = await db.get(FormTemplate, fid)
    if not form or form.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy biểu mẫu trong đơn vị này")
    return form


@router.get("/forms", response_model=list[FormResponse])
async def list_forms(
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    forms = await visible_forms(db, ws_ctx.workspace_id)
    return [to_response(f, ws_ctx.workspace_id) for f in forms]


@router.post("/forms", response_model=FormResponse, status_code=201)
async def create_form(
    body: FormCreate,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    try:
        fields = validate_fields(body.fields)
    except FormError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if body.share_scope == "bank" and not ws_ctx.has_role(WsRole.owner):
        raise HTTPException(status_code=403, detail="Chỉ chủ đơn vị mới mở biểu mẫu cho toàn ngân hàng")

    form = FormTemplate(
        workspace_id=ws_ctx.workspace_id, name=body.name, description=body.description or "",
        fields=fields, prefill_tool_id=uuid.UUID(body.prefill_tool_id) if body.prefill_tool_id else None,
        prefill_arg=body.prefill_arg or None, prefill_mapping=body.prefill_mapping or {},
        is_published=body.is_published, share_scope=body.share_scope if body.share_scope in ("unit", "bank") else "unit",
    )
    db.add(form)
    await db.commit()
    await db.refresh(form)
    return to_response(form, ws_ctx.workspace_id)


@router.patch("/forms/{form_id}", response_model=FormResponse)
async def update_form(
    form_id: str,
    body: FormUpdate,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    form = await _own_form(db, form_id, ws_ctx.workspace_id)
    data = body.model_dump(exclude_unset=True)

    if data.get("fields") is not None:
        try:
            form.fields = validate_fields(data["fields"])
        except FormError as e:
            raise HTTPException(status_code=400, detail=str(e))
    if data.get("share_scope") and data["share_scope"] != form.share_scope:
        if data["share_scope"] not in ("unit", "bank"):
            raise HTTPException(status_code=400, detail="share_scope phải là 'unit' hoặc 'bank'")
        if data["share_scope"] == "bank" and not ws_ctx.has_role(WsRole.owner):
            raise HTTPException(status_code=403, detail="Chỉ chủ đơn vị mới mở biểu mẫu cho toàn ngân hàng")
        form.share_scope = data["share_scope"]
    if data.get("is_published") and not form.template_storage_key:
        raise HTTPException(status_code=400, detail="Tải mẫu .docx lên trước khi công bố biểu mẫu")
    for key in ("name", "description", "prefill_arg", "prefill_mapping", "is_published"):
        if key in data and data[key] is not None:
            setattr(form, key, data[key])
    if "prefill_tool_id" in data:
        form.prefill_tool_id = uuid.UUID(data["prefill_tool_id"]) if data["prefill_tool_id"] else None

    form.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(form)
    return to_response(form, ws_ctx.workspace_id)


@router.delete("/forms/{form_id}", status_code=204)
async def delete_form(
    form_id: str,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    form = await _own_form(db, form_id, ws_ctx.workspace_id)
    await db.delete(form)
    await db.commit()


@router.post("/forms/{form_id}/template", response_model=FormResponse)
async def upload_form_template(
    form_id: str,
    file: UploadFile = File(...),
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    """Attach the .docx and check that every placeholder matches a declared field."""
    form = await _own_form(db, form_id, ws_ctx.workspace_id)
    name = file.filename or "bieu-mau.docx"
    if not name.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Chỉ nhận tệp .docx")
    data = await file.read(MAX_TEMPLATE_BYTES + 1)
    if len(data) > MAX_TEMPLATE_BYTES:
        raise HTTPException(status_code=400, detail="Mẫu tối đa 5MB")
    try:
        placeholders = docx_variables(data)
    except ReportError as e:
        raise HTTPException(status_code=400, detail=str(e))

    known = {f["name"] for f in (form.fields or [])} | {"today", "time", "now", "can_bo", "don_vi"}
    unknown = sorted(p for p in placeholders if p not in known)
    if unknown:
        raise HTTPException(status_code=400,
                            detail=f"Mẫu dùng biến chưa khai báo trong biểu mẫu: {', '.join(unknown)}")

    form.template_storage_key = template_storage_key(form.workspace_id, form.id, name)
    form.template_filename = name
    upload_file(form.template_storage_key, data, DOCX_MIME)
    form.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(form)
    return to_response(form, ws_ctx.workspace_id)


class FormRenderRequest(BaseModel):
    values: dict[str, Any] = {}


@router.post("/forms/{form_id}/render", status_code=201)
async def render_form_preview(
    form_id: str,
    body: FormRenderRequest,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    """Fill the form with test values so the admin can check the .docx before publishing."""
    form = await _own_form(db, form_id, ws_ctx.workspace_id)
    artifact = await fill_form(db, form, body.values, created_by_user_id=ws_ctx.user.id,
                               author="Bản thử của quản trị", audience="admin")
    await db.commit()
    return {"artifact_id": str(artifact.id), "filename": artifact.filename}


async def fill_form(db: AsyncSession, form: FormTemplate, values: dict[str, Any], *,
                    created_by_user_id=None, created_by_employee_id=None,
                    author: str = "", audience: str = "staff"):
    """Shared by the admin preview and the staff submit: values → .docx → artifact row."""
    if not form.template_storage_key:
        raise HTTPException(status_code=400, detail="Biểu mẫu chưa có mẫu .docx")
    try:
        clean = coerce_values(list(form.fields or []), values)
    except FormError as e:
        raise HTTPException(status_code=400, detail=str(e))

    from app.services.reports import VN_TZ

    now = datetime.now(VN_TZ)
    context = {**clean, "today": now.strftime("%d/%m/%Y"), "time": now.strftime("%H:%M"), "now": now,
               "can_bo": author, "don_vi": ""}
    try:
        data = render_docx(download_file(form.template_storage_key), context)
    except ReportError as e:
        raise HTTPException(status_code=400, detail=str(e))

    title = f"{form.name} — {now.strftime('%d/%m/%Y %H:%M')}"
    return await store_artifact(
        db, workspace_id=form.workspace_id, data=data,
        filename=safe_filename(f"{form.name} {now.strftime('%d-%m-%Y %H%M')}", "docx"),
        content_type=DOCX_MIME, title=title, kind="form", audience=audience,
        created_by_user_id=created_by_user_id, created_by_employee_id=created_by_employee_id,
    )

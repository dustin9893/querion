"""Tools CRUD, scoped to a business unit — the registry assistants draw from.

Same scoping rules as datasets and assistants: a tool belongs to the unit in the
``X-Workspace-Id`` header, editors manage it, and only a workspace **owner** may open it to
the whole bank (``share_scope = "bank"``) or let the customer channel use it, because both
decisions reach beyond the unit.

Secrets are write-only: the API accepts ``secret`` and never returns it, only ``has_secret``.
"""

import uuid
from typing import Any

import jsonschema

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import WorkspaceContext, require_ws_role
from app.deps import get_db
from app.models.tool import TOOL_KINDS, AppTool, Tool
from app.models.user_workspace import WsRole
from app.services.encryption import encrypt_key
from app.services.tools.builtin import BUILTINS
from app.services.tools.executor import ToolError, execute_http, http_target_blocked, tool_secret
from app.services.tools.export import export_args_schema
from app.services.tools.registry import SLUG_RE, visible_tools

router = APIRouter(prefix="/v1/tools", tags=["tools"])

MAX_TOOLS_PER_WORKSPACE = 50


# ---------- Schemas ----------

class ToolCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(..., min_length=1, max_length=2000)
    kind: str = "http"
    config: dict[str, Any] = {}
    params_schema: dict[str, Any] = {}
    secret: str | None = None
    requires_approval: bool = False
    allow_customer: bool = False
    share_scope: str = "unit"
    timeout_sec: int = Field(10, ge=1, le=60)


class ToolUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    config: dict[str, Any] | None = None
    params_schema: dict[str, Any] | None = None
    secret: str | None = None          # "" clears it
    requires_approval: bool | None = None
    allow_customer: bool | None = None
    share_scope: str | None = None
    is_active: bool | None = None
    timeout_sec: int | None = Field(None, ge=1, le=60)


class ToolResponse(BaseModel):
    id: str
    workspace_id: str
    slug: str
    name: str
    description: str
    kind: str
    config: dict[str, Any]
    params_schema: dict[str, Any]
    has_secret: bool
    requires_approval: bool
    allow_customer: bool
    share_scope: str
    is_active: bool
    timeout_sec: int
    own_unit: bool = True
    used_by: int = 0
    created_at: str
    updated_at: str


class ToolTestRequest(BaseModel):
    args: dict[str, Any] = {}


def _to_response(t: Tool, *, workspace_id=None, used_by: int = 0) -> ToolResponse:
    return ToolResponse(
        id=str(t.id), workspace_id=str(t.workspace_id), slug=t.slug, name=t.name,
        description=t.description, kind=t.kind, config=dict(t.config or {}),
        params_schema=dict(t.params_schema or {}), has_secret=bool(t.secret_encrypted),
        requires_approval=t.requires_approval, allow_customer=t.allow_customer,
        share_scope=t.share_scope or "unit", is_active=t.is_active, timeout_sec=t.timeout_sec,
        own_unit=(workspace_id is None or t.workspace_id == workspace_id), used_by=used_by,
        created_at=t.created_at.isoformat(), updated_at=t.updated_at.isoformat(),
    )


# ---------- Validation ----------

def _validate_schema(schema: dict) -> dict:
    """The params schema goes straight into the function definition sent to the model."""
    if not schema:
        return {"type": "object", "properties": {}}
    if schema.get("type") != "object" or not isinstance(schema.get("properties"), dict):
        raise HTTPException(status_code=400, detail="params_schema phải là JSON Schema kiểu object có 'properties'")
    if len(schema.get("properties", {})) > 20:
        raise HTTPException(status_code=400, detail="Tối đa 20 tham số")
    try:
        import jsonschema
        jsonschema.Draft202012Validator.check_schema(schema)
    except ImportError:
        pass
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"params_schema không hợp lệ: {exc}")
    return schema


def _validate_config(kind: str, config: dict) -> dict:
    if kind == "builtin":
        fn = config.get("fn")
        if fn not in BUILTINS:
            raise HTTPException(status_code=400, detail=f"fn phải là một trong: {', '.join(BUILTINS)}")
        return {"fn": fn}
    if kind == "http":
        url = (config.get("url") or "").strip()
        if not url:
            raise HTTPException(status_code=400, detail="Cần cấu hình URL")
        # Placeholders are filled at call time; check the literal part of the host now.
        probe = url.split("{{")[0] or url
        if probe.startswith(("http://", "https://")):
            blocked = http_target_blocked(probe if "/" in probe[8:] else probe + "/")
            if blocked:
                raise HTTPException(status_code=400, detail=f"URL bị chặn: {blocked}")
        else:
            raise HTTPException(status_code=400, detail="URL phải bắt đầu bằng http:// hoặc https://")
        if str(config.get("method", "GET")).upper() not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            raise HTTPException(status_code=400, detail="method không hợp lệ")
        return config
    if kind == "report":
        if not str(config.get("workflow_id") or "").strip():
            raise HTTPException(status_code=400, detail="Công cụ báo cáo cần chọn luồng báo cáo")
        return {"workflow_id": str(config["workflow_id"])}
    if kind == "export":
        fmt = str(config.get("format") or "xlsx").lower()
        if fmt != "xlsx":
            raise HTTPException(status_code=400, detail="Công cụ xuất tệp hiện chỉ hỗ trợ định dạng xlsx")
        return {"format": fmt}
    if kind == "mcp":
        transport = config.get("transport", "streamable_http")
        if transport == "stdio":
            if not config.get("command"):
                raise HTTPException(status_code=400, detail="MCP stdio cần 'command'")
        else:
            blocked = http_target_blocked(config.get("url") or "")
            if blocked:
                raise HTTPException(status_code=400, detail=f"URL MCP bị chặn: {blocked}")
        return config
    raise HTTPException(status_code=400, detail=f"kind phải là một trong: {', '.join(TOOL_KINDS)}")


def _require_owner_for(ws_ctx: WorkspaceContext, what: str) -> None:
    if not ws_ctx.has_role(WsRole.owner):
        raise HTTPException(status_code=403, detail=f"Chỉ chủ đơn vị (owner) mới được {what}")


# ---------- Endpoints ----------

@router.get("/builtins")
async def list_builtins(_: WorkspaceContext = Depends(require_ws_role(WsRole.viewer))):
    """Calculations that run locally, offered as ready-made tools in the UI."""
    return [{"fn": fn, "name": e["name"], "description": e["description"], "params_schema": e["schema"]}
            for fn, e in BUILTINS.items()]


@router.get("", response_model=list[ToolResponse])
async def list_tools(
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.viewer)),
    db: AsyncSession = Depends(get_db),
):
    """Tools this unit may use: its own, plus any opened bank-wide by another unit."""
    rows = await visible_tools(db, ws_ctx.workspace_id)
    counts = {tid: n for tid, n in (await db.execute(
        select(AppTool.tool_id, func.count()).group_by(AppTool.tool_id)
    )).all()}
    return [_to_response(t, workspace_id=ws_ctx.workspace_id, used_by=counts.get(t.id, 0)) for t in rows]


@router.post("", response_model=ToolResponse, status_code=201)
async def create_tool(
    body: ToolCreate,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    if not SLUG_RE.match(body.slug):
        raise HTTPException(status_code=400, detail="slug chỉ gồm chữ, số, gạch dưới và gạch ngang, tối đa 64 ký tự")
    existing = (await db.execute(select(Tool).where(
        Tool.workspace_id == ws_ctx.workspace_id, Tool.slug == body.slug))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Đơn vị đã có công cụ với slug này")
    total = (await db.execute(select(func.count()).select_from(Tool)
                              .where(Tool.workspace_id == ws_ctx.workspace_id))).scalar() or 0
    if total >= MAX_TOOLS_PER_WORKSPACE:
        raise HTTPException(status_code=400, detail=f"Mỗi đơn vị tối đa {MAX_TOOLS_PER_WORKSPACE} công cụ")
    if body.share_scope not in ("unit", "bank"):
        raise HTTPException(status_code=400, detail="share_scope phải là 'unit' hoặc 'bank'")
    if body.share_scope == "bank":
        _require_owner_for(ws_ctx, "mở công cụ cho toàn ngân hàng")
    if body.allow_customer:
        _require_owner_for(ws_ctx, "cho phép kênh khách hàng dùng công cụ")

    config = _validate_config(body.kind, dict(body.config or {}))
    if body.kind == "builtin":
        schema = dict(BUILTINS[config["fn"]]["schema"])
    elif body.kind == "report":
        schema = await _report_schema(db, config, ws_ctx.workspace_id)
    elif body.kind == "export":
        # the arguments are the spreadsheet itself, so the schema is fixed, never author-supplied
        schema = export_args_schema()
    else:
        schema = _validate_schema(dict(body.params_schema or {}))

    tool = Tool(
        workspace_id=ws_ctx.workspace_id, slug=body.slug, name=body.name, description=body.description,
        kind=body.kind, config=config, params_schema=schema,
        secret_encrypted=encrypt_key(body.secret) if body.secret else None,
        requires_approval=body.requires_approval, allow_customer=body.allow_customer,
        share_scope=body.share_scope, timeout_sec=body.timeout_sec,
    )
    db.add(tool)
    await db.commit()
    await db.refresh(tool)
    return _to_response(tool, workspace_id=ws_ctx.workspace_id)


async def _report_schema(db: AsyncSession, config: dict, workspace_id) -> dict:
    """Check the report workflow and derive the tool's arguments from its input fields."""
    from app.models.workflow import Workflow
    from app.services.tools.registry import report_args_schema

    try:
        wf_id = uuid.UUID(str(config.get("workflow_id")))
    except ValueError:
        raise HTTPException(status_code=400, detail="workflow_id không hợp lệ")
    wf = (await db.execute(select(Workflow).where(
        Workflow.id == wf_id, Workflow.workspace_id == workspace_id))).scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Luồng báo cáo không thuộc đơn vị này")
    if wf.type != "report":
        raise HTTPException(status_code=400, detail="Chỉ gắn được luồng kiểu 'báo cáo' vào công cụ báo cáo")
    return report_args_schema(wf)


async def _load_own(db: AsyncSession, tool_id: str, ws_ctx: WorkspaceContext) -> Tool:
    """A tool can only be edited from the unit that owns it, never from a unit it is shared with."""
    try:
        tool = await db.get(Tool, uuid.UUID(tool_id))
    except ValueError:
        tool = None
    if not tool or tool.workspace_id != ws_ctx.workspace_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy công cụ trong đơn vị này")
    return tool


async def _load_usable(db: AsyncSession, tool_id: str, ws_ctx: WorkspaceContext) -> Tool:
    """A tool this unit may bind and run: its own, or an active one another unit opened bank-wide."""
    try:
        tool = await db.get(Tool, uuid.UUID(tool_id))
    except ValueError:
        tool = None
    usable = tool and (tool.workspace_id == ws_ctx.workspace_id
                       or (tool.share_scope == "bank" and tool.is_active))
    if not usable:
        raise HTTPException(status_code=404, detail="Không tìm thấy công cụ trong đơn vị này")
    return tool


@router.patch("/{tool_id}", response_model=ToolResponse)
async def update_tool(
    tool_id: str,
    body: ToolUpdate,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    tool = await _load_own(db, tool_id, ws_ctx)
    data = body.model_dump(exclude_unset=True)

    if "share_scope" in data and data["share_scope"] != (tool.share_scope or "unit"):
        if data["share_scope"] not in ("unit", "bank"):
            raise HTTPException(status_code=400, detail="share_scope phải là 'unit' hoặc 'bank'")
        _require_owner_for(ws_ctx, "đổi phạm vi chia sẻ công cụ")
    if data.get("allow_customer") and not tool.allow_customer:
        _require_owner_for(ws_ctx, "cho phép kênh khách hàng dùng công cụ")
    if "config" in data:
        data["config"] = _validate_config(tool.kind, dict(data["config"] or {}))
        if tool.kind == "builtin":
            tool.params_schema = dict(BUILTINS[data["config"]["fn"]]["schema"])
        elif tool.kind == "report":
            tool.params_schema = await _report_schema(db, data["config"], ws_ctx.workspace_id)
        elif tool.kind == "export":
            tool.params_schema = export_args_schema()
    if "params_schema" in data and tool.kind in ("http", "mcp"):
        data["params_schema"] = _validate_schema(dict(data["params_schema"] or {}))
    elif "params_schema" in data:
        data.pop("params_schema")
    if "secret" in data:
        secret = data.pop("secret")
        tool.secret_encrypted = encrypt_key(secret) if secret else None

    for key, value in data.items():
        setattr(tool, key, value)
    await db.commit()
    await db.refresh(tool)
    return _to_response(tool, workspace_id=ws_ctx.workspace_id)


@router.delete("/{tool_id}", status_code=204)
async def delete_tool(
    tool_id: str,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    tool = await _load_own(db, tool_id, ws_ctx)
    await db.delete(tool)
    await db.commit()


@router.post("/{tool_id}/test")
async def test_tool(
    tool_id: str,
    body: ToolTestRequest,
    ws_ctx: WorkspaceContext = Depends(require_ws_role(WsRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    """Run the tool once with the given arguments so an admin can check it before publishing.

    Bank-shared tools of other units can be run too (they can be bound here), never edited.
    """
    tool = await _load_usable(db, tool_id, ws_ctx)
    try:
        if tool.kind == "builtin":
            from app.services.tools.builtin import get_builtin
            entry = get_builtin((tool.config or {}).get("fn", ""))
            if not entry:
                raise ToolError("Công cụ dựng sẵn không tồn tại")
            fn, schema = entry
            jsonschema.validate(body.args, schema)
            return {"ok": True, "result": fn(**body.args)}
        if tool.kind == "http":
            if tool.params_schema:
                jsonschema.validate(body.args, tool.params_schema)
            text = await execute_http(dict(tool.config or {}), body.args,
                                      secret=tool_secret(tool.secret_encrypted), timeout_sec=tool.timeout_sec)
            return {"ok": True, "result": text[:4000]}
        if tool.kind == "export":
            from app.services.tools.executor import split_artifacts
            from app.services.tools.export import export_callable

            jsonschema.validate(body.args, export_args_schema())
            callable_, holder = export_callable(tool, workspace_id=ws_ctx.workspace_id,
                                                channel="admin_test", actor_user_id=ws_ctx.user.id)
            holder["schema"] = export_args_schema()
            text, files = split_artifacts(await callable_(**body.args))
            return {"ok": True, "result": {"tep": files, "ket_qua": text[:1500]}}
        if tool.kind == "report":
            from app.services.tools.executor import split_artifacts
            from app.services.tools.registry import _report_callable

            jsonschema.validate(body.args, dict(tool.params_schema or {}))
            callable_, holder = _report_callable(tool, uuid.UUID(str((tool.config or {}).get("workflow_id"))), "admin_test")
            holder["schema"] = dict(tool.params_schema or {})
            text, files = split_artifacts(await callable_(**body.args))
            return {"ok": True, "result": {"tep": files, "ket_qua": text[:1500]}}
        # MCP: report what the server exposes rather than calling a specific tool
        from app.services.tools.registry import _mcp_tools
        discovered = await _mcp_tools(tool)
        return {"ok": bool(discovered), "result": [{"name": b.slug, "description": b.tool.description} for b in discovered]
                or "Không kết nối được MCP server hoặc server không có công cụ nào."}
    except jsonschema.ValidationError as exc:
        where = ".".join(str(p) for p in exc.path)
        return {"ok": False, "error": f"Tham số không hợp lệ{f' ({where})' if where else ''}: {exc.message}"}
    except ToolError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:300]}"}

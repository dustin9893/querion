"""Turning `tools` rows into callables the agent can use.

Visibility follows the same rule as assistants: a tool belongs to a business unit, and an
assistant may bind it when it is in the same unit or the owner opened it bank-wide. On the
customer channel only tools explicitly flagged ``allow_customer`` are loaded, so an
internal endpoint can never be reached from the public page or an embedded bubble.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.app import App
from app.models.tool import AppTool, Tool
from app.services.tools.builtin import get_builtin
from app.services.tools.executor import (
    ToolError, as_untrusted_block, attach_artifacts, execute_http, http_target_blocked, tool_secret,
)

logger = logging.getLogger(__name__)

SLUG_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
MCP_PREFIX_SEP = "__"


@dataclass
class BoundTool:
    """A callable exposed to the model, plus the policy the wrapper needs."""

    slug: str                    # the name the model calls
    tool: BaseTool
    tool_id: Any                 # uuid of the `tools` row (an MCP row covers several)
    display_name: str
    requires_approval: bool
    kind: str


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

async def visible_tools(db: AsyncSession, workspace_id, *, include_bank: bool = True) -> list[Tool]:
    """Tools a unit may bind: its own, plus the ones shared bank-wide."""
    cond = Tool.workspace_id == workspace_id
    if include_bank:
        cond = or_(cond, Tool.share_scope == "bank")
    rows = await db.execute(select(Tool).where(cond, Tool.is_active.is_(True)).order_by(Tool.name))
    return list(rows.scalars().all())


async def app_tool_rows(db: AsyncSession, app: App, *, channel: str) -> list[Tool]:
    """Tools bound to this assistant that the given channel is allowed to use."""
    rows = await db.execute(
        select(Tool).join(AppTool, AppTool.tool_id == Tool.id).where(
            AppTool.app_id == app.id,
            Tool.is_active.is_(True),
            or_(Tool.workspace_id == app.workspace_id, Tool.share_scope == "bank"),
        ).order_by(Tool.name)
    )
    tools = list(rows.scalars().all())
    if channel in ("customer", "embed") and app.audience == "customer":
        # No staff member is present to approve, so approval-gated tools are simply not offered.
        tools = [t for t in tools if t.allow_customer and not t.requires_approval]
    return tools


# ---------------------------------------------------------------------------
# Building callables
# ---------------------------------------------------------------------------

async def _app_skill_rows(db: AsyncSession, app: App, *, channel: str):
    """Kỹ năng đã công bố mà trợ lý được dùng trên kênh này."""
    from app.services.skills import app_skills

    return await app_skills(db, app, channel=channel)


def _validate_args(schema: dict, args: dict) -> None:
    """A JSON-Schema `args_schema` is not enforced by LangChain, so check it ourselves."""
    if not schema:
        return
    try:
        import jsonschema
    except ImportError:  # pragma: no cover
        return
    try:
        jsonschema.validate(args, schema)
    except jsonschema.ValidationError as exc:
        raise ToolError(f"Tham số không hợp lệ: {exc.message}")


def _http_callable(row: Tool):
    secret = tool_secret(row.secret_encrypted)
    config, schema, slug, timeout = dict(row.config or {}), dict(row.params_schema or {}), row.slug, row.timeout_sec

    async def run(**kwargs: Any) -> str:
        _validate_args(schema, kwargs)
        payload = await execute_http(config, kwargs, secret=secret, timeout_sec=timeout)
        return as_untrusted_block(slug, payload)

    return run


def _builtin_callable(row: Tool, fn, schema: dict):
    slug = row.slug

    async def run(**kwargs: Any) -> str:
        _validate_args(schema, kwargs)
        try:
            result = fn(**kwargs)
        except (ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
            raise ToolError(str(exc))
        # Built-ins compute locally, so the result is trusted; still keep one shape for the model.
        return as_untrusted_block(slug, json.dumps(result, ensure_ascii=False))

    return run


def report_args_schema(workflow) -> dict:
    """JSON Schema the model must fill: the report workflow's own input fields."""
    nodes = (workflow.graph_json or {}).get("nodes", [])
    fields = next((n.get("data", {}).get("fields") or [] for n in nodes if n.get("type") == "input"), [])
    types = {"number": "number", "boolean": "boolean"}
    properties, required = {}, []
    for field in fields:
        name = str(field.get("name") or "").strip()
        if not name:
            continue
        prop: dict[str, Any] = {"type": types.get(field.get("type"), "string"),
                                "description": field.get("description") or field.get("label") or name}
        if field.get("options"):
            prop["enum"] = [str(o) for o in field["options"]]
        properties[name] = prop
        if field.get("required"):
            required.append(name)
    return {"type": "object", "properties": properties, "required": required}


def _report_callable(row: Tool, workflow_id, channel: str, actor_employee_id=None, actor_user_id=None):
    """Run a report workflow on its own session and hand the files back to the chat."""
    slug, schema_holder = row.slug, {}

    async def run(**kwargs: Any) -> str:
        from app.db import async_session_factory
        from app.models.workflow import Workflow
        from app.services.observability import complete_run, create_run
        from app.services.workflow_runtime import run_workflow

        async with async_session_factory() as db:
            wf = await db.get(Workflow, workflow_id)
            if wf is None:
                raise ToolError("Luồng báo cáo đã bị xoá")
            _validate_args(schema_holder.get("schema") or report_args_schema(wf), kwargs)
            run_row = await create_run(db, workflow_id=wf.id, workspace_id=wf.workspace_id,
                                       employee_id=actor_employee_id, user_id=actor_user_id,
                                       channel=channel if channel in ("staff", "admin_test") else "report",
                                       query=f"{row.name}")
            await db.commit()
            try:
                result = await run_workflow(db, wf.graph_json, query=wf.name, inputs=kwargs,
                                            run=run_row, workspace_id=wf.workspace_id,
                                            actor_employee_id=actor_employee_id, actor_user_id=actor_user_id)
            except Exception as exc:
                await complete_run(run_row, status="failed", error=f"{type(exc).__name__}: {exc}")
                await db.commit()
                raise ToolError(f"Chạy báo cáo thất bại: {type(exc).__name__}")
            files = [a for a in result.get("artifacts", []) if a.get("id")]
            errors = [a["error"] for a in result.get("artifacts", []) if a.get("error")]
            await complete_run(run_row, status="completed" if files else "failed",
                               answer=result.get("answer"), error="; ".join(errors) or None)
            await db.commit()

        if not files:
            raise ToolError("Báo cáo chạy xong nhưng không tạo được tệp" + (f": {errors[0]}" if errors else ""))
        payload = {
            "bao_cao": row.name,
            "tham_so": kwargs,
            "tep_da_tao": [{"ten_tep": f.get("filename"), "tieu_de": f.get("title")} for f in files],
            "tom_tat": (result.get("answer") or "")[:2000],
        }
        # The block is what the model reads; the files ride along for the UI only.
        return attach_artifacts(as_untrusted_block(slug, json.dumps(payload, ensure_ascii=False)), files)

    return run, schema_holder


def _structured(row: Tool, schema: dict, coroutine) -> BaseTool:
    return StructuredTool(
        name=row.slug, description=row.description or row.name,
        args_schema=schema or {"type": "object", "properties": {}},
        coroutine=coroutine, func=None, handle_tool_error=True,
    )


async def _mcp_tools(row: Tool) -> list[BoundTool]:
    """Discover the tools an MCP server exposes; names are prefixed with the row's slug."""
    config = dict(row.config or {})
    transport = config.get("transport", "http")
    if transport == "stdio":
        # Running a local command is effectively remote code execution by configuration.
        if not settings.ENABLE_MCP_STDIO:
            logger.warning("MCP stdio server %s skipped: ENABLE_MCP_STDIO is off", row.slug)
            return []
        conn = {"transport": "stdio", "command": config.get("command", ""), "args": list(config.get("args") or [])}
        if not conn["command"]:
            return []
    else:
        url = config.get("url", "")
        blocked = http_target_blocked(url)
        if blocked:
            logger.warning("MCP server %s skipped: %s", row.slug, blocked)
            return []
        headers = dict(config.get("headers") or {})
        secret = tool_secret(row.secret_encrypted)
        if secret and config.get("secret_header"):
            headers[str(config["secret_header"])] = f"{config.get('secret_prefix', '')}{secret}"
        conn = {"transport": config.get("transport", "streamable_http"), "url": url, "headers": headers or None}

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
        client = MultiServerMCPClient({row.slug: conn})
        discovered = await client.get_tools()
    except Exception as exc:
        logger.warning("MCP server %s unreachable: %s", row.slug, exc)
        return []

    out: list[BoundTool] = []
    for t in discovered:
        name = f"{row.slug}{MCP_PREFIX_SEP}{t.name}"[:64]
        t.name = name
        out.append(BoundTool(slug=name, tool=t, tool_id=row.id,
                             display_name=f"{row.name} · {t.name.split(MCP_PREFIX_SEP)[-1]}",
                             requires_approval=row.requires_approval, kind="mcp"))
    return out


def _mcp_payload(result: Any) -> Any:
    """MCP answers with content blocks ([{type: "text", text: "<json>"}]); a report node wants the
    data behind them, so unwrap to text and parse the JSON when there is one."""
    if isinstance(result, tuple) and result:          # (content, artifact) response format
        result = result[0]
    if isinstance(result, list):
        parts = []
        for block in result:
            if isinstance(block, dict):
                parts.append(str(block.get("text") or ""))
            elif isinstance(block, str):
                parts.append(block)
            else:
                parts.append(str(getattr(block, "text", block)))
        result = "\n".join(p for p in parts if p)
    if isinstance(result, str):
        try:
            return json.loads(result)
        except (ValueError, TypeError):
            return result
    return result


async def run_tool_by_id(db: AsyncSession, workspace_id, tool_id, args: dict[str, Any],
                          *, allow_approval_tools: bool = False, mcp_tool: str | None = None) -> Any:
    """Run one tool of this unit directly (no model in the loop) and return its parsed result.

    Used by the workflow ``tool_call`` node and by form prefill. Same policy as the agent: the
    tool must belong to the unit or be shared bank-wide, arguments are checked against its JSON
    Schema, the secret is injected server-side, and an approval-gated tool is refused because
    there is nobody to approve it. For an MCP row (one row = one server) ``mcp_tool`` picks which
    of the server's tools to call.
    """
    from uuid import UUID as _UUID

    if not tool_id:
        raise ToolError("Chưa chọn công cụ")
    if workspace_id is None:
        raise ToolError("Thiếu đơn vị nên không dùng được công cụ")
    try:
        tool_uuid = tool_id if isinstance(tool_id, _UUID) else _UUID(str(tool_id))
    except ValueError:
        raise ToolError("tool_id không hợp lệ")

    row = (await db.execute(select(Tool).where(
        Tool.id == tool_uuid, Tool.is_active.is_(True),
        or_(Tool.workspace_id == workspace_id, Tool.share_scope == "bank"),
    ))).scalar_one_or_none()
    if not row:
        raise ToolError("Công cụ không tồn tại, đã tắt, hoặc không thuộc đơn vị này")
    if row.requires_approval and not allow_approval_tools:
        raise ToolError(f"Công cụ '{row.name}' cần người duyệt nên không chạy tự động được")

    if row.kind == "builtin":
        entry = get_builtin((row.config or {}).get("fn", ""))
        if not entry:
            raise ToolError("Công cụ dựng sẵn không tồn tại")
        fn, schema = entry
        _validate_args(schema, args)
        try:
            return fn(**args)
        except (ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
            raise ToolError(str(exc))
    if row.kind == "http":
        _validate_args(dict(row.params_schema or {}), args)
        text = await execute_http(dict(row.config or {}), args,
                                  secret=tool_secret(row.secret_encrypted), timeout_sec=row.timeout_sec)
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            return text
    if row.kind == "mcp":
        discovered = await _mcp_tools(row)
        if not discovered:
            raise ToolError(f"Không kết nối được MCP server '{row.name}'")
        names = [b.slug.split(MCP_PREFIX_SEP)[-1] for b in discovered]
        if not mcp_tool:
            raise ToolError(f"Chưa chọn công cụ của MCP server '{row.name}'. Có: {', '.join(names)}")
        wanted = str(mcp_tool).split(MCP_PREFIX_SEP)[-1]
        bound = next((b for b in discovered if b.slug.split(MCP_PREFIX_SEP)[-1] == wanted), None)
        if not bound:
            raise ToolError(f"MCP server '{row.name}' không có công cụ '{wanted}'. Có: {', '.join(names)}")
        try:
            return _mcp_payload(await bound.tool.ainvoke(args))
        except Exception as exc:
            raise ToolError(f"MCP '{wanted}' lỗi: {type(exc).__name__}: {exc}")
    raise ToolError(f"Loại công cụ '{row.kind}' chưa gọi trực tiếp được")


async def build_bound_tools(db: AsyncSession, app: App, *, channel: str,
                            actor_employee_id=None, actor_user_id=None, run_id=None,
                            ops_ctx=None, skill_sink: list | None = None) -> list[BoundTool]:
    """Every callable this assistant may use on this channel, ready for the agent.

    ``actor_*`` is who is chatting: a file-producing tool stores its output under that person, so a
    report or export a staff member asked for shows up in their own "Báo cáo của tôi" and nobody
    else's; ``run_id`` links the file to the chat run in the audit log.

    ``skill_sink`` collects the skills the model activated, so the router can emit the chip and
    the audit log can record which playbook shaped the answer.

    ``ops_ctx`` is the ``OpsActor`` of an admin talking to the Trợ lý Vận hành. It adds that
    assistant's built-in read-only tools, already scoped to what this admin may see. It is never
    passed by the staff, customer, embed or extension channels, so a business assistant cannot
    reach them even if someone tries to bind them.
    """
    bound: list[BoundTool] = []
    # Kỹ năng: mức 2 của nạp dần. Mô hình thấy danh mục trong system prompt và gọi công cụ này khi
    # câu hỏi thật sự khớp, nên toàn văn bí kíp chỉ vào ngữ cảnh lúc cần.
    skill_rows = await _app_skill_rows(db, app, channel=channel)
    if skill_rows:
        from app.services.tools.skill_tool import activate_skill_tool

        tool, holder = activate_skill_tool(skill_rows, skill_sink)
        bound.append(BoundTool(slug="kich_hoat_ky_nang", tool=tool, tool_id=None,
                               display_name="Kích hoạt kỹ năng", requires_approval=False, kind="skill"))
        holder["bound"] = True
    if ops_ctx is not None:
        from app.services.tools.ops_tools import ops_tools

        for tool in ops_tools(ops_ctx, workflow_gen_enabled=getattr(ops_ctx, "workflow_gen", True)):
            bound.append(BoundTool(slug=tool.name, tool=tool, tool_id=None, display_name=tool.name,
                                   requires_approval=False, kind="ops"))
    for row in await app_tool_rows(db, app, channel=channel):
        if not SLUG_RE.match(row.slug or ""):
            logger.warning("tool %s has an invalid slug, skipped", row.id)
            continue
        if row.kind == "builtin":
            entry = get_builtin((row.config or {}).get("fn", ""))
            if not entry:
                continue
            fn, schema = entry
            bound.append(BoundTool(slug=row.slug, tool=_structured(row, schema, _builtin_callable(row, fn, schema)),
                                   tool_id=row.id, display_name=row.name,
                                   requires_approval=row.requires_approval, kind="builtin"))
        elif row.kind == "http":
            schema = dict(row.params_schema or {})
            bound.append(BoundTool(slug=row.slug, tool=_structured(row, schema, _http_callable(row)),
                                   tool_id=row.id, display_name=row.name,
                                   requires_approval=row.requires_approval, kind="http"))
        elif row.kind == "mcp":
            bound.extend(await _mcp_tools(row))
        elif row.kind == "report":
            from app.models.workflow import Workflow

            wf_id = (row.config or {}).get("workflow_id")
            wf = await db.get(Workflow, uuid.UUID(str(wf_id))) if wf_id else None
            if wf is None or wf.workspace_id != app.workspace_id:
                logger.warning("report tool %s points at a missing workflow", row.slug)
                continue
            schema = report_args_schema(wf)
            callable_, holder = _report_callable(row, wf.id, channel, actor_employee_id, actor_user_id)
            holder["schema"] = schema
            description = row.description or f"Chạy báo cáo '{wf.name}' và trả về tệp kết quả."
            row_for_tool = row
            row_for_tool.description = description
            bound.append(BoundTool(slug=row.slug, tool=_structured(row_for_tool, schema, callable_),
                                   tool_id=row.id, display_name=row.name,
                                   requires_approval=row.requires_approval, kind="report"))
        elif row.kind == "export":
            from app.services.tools.export import DEFAULT_DESCRIPTION, export_args_schema, export_callable

            schema = export_args_schema()
            callable_, holder = export_callable(
                row, workspace_id=app.workspace_id, channel=channel, run_id=run_id,
                actor_employee_id=actor_employee_id, actor_user_id=actor_user_id)
            holder["schema"] = schema
            row.description = row.description or DEFAULT_DESCRIPTION
            bound.append(BoundTool(slug=row.slug, tool=_structured(row, schema, callable_),
                                   tool_id=row.id, display_name=row.name,
                                   requires_approval=row.requires_approval, kind="export"))
    return bound

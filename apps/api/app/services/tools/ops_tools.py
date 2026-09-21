"""Công cụ của Trợ lý Vận hành: soạn luồng xử lý và tra trạng thái hệ thống.

Khác với công cụ trong sổ đăng ký, những công cụ này **không phải một dòng trong bảng `tools`**.
Chúng gắn cứng vào trợ lý hệ thống và chỉ được dựng khi `build_bound_tools` nhận `ops_ctx`, nên
không có cách nào gắn nhầm vào một trợ lý nghiệp vụ.

Hai nguyên tắc xuyên suốt:

* **Chỉ đọc.** Không công cụ nào ở đây ghi gì vào hệ thống. Công cụ soạn luồng chỉ trả về một bản
  nháp đã kiểm; người dùng bấm nút thì luồng mới được tạo, bằng chính quyền của họ. AI đề xuất,
  người chốt.
* **Phân quyền đi theo người hỏi, không đi theo trợ lý.** Trợ lý vận hành nằm ở đơn vị "Hệ thống",
  nhưng dữ liệu nó đọc được luôn lọc theo `OpsActor` của người đang chat. Nếu không, nó thành
  đường vòng để quản trị đơn vị này đọc dữ liệu đơn vị khác.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session_factory
from app.models.dataset import Dataset
from app.models.document import Document, DocumentStatus
from app.models.ai_provider import AiProvider
from app.models.run import Run
from app.models.tool import Tool
from app.models.usage import TokenUsage
from app.models.workflow import Workflow
from app.models.workspace import Workspace
from app.services.ops import OpsActor, audit_scope, scope_workspaces
from app.services.tools.executor import ToolError, as_untrusted_block
from app.services.workflow_gen import graph_to_steps, steps_to_graph
from app.services.workflow_schema import NODE_SPECS
from app.services.workflow_validator import ValidationError

logger = logging.getLogger(__name__)

MAX_ROWS = 20


# ---------------------------------------------------------------------------
# Lược đồ tham số
# ---------------------------------------------------------------------------

def _step_schema() -> dict:
    """Lược đồ một bước. Cố ý nông: mô hình liệt kê bước, máy chủ mới dựng đồ thị."""
    return {
        "type": "object",
        "properties": {
            "loai": {"type": "string", "enum": [t for t in NODE_SPECS if t not in ("input", "output")],
                     "description": "Loại node của bước này"},
            "nhan": {"type": "string", "description": "Nhãn tiếng Việt ngắn hiện trên canvas"},
        },
        "required": ["loai"],
        "additionalProperties": True,
    }


def draft_workflow_schema() -> dict:
    step = _step_schema()
    branch = {"type": "array", "items": step,
              "description": "Danh sách bước của nhánh này, phải có ít nhất một bước"}
    nested = dict(step)
    nested["properties"] = {**step["properties"], "neu_dung": branch, "neu_sai": branch}
    return {
        "type": "object",
        "properties": {
            "ten": {"type": "string", "description": "Tên luồng, tiếng Việt, ngắn gọn"},
            "mo_ta": {"type": "string", "description": "Một câu mô tả luồng làm gì"},
            "buoc": {"type": "array", "items": nested, "minItems": 1,
                     "description": "Các bước theo thứ tự chạy. KHÔNG cần bước input và output, "
                                    "máy chủ tự thêm. Bước rẽ nhánh phải có neu_dung và neu_sai, "
                                    "mỗi nhánh ít nhất một bước."},
            "workflow_id": {"type": "string",
                            "description": "Chỉ điền khi đang SỬA một luồng đã có, lấy id từ khối ngữ cảnh"},
        },
        "required": ["buoc"],
    }


READ_WORKFLOW_SCHEMA = {
    "type": "object",
    "properties": {"workflow_id": {"type": "string", "description": "Id luồng cần đọc, lấy từ khối ngữ cảnh"}},
    "required": ["workflow_id"],
}

EMPTY_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}

DAYS_SCHEMA = {
    "type": "object",
    "properties": {"so_ngay": {"type": "integer", "description": "Số ngày nhìn lại, mặc định 7", "minimum": 1,
                               "maximum": 90}},
}


# ---------------------------------------------------------------------------
# Tiện ích
# ---------------------------------------------------------------------------

def _scoped(stmt, column, scope: list[uuid.UUID] | None):
    """Giới hạn truy vấn theo phạm vi. `None` là không giới hạn, danh sách rỗng là không thấy gì."""
    if scope is None:
        return stmt
    if not scope:
        return stmt.where(column.is_(None))
    return stmt.where(column.in_(scope))


async def _unit_names(db: AsyncSession) -> dict[uuid.UUID, str]:
    return dict((await db.execute(select(Workspace.id, Workspace.name))).all())


def _block(slug: str, payload: Any) -> str:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, default=str)
    return as_untrusted_block(slug, text)


# ---------------------------------------------------------------------------
# Công cụ: soạn luồng xử lý
# ---------------------------------------------------------------------------

def _draft_workflow(actor: OpsActor):
    async def run(**kwargs: Any) -> str:
        spec = dict(kwargs)
        async with async_session_factory() as db:
            scope = scope_workspaces(actor)
            if scope is not None and not scope:
                raise ToolError("Người dùng chưa thuộc đơn vị nào nên chưa soạn luồng được.")
            target_ws = actor.active_workspace_id or (scope[0] if scope else None)
            if target_ws is None:
                raise ToolError("Chưa xác định được đơn vị để tạo luồng. Hãy hỏi người dùng đang "
                                "làm việc ở đơn vị nào.")

            ds_ids = {str(r) for r in (await db.execute(_scoped(
                select(Dataset.id), Dataset.workspace_id, [target_ws]))).scalars().all()}
            tool_ids = {str(r) for r in (await db.execute(_scoped(
                select(Tool.id), Tool.workspace_id, [target_ws]))).scalars().all()}

            try:
                graph = steps_to_graph(spec, dataset_ids=ds_ids, tool_ids=tool_ids)
            except ValidationError as exc:
                # Trả lỗi cho mô hình sửa chứ không ném ra ngoài: vòng lặp gọi công cụ của agent
                # chính là vòng sửa lỗi, mô hình gọi lại công cụ với bản đã sửa.
                raise ToolError(f"Bản nháp chưa hợp lệ: {exc} — hãy sửa đúng chỗ đó rồi gọi lại công cụ.")

            name = str(spec.get("ten") or "").strip() or "Luồng nháp"
            existing_id = str(spec.get("workflow_id") or "").strip()
            existing_name = None
            if existing_id:
                try:
                    wf = await db.get(Workflow, uuid.UUID(existing_id))
                except (ValueError, TypeError):
                    wf = None
                if wf is None or not actor.may_configure(wf.workspace_id):
                    raise ToolError("Không tìm thấy luồng cần sửa trong phạm vi của người dùng.")
                existing_name = wf.name
                target_ws = wf.workspace_id

            draft = {
                "ten": name,
                "mo_ta": str(spec.get("mo_ta") or "").strip(),
                "workspace_id": str(target_ws),
                "workflow_id": existing_id or None,
                "workflow_name": existing_name,
                "graph_json": graph,
            }
            actor.drafts.append(draft)

            summary = {
                "trang_thai": "Bản nháp đã kiểm hợp lệ và đang hiện cho người dùng xem trước.",
                "ten": name,
                "so_node": len(graph["nodes"]),
                "cac_buoc": [n["data"].get("label") or n["type"] for n in graph["nodes"]],
                "luu_y": "KHÔNG có gì được lưu. Người dùng phải tự bấm nút tạo luồng. "
                         "Hãy nói ngắn gọn luồng làm gì và mời họ bấm nút bên dưới.",
            }
            return _block("soan_luong_xu_ly", summary)

    return run


def _read_workflow(actor: OpsActor):
    async def run(**kwargs: Any) -> str:
        raw = str(kwargs.get("workflow_id") or "").strip()
        try:
            wf_id = uuid.UUID(raw)
        except (ValueError, TypeError):
            raise ToolError("workflow_id không hợp lệ.")
        async with async_session_factory() as db:
            wf = await db.get(Workflow, wf_id)
            if wf is None or not actor.may_configure(wf.workspace_id):
                raise ToolError("Không tìm thấy luồng này trong phạm vi của người dùng.")
            steps = graph_to_steps(wf.graph_json or {})
            payload = {"ten": wf.name, "loai": wf.type, "mo_ta": wf.description, **steps}
            if steps.get("khong_day_du"):
                payload["canh_bao"] = ("Đồ thị này có chỗ không biểu diễn được bằng danh sách bước. "
                                       "Chỉ sửa những bước thấy ở đây và nói rõ với người dùng.")
            return _block("doc_luong_xu_ly", payload)

    return run


# ---------------------------------------------------------------------------
# Công cụ: trạng thái hệ thống, chỉ đọc
# ---------------------------------------------------------------------------

def _failed_documents(actor: OpsActor):
    async def run(**kwargs: Any) -> str:
        scope = audit_scope(actor)
        async with async_session_factory() as db:
            names = await _unit_names(db)
            stmt = (select(Document, Dataset.name, Dataset.workspace_id)
                    .join(Dataset, Document.dataset_id == Dataset.id)
                    .where(Document.status == DocumentStatus.failed)
                    .order_by(Document.updated_at.desc()).limit(MAX_ROWS))
            rows = (await db.execute(_scoped(stmt, Dataset.workspace_id, scope))).all()
            items = [{
                "van_ban": doc.filename,
                "kho": ds_name,
                "don_vi": names.get(ws_id, "?"),
                "loi": (doc.error_message or "")[:300] or "không ghi lý do",
            } for doc, ds_name, ws_id in rows]
            if not items:
                return _block("van_ban_loi", {
                    "so_luong": 0, "ket_luan": "Không có văn bản nào đang ở trạng thái lỗi."})
            return _block("van_ban_loi", {
                "so_luong": len(items), "danh_sach": items,
                "goi_y": "Lập chỉ mục lại từng văn bản sau khi đã xử lý nguyên nhân."})

    return run


def _failed_runs(actor: OpsActor):
    async def run(**kwargs: Any) -> str:
        days = int(kwargs.get("so_ngay") or 7)
        since = datetime.now(timezone.utc) - timedelta(days=days)
        scope = audit_scope(actor)
        async with async_session_factory() as db:
            names = await _unit_names(db)
            stmt = (select(Run).where(Run.started_at >= since, Run.status.in_(("failed", "blocked")))
                    .order_by(Run.started_at.desc()).limit(MAX_ROWS))
            rows = (await db.execute(_scoped(stmt, Run.workspace_id, scope))).scalars().all()
            items = [{
                "thoi_diem": r.started_at.isoformat(timespec="minutes") if r.started_at else None,
                "kenh": r.channel, "trang_thai": r.status,
                "don_vi": names.get(r.workspace_id, "?"),
                "cau_hoi": (r.query_preview or "")[:120],
                "loi": (r.error or "")[:200],
            } for r in rows]
            return _block("luot_hoi_loi", {
                "so_ngay": days, "so_luong": len(items), "danh_sach": items})

    return run


def _background_status(actor: OpsActor):
    async def run(**kwargs: Any) -> str:
        out: dict[str, Any] = {}
        async with async_session_factory() as db:
            providers = (await db.execute(select(AiProvider).where(
                AiProvider.is_active.is_(True)))).scalars().all()
            out["nha_cung_cap_dang_bat"] = [
                {"muc_dich": p.purpose, "nha_cung_cap": p.provider_name, "model": p.model_name}
                for p in providers] or "KHÔNG có nhà cung cấp nào đang bật, mọi câu trả lời sẽ lỗi."

            scope = audit_scope(actor)
            stmt = (select(Document.status, func.count()).join(Dataset, Document.dataset_id == Dataset.id)
                    .group_by(Document.status))
            rows = (await db.execute(_scoped(stmt, Dataset.workspace_id, scope))).all()
            out["van_ban_theo_trang_thai"] = {
                str(getattr(st, "value", st)): n for st, n in rows}

        try:
            from app.deps import get_redis

            redis = await get_redis()
            beat = await redis.get("scheduler:heartbeat")
            out["bo_lap_lich"] = ("đang chạy" if beat else
                                 "KHÔNG thấy nhịp tim, lịch chạy sẽ không nổ. Kiểm tra tiến trình scheduler.")
        except Exception as exc:  # Redis hỏng không được làm hỏng câu trả lời
            logger.warning("ops: không đọc được nhịp tim bộ lập lịch: %s", exc)
            out["bo_lap_lich"] = "không kiểm tra được"
        return _block("trang_thai_nen", out)

    return run


def _token_usage(actor: OpsActor):
    async def run(**kwargs: Any) -> str:
        days = int(kwargs.get("so_ngay") or 30)
        since = datetime.now(timezone.utc) - timedelta(days=days)
        scope = audit_scope(actor)
        async with async_session_factory() as db:
            stmt = (select(TokenUsage.component, func.sum(TokenUsage.total_tokens), func.sum(TokenUsage.calls))
                    .where(TokenUsage.created_at >= since).group_by(TokenUsage.component))
            rows = (await db.execute(_scoped(stmt, TokenUsage.workspace_id, scope))).all()
            by_component = {c: {"token": int(t or 0), "luot_goi": int(n or 0)} for c, t, n in rows}
            return _block("token_ky_nay", {
                "so_ngay": days,
                "tong_token": sum(v["token"] for v in by_component.values()),
                "theo_thanh_phan": by_component or "chưa có lượt gọi nào trong khoảng này",
            })

    return run


# ---------------------------------------------------------------------------
# Lắp vào agent
# ---------------------------------------------------------------------------

def _tool(slug: str, description: str, schema: dict, coroutine) -> StructuredTool:
    return StructuredTool(name=slug, description=description, args_schema=schema,
                          coroutine=coroutine, func=None, handle_tool_error=True)


def ops_tools(actor: OpsActor, *, workflow_gen_enabled: bool = True) -> list[BaseTool]:
    """Công cụ cho trợ lý vận hành, đã gắn sẵn phạm vi của người đang hỏi."""
    tools: list[BaseTool] = [
        _tool("trang_thai_he_thong",
              "Tra trạng thái nền: nhà cung cấp AI đang bật, số văn bản theo trạng thái lập chỉ mục, "
              "bộ lập lịch còn chạy không. Dùng khi người dùng hỏi hệ thống có ổn không.",
              EMPTY_SCHEMA, _background_status(actor)),
        _tool("van_ban_loi",
              "Liệt kê các văn bản đang ở trạng thái lập chỉ mục lỗi kèm lý do. "
              "Dùng khi người dùng hỏi vì sao văn bản chưa dùng được.",
              EMPTY_SCHEMA, _failed_documents(actor)),
        _tool("luot_hoi_loi",
              "Liệt kê các lượt hỏi gần đây bị lỗi hoặc bị bộ lọc chặn. "
              "Dùng khi người dùng hỏi có gì hỏng không.",
              DAYS_SCHEMA, _failed_runs(actor)),
        _tool("token_da_dung",
              "Tổng token đã dùng theo thành phần trong N ngày gần đây. "
              "Dùng khi người dùng hỏi về chi phí.",
              DAYS_SCHEMA, _token_usage(actor)),
    ]
    if workflow_gen_enabled:
        tools.extend([
            _tool("doc_luong_xu_ly",
                  "Đọc một luồng xử lý đang có và trả về dưới dạng danh sách bước. "
                  "Gọi công cụ này TRƯỚC khi sửa một luồng, để biết nó đang làm gì.",
                  READ_WORKFLOW_SCHEMA, _read_workflow(actor)),
            _tool("soan_luong_xu_ly",
                  "Soạn một luồng xử lý từ danh sách bước và hiện bản xem trước cho người dùng. "
                  "Máy chủ tự thêm bước đầu và bước cuối, tự nối cạnh và tự đặt toạ độ, nên chỉ cần "
                  "liệt kê các bước nghiệp vụ theo thứ tự. Công cụ trả về lỗi nếu bản nháp sai; "
                  "khi đó hãy sửa đúng chỗ báo lỗi rồi gọi lại. Công cụ này KHÔNG lưu gì cả.",
                  draft_workflow_schema(), _draft_workflow(actor)),
        ])
    return tools


__all__ = ["ops_tools", "draft_workflow_schema"]

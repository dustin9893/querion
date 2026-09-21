"""Business forms: validate what staff typed, prefill from a tool, draft free text, export .docx.

The privacy rule lives here: fields flagged ``pii`` (customer name, CCCD, account number) go
from the tool or the employee's keyboard straight into the document and are never put in a
prompt. That is the whole reason a form is a form and not a chat — ``mask_pii`` would redact
exactly the values the document needs.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.form_template import FormTemplate

logger = logging.getLogger(__name__)

FIELD_TYPES = ("string", "text", "number", "date", "select", "boolean")
FIELD_SOURCES = ("user", "tool", "llm")
MAX_FIELDS = 40


class FormError(Exception):
    """Bad form definition or bad values — the message is shown to the admin or the employee."""


# ---------------------------------------------------------------------------
# Definition + values
# ---------------------------------------------------------------------------

def validate_fields(fields: list[dict]) -> list[dict]:
    if not isinstance(fields, list):
        raise FormError("fields phải là danh sách")
    if len(fields) > MAX_FIELDS:
        raise FormError(f"Tối đa {MAX_FIELDS} trường")
    seen: set[str] = set()
    out: list[dict] = []
    for raw in fields:
        if not isinstance(raw, dict):
            raise FormError("Mỗi trường phải là object")
        name = str(raw.get("name") or "").strip()
        if not name.isidentifier():
            raise FormError(f"Tên trường '{name}' không hợp lệ (chỉ chữ, số, gạch dưới, không bắt đầu bằng số)")
        if name in seen:
            raise FormError(f"Trường '{name}' bị trùng")
        seen.add(name)
        ftype = raw.get("type") or "string"
        source = raw.get("source") or "user"
        if ftype not in FIELD_TYPES:
            raise FormError(f"Kiểu trường '{ftype}' không hợp lệ")
        if source not in FIELD_SOURCES:
            raise FormError(f"Nguồn dữ liệu '{source}' không hợp lệ")
        out.append({
            "name": name, "label": str(raw.get("label") or name), "type": ftype, "source": source,
            "required": bool(raw.get("required")), "pii": bool(raw.get("pii")),
            "default": raw.get("default", ""), "options": [str(o) for o in (raw.get("options") or [])],
            "description": str(raw.get("description") or ""),
            "llm_prompt": str(raw.get("llm_prompt") or ""),
        })
    return out


def coerce_values(fields: list[dict], values: dict[str, Any]) -> dict[str, Any]:
    """Check what the employee submitted and convert types; raises on a missing required field."""
    out: dict[str, Any] = {}
    for field in fields:
        name = field["name"]
        value = values.get(name, field.get("default"))
        label = field.get("label") or name
        if value in (None, ""):
            if field.get("required"):
                raise FormError(f"Thiếu thông tin bắt buộc: {label}")
            out[name] = ""
            continue
        ftype = field.get("type") or "string"
        if ftype == "number":
            try:
                out[name] = float(str(value).replace(",", "."))
            except (TypeError, ValueError):
                raise FormError(f"'{label}' phải là số")
        elif ftype == "boolean":
            out[name] = value if isinstance(value, bool) else str(value).lower() in ("true", "1", "yes", "có")
        elif ftype == "select":
            options = field.get("options") or []
            if options and str(value) not in options:
                raise FormError(f"'{label}' phải là một trong: {', '.join(options)}")
            out[name] = str(value)
        else:
            out[name] = str(value)
    return out


def non_sensitive(fields: list[dict], values: dict[str, Any]) -> dict[str, Any]:
    """The subset of values a model may see: everything except fields flagged ``pii``."""
    pii = {f["name"] for f in fields if f.get("pii")}
    return {k: v for k, v in values.items() if k not in pii and v not in (None, "")}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

async def visible_forms(db: AsyncSession, workspace_id, *, published_only: bool = False) -> list[FormTemplate]:
    """Forms a unit may use: its own, plus the ones another unit opened bank-wide."""
    cond = [or_(FormTemplate.workspace_id == workspace_id, FormTemplate.share_scope == "bank")]
    if published_only:
        cond.append(FormTemplate.is_published.is_(True))
    rows = await db.execute(select(FormTemplate).where(*cond).order_by(FormTemplate.name))
    return list(rows.scalars().all())


def dig(data: Any, path: str) -> Any:
    """Read 'ho_so.khach_hang' (or 'items.0.name') out of a tool result."""
    current = data
    for part in str(path or "").split("."):
        if part == "":
            continue
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current


async def prefill_values(db: AsyncSession, form: FormTemplate, key: str) -> dict[str, Any]:
    """Call the form's prefill tool with one business code and map the result into field values."""
    from app.services.tools.executor import ToolError
    from app.services.tools.registry import run_tool_by_id

    if not form.prefill_tool_id or not form.prefill_arg:
        raise FormError("Biểu mẫu này chưa cấu hình điền sẵn")
    try:
        result = await run_tool_by_id(db, form.workspace_id, form.prefill_tool_id, {form.prefill_arg: key})
    except ToolError as exc:
        raise FormError(str(exc))

    names = {f["name"] for f in (form.fields or [])}
    values: dict[str, Any] = {}
    for field_name, path in (form.prefill_mapping or {}).items():
        if field_name not in names:
            continue
        picked = dig(result, str(path))
        if picked is not None:
            values[field_name] = picked
    return values


async def suggest_text(db: AsyncSession, form: FormTemplate, field: dict, values: dict[str, Any],
                       *, usage=None) -> str:
    """Draft one free-text field. Only non-PII values reach the model."""
    from app.services.chat import get_active_llm_provider
    from app.services.encryption import decrypt_key
    from app.services.usage import TokenMeter, record_usage
    from app.services.workflow_runtime import _call_llm

    provider = await get_active_llm_provider(db)
    if not provider:
        raise FormError("Chưa cấu hình mô hình ngôn ngữ (LLM)")

    safe = non_sensitive(form.fields or [], values)
    context = "\n".join(f"- {k}: {v}" for k, v in safe.items()) or "(chưa có dữ liệu)"
    instruction = field.get("llm_prompt") or f"Soạn nội dung cho mục '{field.get('label') or field['name']}'."
    messages = [
        {"role": "system", "content":
            "Bạn soạn thảo nội dung cho biểu mẫu nghiệp vụ ngân hàng bằng tiếng Việt, văn phong hành chính, "
            "ngắn gọn 2–5 câu. Chỉ dùng dữ liệu được cung cấp; KHÔNG bịa số liệu, KHÔNG nêu tên khách hàng, "
            "số CCCD hay số tài khoản; không kết luận thay cấp phê duyệt. Chỉ trả về nội dung, không thêm lời dẫn."},
        {"role": "user", "content": f"Biểu mẫu: {form.name}\nYêu cầu: {instruction}\n\nThông tin đã có:\n{context}"},
    ]
    meter = TokenMeter()
    text = await _call_llm(
        provider_name=provider.provider_name, api_key=decrypt_key(provider.api_key_encrypted),
        model=provider.model_name, messages=messages, temperature=0.3, max_tokens=500,
        base_url=provider.base_url, meter=meter,
    )
    await record_usage(usage, component="form_suggest", purpose="llm", provider=provider, meter=meter,
                       prompt_text=context + instruction, completion_text=text)
    return (text or "").strip()

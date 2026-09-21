"""Công cụ xuất tệp dùng chung: mô hình dựng bảng từ nội dung hội thoại rồi trả về .xlsx.

Khác với công cụ loại ``report`` (chạy một luồng báo cáo đã dựng sẵn, số liệu lấy từ hệ thống),
công cụ này **không thuộc loại báo cáo nào**: cán bộ hỏi gì, tra được gì trong hội thoại thì bảo
trợ lý "xuất Excel" và mô hình tự khai báo sheet / cột / dòng từ đúng ngữ cảnh đó. Vì dữ liệu do
mô hình điền nên ở đây chỉ có định dạng và giới hạn, không có truy vấn nào cả.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

MAX_SHEETS = 5
MAX_COLUMNS = 30
MAX_ROWS = 2000            # đây là bảng trong hội thoại, không phải kho dữ liệu
MAX_TEXT_LEN = 2000

# Tên định dạng cột mà mô hình thấy → định dạng ô của render_xlsx
COLUMN_FORMATS = {
    "chu": "",
    "tien": "money",
    "so": "number",
    "so_nguyen": "int",
    "phan_tram": "percent",
}

_NUMERIC = {"tien", "so", "so_nguyen", "phan_tram"}

# Loại biểu đồ mô hình thấy → loại của render_xlsx
CHART_KINDS = {"cot": "bar", "cot_ngang": "bar_h", "duong": "line", "tron": "pie"}
_NUM_RE = re.compile(r"^-?\d+(?:\.\d{3})*(?:,\d+)?$|^-?\d+(?:,\d{3})*(?:\.\d+)?$|^-?\d+(?:[.,]\d+)?$")


def export_args_schema() -> dict:
    """JSON Schema mô hình phải điền — chính là bảng nó muốn xuất."""
    column = {
        "type": "object",
        "properties": {
            "nhan": {"type": "string", "description": "Tiêu đề cột hiển thị trong Excel, vd 'Chi nhánh'."},
            "khoa": {"type": "string", "description": "Tên trường tương ứng trong mỗi phần tử của 'dong', vd 'chi_nhanh'."},
            "dinh_dang": {
                "type": "string",
                "enum": list(COLUMN_FORMATS),
                "description": "chu = chữ, tien = số tiền VND, so = số thập phân, so_nguyen = số nguyên, "
                               "phan_tram = tỷ lệ (ghi dạng thập phân: 0.952 nghĩa là 95,2%).",
            },
            "tong": {"type": "boolean", "description": "true nếu muốn cộng tổng cột này ở dòng cuối bảng."},
        },
        "required": ["nhan", "khoa"],
    }
    sheet = {
        "type": "object",
        "properties": {
            "ten": {"type": "string", "description": "Tên sheet, tối đa 31 ký tự."},
            "tieu_de": {"type": "string", "description": "Tiêu đề in ở đầu sheet (tuỳ chọn)."},
            "cot": {"type": "array", "minItems": 1, "maxItems": MAX_COLUMNS, "items": column},
            "dong": {
                "type": "array",
                "maxItems": MAX_ROWS,
                "description": "Dữ liệu thật của bảng. Mỗi phần tử là một object dùng đúng các 'khoa' đã khai báo ở 'cot'.",
                "items": {"type": ["object", "array"]},
            },
            "tom_tat": {
                "type": "array",
                "description": "Các dòng tóm tắt đặt phía trên bảng, mỗi dòng là cặp [nhãn, giá trị].",
                "items": {"type": "array"},
            },
            "bieu_do": {
                "type": "object",
                "description": "Tuỳ chọn: một biểu đồ vẽ ngay trong sheet từ chính bảng này. Dùng khi người "
                               "hỏi muốn biểu đồ hoặc khi bảng so sánh các nhóm/kỳ với nhau.",
                "properties": {
                    "loai": {"type": "string", "enum": list(CHART_KINDS),
                             "description": "cot = cột đứng, cot_ngang = cột ngang, duong = đường, tron = tròn."},
                    "tieu_de": {"type": "string"},
                    "truc_nhan": {"type": "string", "description": "'khoa' của cột chữ dùng làm nhãn (vd chi_nhanh)."},
                    "chuoi": {"type": "array", "maxItems": 4, "items": {"type": "string"},
                              "description": "Các 'khoa' của cột số cần vẽ, biểu đồ tròn chỉ lấy cột đầu."},
                },
                "required": ["loai", "truc_nhan", "chuoi"],
            },
        },
        "required": ["ten", "cot", "dong"],
    }
    return {
        "type": "object",
        "properties": {
            "ten_tep": {"type": "string", "description": "Tên tệp, không kèm đuôi, vd 'ho-so-qua-han-09-2026'."},
            "tieu_de": {"type": "string", "description": "Tiêu đề in ở đầu tệp."},
            "sheets": {"type": "array", "minItems": 1, "maxItems": MAX_SHEETS, "items": sheet},
        },
        "required": ["sheets"],
    }


DEFAULT_DESCRIPTION = (
    "Xuất dữ liệu đang có trong hội thoại ra tệp Excel (.xlsx) để cán bộ tải về. Tự khai báo bảng: "
    "mỗi sheet gồm danh sách cột (nhãn + khoá) và danh sách dòng dữ liệu thật lấy từ những gì vừa "
    "trao đổi hoặc vừa tra được. Dùng khi người hỏi muốn 'xuất Excel', 'tải về bảng', 'lập file' cho "
    "nội dung hiện có. Có thể kèm một biểu đồ (cột, đường, tròn) vẽ ngay trong sheet qua trường "
    "'bieu_do'. Đây KHÔNG phải công cụ tra cứu: không tự bịa số liệu, chỉ đưa vào bảng những "
    "dữ liệu đã có trong hội thoại."
)


def _to_number(value: Any) -> Any:
    """'1.234.567' / '95,2' / '12 000' → số, nếu không phải số thì trả lại nguyên văn."""
    if isinstance(value, bool) or isinstance(value, (int, float)) or value is None:
        return value
    text = str(value).strip().replace(" ", "").replace(" ", "")
    for suffix in ("đ", "VND", "vnd", "%"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    if not text or not _NUM_RE.match(text):
        return value
    if "," in text and "." in text:
        # kiểu Việt Nam '1.234.567,89' vs kiểu Anh '1,234,567.89'
        text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") \
            else text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".") if len(text.split(",")[-1]) != 3 else text.replace(",", "")
    elif text.count(".") > 1 or (("." in text) and len(text.split(".")[-1]) == 3):
        text = text.replace(".", "")
    try:
        number = float(text)
    except ValueError:
        return value
    return int(number) if number.is_integer() else number


def _cell(value: Any, fmt: str) -> Any:
    """Ép kiểu ô theo định dạng cột; chuỗi dài bị cắt để một ô không nuốt cả tài liệu."""
    if fmt in _NUMERIC:
        value = _to_number(value)
        if fmt == "phan_tram" and isinstance(value, (int, float)) and not isinstance(value, bool):
            # mô hình hay ghi 95.2 thay vì 0.952; định dạng ô là phần trăm nên quy về thập phân
            if abs(value) > 1.5:
                value = round(value / 100, 6)
    if isinstance(value, (dict, list)):
        return str(value)[:MAX_TEXT_LEN]
    if isinstance(value, str):
        return value[:MAX_TEXT_LEN]
    return value


def _summary_value(value: Any) -> Any:
    """Số trong dòng tóm tắt vào ô số để Excel tính được; '08/2026' hay '87,2%' giữ nguyên chữ
    vì bỏ dấu % đi thì con số đọc sai."""
    if isinstance(value, str) and value.strip().endswith("%"):
        return value.strip()[:MAX_TEXT_LEN]
    return _cell(value, "so")


def build_sheets(args: dict) -> tuple[list[dict], str, str, int]:
    """(sheets cho render_xlsx, tiêu đề, tên tệp gốc, tổng số dòng)."""
    from app.services.reports import ReportError

    sheets_in = args.get("sheets") or []
    if not isinstance(sheets_in, list) or not sheets_in:
        raise ReportError("Chưa khai báo sheet nào để xuất")
    title = str(args.get("tieu_de") or "").strip()
    sheets: list[dict] = []
    total_rows = 0

    for index, sheet in enumerate(sheets_in[:MAX_SHEETS], start=1):
        if not isinstance(sheet, dict):
            raise ReportError("Mỗi sheet phải là một object")
        columns_in = [c for c in (sheet.get("cot") or []) if isinstance(c, dict)][:MAX_COLUMNS]
        if not columns_in:
            raise ReportError(f"Sheet '{sheet.get('ten') or index}' chưa khai báo cột nào")

        keys, columns = [], []
        for position, column in enumerate(columns_in):
            key = str(column.get("khoa") or column.get("nhan") or f"cot_{position + 1}").strip()
            keys.append(key)
            columns.append({
                "header": str(column.get("nhan") or key)[:120],
                "field": key,
                "format": COLUMN_FORMATS.get(str(column.get("dinh_dang") or "chu"), ""),
                "total": bool(column.get("tong")),
            })

        formats = [str(c.get("dinh_dang") or "chu") for c in columns_in]
        rows = []
        for row in (sheet.get("dong") or [])[:MAX_ROWS]:
            if isinstance(row, (list, tuple)):        # mô hình trả mảng theo thứ tự cột
                row = {keys[i]: v for i, v in enumerate(row) if i < len(keys)}
            if not isinstance(row, dict):
                continue
            rows.append({key: _cell(row.get(key), formats[i]) for i, key in enumerate(keys)})
        total_rows += len(rows)

        # a summary value that reads as a number goes in as a number, so Excel can total it;
        # "08/2026" and the like stay text because they do not parse
        summary = []
        for line in (sheet.get("tom_tat") or [])[:20]:
            if isinstance(line, (list, tuple)) and line:
                summary.append([str(line[0])[:200], _summary_value(line[1]) if len(line) > 1 else ""])
            elif isinstance(line, dict) and line:
                for label, value in list(line.items())[:2]:
                    summary.append([str(label)[:200], _summary_value(value)])

        charts = []
        chart = sheet.get("bieu_do")
        if isinstance(chart, dict) and chart.get("truc_nhan") and chart.get("chuoi"):
            charts.append({
                "type": CHART_KINDS.get(str(chart.get("loai") or "cot"), "bar"),
                "title": str(chart.get("tieu_de") or sheet.get("tieu_de") or "")[:120],
                "category_field": str(chart["truc_nhan"]),
                "series": [str(k) for k in chart["chuoi"] if isinstance(k, str)][:4],
            })

        sheets.append({
            "name": str(sheet.get("ten") or f"Sheet{index}")[:31],
            "title": str(sheet.get("tieu_de") or (title if index == 1 else ""))[:200] or None,
            "columns": columns,
            "rows": rows,
            "summary": summary,
            "charts": charts,
        })

    if not any(s["rows"] for s in sheets):
        raise ReportError("Bảng không có dòng dữ liệu nào để xuất")
    # the title is what the download chip says, so fall back to the sheet name before a generic one
    name = str(args.get("ten_tep") or title or sheets[0]["name"] or "bang-du-lieu")
    return sheets, (title or sheets[0]["title"] or sheets[0]["name"] or "Bảng dữ liệu"), name, total_rows


def export_callable(row, *, workspace_id, channel: str, run_id=None,
                    actor_employee_id=None, actor_user_id=None):
    """Callable của công cụ: dựng .xlsx từ tham số mô hình điền, lưu thành artifact, trả về tệp."""
    slug, schema_holder = row.slug, {}

    async def run(**kwargs: Any) -> str:
        import json

        from app.db import async_session_factory
        from app.services.reports import (
            XLSX_MIME, ReportError, build_context, render_xlsx, safe_filename, store_artifact,
        )
        from app.services.tools.executor import ToolError, as_untrusted_block, attach_artifacts
        from app.services.tools.registry import _validate_args

        _validate_args(schema_holder.get("schema") or export_args_schema(), kwargs)
        try:
            sheets, title, name, total_rows = build_sheets(kwargs)
            data = render_xlsx(sheets, build_context({}), title=title)
        except ReportError as exc:
            raise ToolError(f"Không xuất được tệp: {exc}")
        except Exception as exc:  # openpyxl is strict about titles and cell types
            logger.exception("export tool %s could not build the workbook", slug)
            raise ToolError(f"Không dựng được tệp Excel ({type(exc).__name__}). "
                            "Hãy đặt tên sheet ngắn, không dấu / \\ * ? : [ ] và gửi lại dữ liệu dạng bảng phẳng.")

        filename = safe_filename(name, "xlsx")
        async with async_session_factory() as db:
            artifact = await store_artifact(
                db, workspace_id=workspace_id, data=data, filename=filename,
                content_type=XLSX_MIME, title=title, kind="export",
                audience=("staff" if actor_employee_id else "admin"),
                run_id=run_id, created_by_employee_id=actor_employee_id,
                created_by_user_id=actor_user_id,
            )
            await db.commit()
            file = {"id": str(artifact.id), "filename": artifact.filename, "title": artifact.title,
                    "content_type": artifact.content_type, "size": artifact.size}

        logger.info("export tool %s wrote %s (%d dòng, kênh %s)", slug, filename, total_rows, channel)
        payload = {
            "da_tao_tep": filename,
            "tieu_de": title,
            "so_sheet": len(sheets),
            "so_dong": total_rows,
            "ghi_chu": "Tệp đã sẵn sàng, người dùng bấm nút tải ngay dưới câu trả lời. "
                       "Chỉ cần xác nhận ngắn gọn, không cần chép lại bảng.",
        }
        return attach_artifacts(as_untrusted_block(slug, json.dumps(payload, ensure_ascii=False)), [file])

    return run, schema_holder

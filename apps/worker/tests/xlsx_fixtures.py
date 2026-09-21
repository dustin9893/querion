"""Dựng bảng tính .xlsx ngay trong test — không commit tệp nhị phân nào.

openpyxl không GHI được hai dạng mà Excel ghi: ô công thức có giá trị tính đã lưu, và một
nhóm cột ẩn lưu một lần dưới dạng <col min="3" max="5" hidden="1"/>. `patch_xml` sửa trực
tiếp một phần tử XML trong tệp zip để tạo đúng hai dạng đó.

Run: apps/api/.venv/Scripts/python.exe -m pytest apps/worker/tests -q
(từ gốc repo)
"""

import io
import zipfile
from pathlib import Path

from openpyxl import Workbook

from worker.pipeline.spreadsheet import SheetLines

SHEET1 = "xl/worksheets/sheet1.xml"


def to_bytes(wb: Workbook) -> bytes:
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def to_path(wb: Workbook, tmp_path: Path, name: str = "bang.xlsx") -> str:
    path = tmp_path / name
    path.write_bytes(to_bytes(wb))
    return str(path)


def patch_xml(data: bytes | str | Path, member: str, fn) -> bytes:
    """Return the workbook bytes with one zip member rewritten as ``fn(xml_text)``."""
    if not isinstance(data, bytes):
        data = Path(data).read_bytes()
    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            body = src.read(info.filename)
            if info.filename == member:
                body = fn(body.decode("utf-8")).encode("utf-8")
            dst.writestr(info, body)
    return out.getvalue()


def all_cell_values(wb: Workbook) -> list[str]:
    """Every non-empty value of the visible sheets, as text (tests use plain strings)."""
    return [
        str(value)
        for ws in wb.worksheets
        if ws.sheet_state == "visible"
        for row in ws.iter_rows(values_only=True)
        for value in row
        if value not in (None, "")
    ]


def emitted_text(sheets: list[SheetLines]) -> str:
    """Everything the reader emitted (titles and lines), as one searchable string."""
    parts: list[str] = []
    for sheet in sheets:
        parts.append(sheet.title)
        parts.extend(text for _, text, _ in sheet.lines)
    return "\n".join(parts)


def assert_no_loss(wb: Workbook, sheets: list[SheetLines]) -> None:
    """Every visible non-empty cell shows up as a column name, a title or a value."""
    text = emitted_text(sheets)
    missing = [v for v in all_cell_values(wb) if v not in text]
    assert not missing, f"lost cell values: {missing}"

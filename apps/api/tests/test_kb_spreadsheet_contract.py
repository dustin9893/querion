"""Hợp đồng giữa định dạng đoạn (chunk) của worker cho bảng tính và phần API dùng đoạn đó.

Sự cố mà test này canh giữ: `sanitize_chunk` của guard xoá mọi đoạn "<...>" (coi là thẻ
HTML) trước khi đưa tài liệu vào prompt. Một biểu phí có hai ô cạnh nhau "<5 triệu" và
">0,02%" nên dòng "Mức: <5 triệu; Tỷ lệ: >0,02%" bị cắt thành "Mức: 0,02%" — hai giá trị
biến mất mà không có lỗi nào. Worker vì thế đổi < > thành dấu toàn chiều ＜ ＞.

Test chạy trên các hàm THẬT của cả hai bên:
- worker đọc và chia bảng tính thành đoạn;
- `_section_of` của retrieval phải đọc lại đúng mục "Sheet …" mà worker ghi vào đoạn;
- `sanitize_chunk` không được làm mất giá trị ô nào, nhưng vẫn vô hiệu hoá ảnh markdown
  như với mọi tài liệu khác.

Worker là một gói riêng: chỉ trong tệp này apps/worker được thêm vào sys.path, và
worker.pipeline.spreadsheet phải import được chỉ với thư viện chuẩn + openpyxl.

Run: cd apps/api && pytest tests/test_kb_spreadsheet_contract.py -v
"""

import io
import sys
from pathlib import Path

import pytest
from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "worker"))

from worker.pipeline.spreadsheet import chunk_sheets, read_sheets

from app.services.guard import sanitize_chunk
from app.services.retrieval import _section_of

MD_IMAGE = "![x](http://evil.example/a.png)"

# Values as they must survive the guard: comparison signs in their fullwidth form.
EXPECTED_VALUES = [
    "Biểu phí chuyển tiền 2026",
    "Nhóm",
    "Mức",
    "Tỷ lệ",
    "Ghi chú",
    "Cá nhân",
    "＜5 triệu",
    "＞0,02%",
    "Miễn phí",
    "Tổ chức",
    "Theo hợp đồng",
]


def _fee_workbook() -> io.BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "Biểu phí"
    ws["A1"] = "Biểu phí chuyển tiền 2026"
    ws.merge_cells("A1:D1")
    ws.append(["Nhóm", "Mức", "Tỷ lệ", "Ghi chú"])
    ws.append(["Cá nhân", "<5 triệu", ">0,02%", MD_IMAGE])
    ws.append([None, "Từ 5 triệu", "Miễn phí", "Áp dụng 2026"])
    ws.merge_cells("A3:A4")
    ws.append(["Tổ chức", "Mọi mức", "Theo hợp đồng", "Liên hệ chi nhánh"])
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return out


@pytest.fixture
def chunks():
    return chunk_sheets(read_sheets(_fee_workbook()))


def test_the_workbook_produces_chunks(chunks):
    assert chunks


def test_retrieval_reads_back_the_section_the_worker_wrote(chunks):
    for chunk in chunks:
        assert _section_of(chunk.content) == chunk.section
        assert chunk.section.startswith("Sheet ")


@pytest.mark.parametrize("value", EXPECTED_VALUES)
def test_every_cell_value_survives_the_guard(chunks, value):
    sanitized = "\n".join(sanitize_chunk(c.content) for c in chunks)
    assert value in sanitized


def test_the_guard_still_neutralises_a_markdown_image_in_a_cell(chunks):
    sanitized = "\n".join(sanitize_chunk(c.content) for c in chunks)
    assert "evil.example" not in sanitized
    assert "[hình ảnh đã bỏ]" in sanitized


def test_ascii_comparison_signs_lose_a_value_in_the_guard():
    # Negative control: why the worker swaps < > for fullwidth signs.
    sanitized = sanitize_chunk("Mức: <5 triệu; Tỷ lệ: >0,02%")
    assert "5 triệu" not in sanitized
    assert sanitized == "Mức: 0,02%"

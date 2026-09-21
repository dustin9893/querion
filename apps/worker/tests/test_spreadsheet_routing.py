"""Kiểm thử rẽ nhánh bảng tính trong `build_chunks`.

Sự cố mà các test này canh giữ:
- Tệp .xlsx được khai content type "text/plain" (hoặc sai loại) mà rơi vào đường văn bản thì
  nội dung zip nhị phân ("PK…") bị lập chỉ mục thành rác. Rẽ nhánh theo ĐUÔI tệp, không theo
  content type, vì API nhận tệp theo đuôi và bộ tải giữ nguyên đuôi.
- Thêm đường bảng tính không được làm đổi đường văn bản (TXT/PDF/DOCX).

Run: apps/api/.venv/Scripts/python.exe -m pytest apps/worker/tests -q
(từ gốc repo)
"""

import pytest
from openpyxl import Workbook

from tests.test_chunker_golden import INPUT
from tests.xlsx_fixtures import to_path
from worker.pipeline.chunker import chunk_text
from worker.pipeline.parser import parse
from worker.pipeline.route import build_chunks
from worker.pipeline.spreadsheet import EMPTY_MSG, is_spreadsheet


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("a.xlsx", True),
        ("A.XLSX", True),
        ("dir.v2/b.xlsx", True),
        ("a.xls", False),
        ("a.xlsm", False),
        ("a.csv", False),
        ("a.txt", False),
        ("a.docx", False),
        ("xlsx", False),
    ],
)
def test_is_spreadsheet_matches_the_xlsx_extension_only(path, expected):
    assert is_spreadsheet(path) is expected


def test_xlsx_declared_as_text_is_still_read_as_a_spreadsheet(tmp_path):
    wb = Workbook()
    wb.active.append(["Mã", "Dịch vụ", "Mức phí"])
    wb.active.append(["P01", "Chuyển tiền", "11000"])
    path = to_path(wb, tmp_path)

    chunks = build_chunks(path, "text/plain")

    assert chunks[0].content.startswith("[Sheet ")
    assert "Mã: P01 | Dịch vụ: Chuyển tiền | Mức phí: 11000" in chunks[0].content
    assert not any("PK" in c.content for c in chunks)


def test_txt_path_is_unchanged(tmp_path):
    path = tmp_path / "quy_trinh.txt"
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(INPUT)

    assert build_chunks(str(path), "text/plain") == chunk_text(parse(str(path), "text/plain"))


def test_empty_workbook_fails_with_the_empty_message(tmp_path):
    path = to_path(Workbook(), tmp_path)

    with pytest.raises(ValueError) as exc:
        build_chunks(path, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    assert str(exc.value) == EMPTY_MSG

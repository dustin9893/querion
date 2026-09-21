"""Chốt những loại tệp mà kho tri thức chấp nhận khi tải lên.

Phần mở rộng được so không phân biệt hoa thường và chỉ lấy đoạn sau dấu chấm cuối cùng;
tệp không có phần mở rộng hoặc thuộc loại ngoài danh sách bị từ chối bằng lỗi 400 rõ ràng.

Run: cd apps/api && pytest tests/test_kb_upload_check.py -v
"""

import pytest
from fastapi import HTTPException

from app.routers.documents import _upload_extension


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("a.txt", ".txt"),
        ("A.PDF", ".pdf"),  # upper case is folded
        ("bao.cao.v2.docx", ".docx"),  # only the part after the last dot counts
        ("a.xlsx", ".xlsx"),
        ("A.XLSX", ".xlsx"),
        ("bao.cao.v2.xlsx", ".xlsx"),
    ],
)
def test_a_supported_file_is_accepted(filename, expected):
    assert _upload_extension(filename) == expected


@pytest.mark.parametrize(
    "filename",
    [
        "a.exe",
        "noext",
        None,  # the browser sent no name: treated as "unnamed"
        "archive.tar.gz",
        ".xls",  # legacy binary Excel: openpyxl cannot read it
        ".xlsm",  # macro-enabled workbook
        ".csv",
        "filexlsx",  # no dot: no extension at all
        "a.xlsx.bak",  # only the part after the last dot counts
    ],
)
def test_an_unsupported_file_is_a_clear_400(filename):
    with pytest.raises(HTTPException) as err:
        _upload_extension(filename)
    assert err.value.status_code == 400
    assert "Unsupported file type" in err.value.detail
    # Sorted, so the message is the same on every run (a set has no stable order).
    assert "Allowed: .docx, .pdf, .txt, .xlsx" in err.value.detail

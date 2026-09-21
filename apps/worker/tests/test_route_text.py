"""Kiểm thử `build_chunks` trên đường văn bản (TXT).

`build_chunks` gom bước 3-4 của `index_document` (đọc tệp → cắt đoạn) vào một hàm để sắp
thêm đường bảng tính. Các test này ghim rằng với tệp văn bản kết quả y hệt
`chunk_text(parse(...))`, và các thông báo lỗi (lưu vào documents.error_message, hiện cho
người dùng) giữ nguyên từng byte.

Run: apps/api/.venv/Scripts/python.exe -m pytest apps/worker/tests -q
(từ gốc repo)
"""

import pytest

from tests.test_chunker_golden import INPUT
from worker.pipeline.chunker import chunk_text
from worker.pipeline.parser import parse
from worker.pipeline.route import build_chunks


def _write(tmp_path, name: str, content: str) -> str:
    path = tmp_path / name
    # newline="" để giữ nguyên "\r\n" trong INPUT.
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    return str(path)


def test_build_chunks_txt_matches_parse_then_chunk(tmp_path):
    path = _write(tmp_path, "quy_trinh.txt", INPUT)

    chunks = build_chunks(path, "text/plain")

    assert chunks
    assert chunks == chunk_text(parse(path, "text/plain"))


@pytest.mark.parametrize("content", ["", " \r\n\t\n  "], ids=["empty", "whitespace"])
def test_build_chunks_rejects_txt_without_text(tmp_path, content):
    path = _write(tmp_path, "rong.txt", content)

    with pytest.raises(ValueError, match=r"^No text content extracted from document$"):
        build_chunks(path, "text/plain")


def test_build_chunks_rejects_heading_only_txt(tmp_path):
    # Chỉ có một dòng tiêu đề, không có thân → chunk_text không tạo chunk nào.
    path = _write(tmp_path, "tieu_de.txt", "Điều 1. Phạm vi")

    with pytest.raises(ValueError, match=r"^No chunks created from text$"):
        build_chunks(path, "text/plain")


def test_build_chunks_rejects_unsupported_file(tmp_path):
    path = tmp_path / "x.bin"
    path.write_bytes(b"\x00\x01\x02")

    with pytest.raises(ValueError, match="Unsupported content type"):
        build_chunks(str(path), "application/octet-stream")

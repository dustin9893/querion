"""Kiểm thử đặc tả cho `parse` — bộ tách văn bản của đường PDF/DOCX/TXT cũ.

Ghim hành vi hiện tại trước khi thêm đường bảng tính vào worker. Đặc biệt `parse` phải tiếp
tục từ chối tệp .xlsx: bảng tính phải được rẽ nhánh TRƯỚC khi gọi `parse`, không phải bên trong.

Run: apps/api/.venv/Scripts/python.exe -m pytest apps/worker/tests -q
(từ gốc repo; chạy riêng với apps/api/tests vì cả hai gói đều tên là `tests`)
"""

import pytest

from worker.pipeline.parser import parse

VI_TEXT = "Điều 1. Phạm vi áp dụng\nQuy trình cho vay áp dụng cho khách hàng cá nhân.\n"


def _minimal_pdf(text: str) -> bytes:
    """Một PDF một trang tối thiểu, chữ ASCII bằng Helvetica, bảng xref đúng offset."""
    stream = f"BT /F1 24 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for num, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % num + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref_at)
    return bytes(out)


def test_txt_returns_exact_text(tmp_path):
    path = tmp_path / "quy_trinh.txt"
    path.write_bytes(VI_TEXT.encode("utf-8"))

    assert parse(str(path), "text/plain") == VI_TEXT


def test_txt_by_extension_with_octet_stream(tmp_path):
    path = tmp_path / "quy_trinh.txt"
    path.write_bytes(VI_TEXT.encode("utf-8"))

    assert parse(str(path), "application/octet-stream") == VI_TEXT


def test_docx_joins_non_empty_paragraphs(tmp_path):
    docx = pytest.importorskip("docx")
    path = tmp_path / "huong_dan.docx"
    doc = docx.Document()
    doc.add_paragraph("Điều 2. Hồ sơ vay vốn")
    doc.add_paragraph("")
    doc.add_paragraph("Khách hàng nộp giấy đề nghị vay vốn tại quầy.")
    doc.save(str(path))

    result = parse(str(path), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    assert result == "Điều 2. Hồ sơ vay vốn\n\nKhách hàng nộp giấy đề nghị vay vốn tại quầy."


def test_pdf_extracts_text(tmp_path):
    pytest.importorskip("pdfplumber")
    path = tmp_path / "quy_dinh.pdf"
    path.write_bytes(_minimal_pdf("PDFTAG-7421"))

    assert "PDFTAG-7421" in parse(str(path), "application/pdf")


def test_xlsx_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Unsupported content type"):
        parse(str(tmp_path / "x.xlsx"), "application/octet-stream")

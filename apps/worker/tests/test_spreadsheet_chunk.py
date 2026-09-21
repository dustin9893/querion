"""Kiểm thử `chunk_sheets` — xếp các dòng bảng tính vào đoạn để embed và trích dẫn.

Sự cố mà các test này canh giữ:
- Một dòng bảng bị cắt đôi giữa hai đoạn (như cửa sổ cố định của `chunk_text`) thì nửa sau
  mất mã dòng và tên cột; câu trả lời trích sai phí.
- Tiền tố "[Sheet … › dòng a–b]" không khớp regex `_section_of` của retrieval.py (tên sheet
  chứa "]", quá dài, xuống dòng) thì trích dẫn mất nhãn; khoảng dòng sai thì chỉ nhầm chỗ.
- Đoạn nằm dưới một dải mục ("II. CHUYỂN TIỀN QUỐC TẾ") mất ngữ cảnh mục khi sang đoạn sau.
- Bảng tính khổng lồ sinh hàng chục nghìn đoạn, làm nghẽn bước embed.

Run: apps/api/.venv/Scripts/python.exe -m pytest apps/worker/tests -q
(từ gốc repo)
"""

import re

import pytest

from worker.pipeline import spreadsheet
from worker.pipeline.chunker import CHUNK_SIZE
from worker.pipeline.spreadsheet import PAIR_SEP, SheetLines, chunk_sheets

# Copied verbatim from apps/api/app/services/retrieval.py:125 (_SECTION_RE), which turns the
# chunk prefix back into the citation label.
SECTION_RE = re.compile(r"^\[([^\]]{1,160})\]\s")
ROWS_RE = re.compile(r"› dòng (\d+)(?:–(\d+))?$")


def _row_line(i: int) -> str:
    return f"Mã: ROW-{i:04d} | Dịch vụ: Dịch vụ số {i} | Mức phí: {i * 1000} | Ghi chú: áp dụng toàn hệ thống"


def _table(n: int = 200, name: str = "Biểu phí", title: str = "BIỂU PHÍ 2026") -> SheetLines:
    # Excel rows 5, 7, 9, ... so a wrong row range cannot pass by accident.
    return SheetLines(name=name, title=title, lines=[(5 + 2 * i, _row_line(i), False) for i in range(1, n + 1)])


def _body_lines(content: str) -> list[str]:
    return content.split("\n")


def _row_range(section: str) -> tuple[int, int]:
    first, last = ROWS_RE.search(section).groups()
    return int(first), int(last or first)


def test_every_row_lands_intact_in_exactly_one_chunk_in_order():
    sheet = _table()

    chunks = chunk_sheets([sheet])

    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert len(chunks) > 1
    assert all(len(c.content) <= CHUNK_SIZE + 50 for c in chunks)
    seen = [line for c in chunks for line in _body_lines(c.content) if "ROW-" in line]
    assert seen == [text for _, text, _ in sheet.lines]


def test_every_chunk_prefix_matches_the_citation_regex_and_row_range():
    sheet = _table()
    row_of = {text: row for row, text, _ in sheet.lines}

    chunks = chunk_sheets([sheet])

    for chunk in chunks:
        m = SECTION_RE.match(chunk.content)
        assert m and m.group(1) == chunk.section
        rows = [row_of[line] for line in _body_lines(chunk.content) if line in row_of]
        assert _row_range(chunk.section) == (rows[0], rows[-1])


def test_chunk_head_is_the_sheet_title():
    chunk = chunk_sheets([_table(n=2)])[0]

    assert chunk.content == f"[Sheet Biểu phí › dòng 7–9] BIỂU PHÍ 2026\n{_row_line(1)}\n{_row_line(2)}"
    assert chunk.section == "Sheet Biểu phí › dòng 7–9"


def test_single_row_chunk_names_one_row_and_no_title_means_no_head():
    chunk = chunk_sheets([SheetLines(name="S", title="", lines=[(4, "a: b", False)])])[0]

    assert chunk.content == "[Sheet S › dòng 4] a: b"


def test_over_long_row_is_split_with_its_first_pair_repeated():
    long_pairs = [f"Cột {c:02d}: " + f"{c:02d}" * 60 for c in range(40)]
    long_line = PAIR_SEP.join(["Mã: LONG-01", *long_pairs])
    sheet = SheetLines(
        name="Rộng",
        title="",
        lines=[(2, "Mã: BEFORE | x: 1", False), (3, long_line, False), (4, "Mã: AFTER | x: 2", False)],
    )

    chunks = chunk_sheets([sheet])

    lines = [line for c in chunks for line in _body_lines(SECTION_RE.sub("", c.content))]
    pieces = [line for line in lines if "LONG-01" in line]
    assert len(pieces) > 1
    assert all(piece.startswith("Mã: LONG-01 | Cột ") for piece in pieces)
    assert all(len(c.content) <= CHUNK_SIZE for c in chunks)
    assert all(_row_range(c.section)[0] <= 3 <= _row_range(c.section)[1] for c in chunks if "LONG-01" in c.content)
    assert lines[0] == "Mã: BEFORE | x: 1" and lines[-1] == "Mã: AFTER | x: 2"
    joined = "\n".join(pieces)
    assert all(pair in joined for pair in long_pairs)


def test_single_over_long_pair_is_cut_hard():
    line = "Mã: X1 | Mô tả: " + "y" * 3000
    chunks = chunk_sheets([SheetLines(name="S", title="", lines=[(2, line, False)])])

    assert len(chunks) > 1
    assert all(len(c.content) <= CHUNK_SIZE for c in chunks)
    assert all(c.content.startswith("[Sheet S › dòng 2] Mã: X1 | ") for c in chunks)
    assert sum(c.content.count("y") for c in chunks) == 3000


@pytest.mark.parametrize(
    "name",
    ["a]b[c", "x" * 200, "tab\tnew\nline", "Doanh số 08-2026 (2)", "Phí 💳 thẻ", "   "],
    ids=["brackets", "very-long", "whitespace", "parentheses", "emoji", "blank"],
)
def test_odd_sheet_names_still_give_a_valid_section(name):
    chunks = chunk_sheets([SheetLines(name=name, title="", lines=[(1, "a: b", False), (2, "c: d", False)])])

    for chunk in chunks:
        m = SECTION_RE.match(chunk.content)
        assert m and m.group(1) == chunk.section
        assert "]" not in chunk.section and "\n" not in chunk.section
        assert len(chunk.section) <= 160


def test_chunks_never_mix_sheets_and_indexes_continue():
    a, b = _table(n=60, name="Một"), _table(n=60, name="Hai")

    chunks = chunk_sheets([a, b])

    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    names = [c.section.split(" › ")[0] for c in chunks]
    assert names == sorted(names, key=["Sheet Một", "Sheet Hai"].index)
    assert set(names) == {"Sheet Một", "Sheet Hai"}


def test_chunk_starting_after_a_band_row_carries_that_label():
    band = "II. CHUYỂN TIỀN QUỐC TẾ"
    lines = [(3, "I. TRONG NƯỚC", True), (4, _row_line(0), False), (5, band, True)]
    lines += [(6 + i, _row_line(i), False) for i in range(1, 60)]
    sheet = SheetLines(name="Phí", title="BIỂU PHÍ", lines=lines)

    chunks = chunk_sheets([sheet])

    first, later = chunks[0], chunks[1:]
    # The first chunk holds both bands itself, so its head is just the title.
    assert first.content.split("\n")[0].endswith("] BIỂU PHÍ")
    assert band in first.content.split("\n")
    assert later
    assert all(c.content.split("\n")[0].endswith(f"] BIỂU PHÍ › {band}") for c in later)


def test_too_many_chunks_fails_with_the_limit_in_the_message(monkeypatch):
    monkeypatch.setattr(spreadsheet, "MAX_CHUNKS", 3)

    with pytest.raises(ValueError, match=r"^Bảng tính tạo ra \d+ đoạn, vượt giới hạn 3 đoạn cho một tài liệu\."):
        chunk_sheets([_table()])


def test_no_sheets_gives_no_chunks():
    assert chunk_sheets([]) == []

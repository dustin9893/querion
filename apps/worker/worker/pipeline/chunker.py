"""Split text into overlapping chunks, aware of Vietnamese legal/procedural structure.

Bank documents (quy trình, quy định, hướng dẫn) are organised as
``Chương → Mục → Điều → 1. / 1.1``. We first cut the text at those headings
so a chunk never straddles two "Điều", then apply fixed-size windows inside
each section. Every chunk is prefixed with a breadcrumb such as
``[Điều 5. Điều kiện giải ngân]`` so both the retriever (embedding) and the
citation UI know exactly which clause the passage belongs to.
"""

import re
from dataclasses import dataclass

CHUNK_SIZE = 1000  # chars (MVP uses chars, upgrade to tokens later)
CHUNK_OVERLAP = 200  # chars

# Structural headings, ordered by level (lower = higher in the hierarchy).
_HEADING_PATTERNS: list[tuple[int, re.Pattern[str]]] = [
    (1, re.compile(r"^(PHẦN|Phần|CHƯƠNG|Chương)\s+[IVXLC\d]+\b.*$")),
    (2, re.compile(r"^(MỤC|Mục)\s+[IVXLC\d]+\b.*$")),
    (3, re.compile(r"^(ĐIỀU|Điều)\s+\d+[a-z]?\s*[\.:\-–]?.*$")),
    (4, re.compile(r"^(\d+)[\.\)]\s+\S.*$")),            # "1. Tiêu đề"
    (5, re.compile(r"^(\d+\.\d+(?:\.\d+)?)[\.\)]?\s+\S.*$")),  # "1.1 Tiêu đề" / "1.1.2. Tiêu đề"
]

_MAX_HEADING_LEN = 160
_MAX_NUMBERED_HEADING_LEN = 100
_BREADCRUMB_MAX = 110


@dataclass
class ChunkResult:
    chunk_index: int
    content: str
    section: str | None = None


def _heading_level(line: str) -> int | None:
    """Return the heading level of a line, or None if it is body text."""
    stripped = line.strip()
    if not stripped or len(stripped) > _MAX_HEADING_LEN:
        return None
    for level, pat in _HEADING_PATTERNS:
        if pat.match(stripped):
            # Numbered items that read like sentences (end with . ; : ,) are list
            # items, not headings — keep them inside the body.
            if level >= 4:
                if len(stripped) > _MAX_NUMBERED_HEADING_LEN or stripped[-1] in ".;:,":
                    return None
            return level
    return None


def _split_sections(text: str) -> list[tuple[str | None, str]]:
    """Split raw text into (breadcrumb, body) sections using structural headings."""
    stack: dict[int, str] = {}
    sections: list[tuple[str | None, str]] = []
    buf: list[str] = []

    def flush():
        body = "\n".join(buf).strip()
        if body:
            crumb = _breadcrumb(stack)
            sections.append((crumb, body))
        buf.clear()

    for raw in text.splitlines():
        level = _heading_level(raw)
        if level is None:
            buf.append(raw)
            continue
        flush()
        # a heading at level N invalidates deeper levels
        for deeper in [k for k in stack if k >= level]:
            del stack[deeper]
        stack[level] = raw.strip()
    flush()
    return sections


def _breadcrumb(stack: dict[int, str]) -> str | None:
    if not stack:
        return None
    # Keep the two most specific levels (e.g. "Điều 5. ... › 2. ...") to stay short.
    parts = [stack[k] for k in sorted(stack)][-2:]
    crumb = " › ".join(parts)
    if len(crumb) > _BREADCRUMB_MAX:
        crumb = crumb[: _BREADCRUMB_MAX - 1].rstrip() + "…"
    return crumb


def _window(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Fixed-size sliding windows over normalised text."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    out: list[str] = []
    start = 0
    step = max(chunk_size - overlap, 1)
    while start < len(text):
        piece = text[start : start + chunk_size].strip()
        if piece:
            out.append(piece)
        if start + chunk_size >= len(text):
            break
        start += step
    return out


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[ChunkResult]:
    """Split text into structure-aware, overlapping chunks.

    1. Cut at Chương / Mục / Điều / numbered headings
    2. Window each section into ``chunk_size`` chars with ``overlap``
    3. Prefix each chunk with ``[breadcrumb]`` when a heading is known
    """
    chunks: list[ChunkResult] = []
    idx = 0
    for crumb, body in _split_sections(text):
        prefix = f"[{crumb}] " if crumb else ""
        # leave room for the prefix so total stays ~chunk_size
        inner = max(chunk_size - len(prefix), 200)
        for piece in _window(body, inner, overlap):
            chunks.append(ChunkResult(chunk_index=idx, content=prefix + piece, section=crumb))
            idx += 1
    return chunks

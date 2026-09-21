"""Turn a downloaded document into chunks: pick the reader for the file, then cut.

.xlsx workbooks go to the spreadsheet reader (row-aware lines, never split mid-row);
everything else is parsed to text and cut by the prose chunker.
"""

from worker.pipeline.chunker import ChunkResult, chunk_text
from worker.pipeline.parser import parse
from worker.pipeline.spreadsheet import chunk_sheets, is_spreadsheet, read_sheets


def build_chunks(file_path: str, content_type: str) -> list[ChunkResult]:
    """Chunk a spreadsheet by rows, or parse the file and chunk its text.

    Raises ValueError (message stored in documents.error_message) when the file type is
    unsupported, no text was extracted, or the text yields no chunks; spreadsheets raise
    their own Vietnamese messages (see worker.pipeline.spreadsheet).
    """
    if is_spreadsheet(file_path):
        return chunk_sheets(read_sheets(file_path))

    text = parse(file_path, content_type)
    if not text.strip():
        raise ValueError("No text content extracted from document")

    chunks = chunk_text(text)
    if not chunks:
        raise ValueError("No chunks created from text")

    return chunks

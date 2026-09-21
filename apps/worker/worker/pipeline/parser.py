"""Extract text from PDF, DOCX, and TXT files."""

import os


def parse(file_path: str, content_type: str) -> str:
    """Extract text from a file based on its content type."""
    ext = os.path.splitext(file_path)[1].lower()

    if content_type == "text/plain" or ext == ".txt":
        return _parse_txt(file_path)
    elif content_type == "application/pdf" or ext == ".pdf":
        return _parse_pdf(file_path)
    elif ext == ".docx" or "wordprocessingml" in content_type:
        return _parse_docx(file_path)
    else:
        raise ValueError(f"Unsupported content type: {content_type} (ext: {ext})")


def _parse_txt(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _parse_pdf(file_path: str) -> str:
    import pdfplumber

    text_parts = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n\n".join(text_parts)


def _parse_docx(file_path: str) -> str:
    from docx import Document

    doc = Document(file_path)
    return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())

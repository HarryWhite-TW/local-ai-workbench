from __future__ import annotations

from pathlib import Path

from docx import Document as DocxDocument
from pypdf import PdfReader


def read_text_file(file_path: Path) -> str:
    return file_path.read_bytes().decode("utf-8", errors="replace")


def extract_pdf_text(file_path: Path) -> str:
    reader = PdfReader(str(file_path))
    page_texts: list[str] = []

    for page in reader.pages:
        text = page.extract_text() or ""
        normalized = text.strip()
        if normalized:
            page_texts.append(normalized)

    return "\n\n".join(page_texts)


def extract_docx_text(file_path: Path) -> str:
    document = DocxDocument(str(file_path))
    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    return "\n\n".join(paragraphs)


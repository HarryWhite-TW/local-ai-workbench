from __future__ import annotations

import re
from pathlib import Path

from docx import Document as DocxDocument
from pypdf import PdfReader

CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
INLINE_WHITESPACE_PATTERN = re.compile(r"[^\S\n]+")
EXCESS_BLANK_LINES_PATTERN = re.compile(r"\n{3,}")


def read_text_file(file_path: Path) -> str:
    return file_path.read_bytes().decode("utf-8", errors="replace")


def normalize_extracted_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = CONTROL_CHAR_PATTERN.sub("", normalized)
    normalized_lines = [INLINE_WHITESPACE_PATTERN.sub(" ", line).strip() for line in normalized.split("\n")]
    normalized = "\n".join(normalized_lines)
    normalized = EXCESS_BLANK_LINES_PATTERN.sub("\n\n", normalized)
    return normalized.strip()


def extract_pdf_text(file_path: Path) -> str:
    reader = PdfReader(str(file_path))
    page_texts: list[str] = []

    for page in reader.pages:
        text = page.extract_text() or ""
        normalized = normalize_extracted_text(text)
        if normalized:
            page_texts.append(normalized)

    return "\n\n".join(page_texts)


def extract_docx_text(file_path: Path) -> str:
    document = DocxDocument(str(file_path))
    paragraphs = [normalize_extracted_text(paragraph.text) for paragraph in document.paragraphs]
    return normalize_extracted_text("\n\n".join(paragraph for paragraph in paragraphs if paragraph))

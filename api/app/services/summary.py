from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from api.app.services.audit import create_audit_event
from api.app.services.documents import get_document

CODE_FENCE_PATTERNS = [
    re.compile(r"(?ms)^[ \t]*```.*?^[ \t]*```[ \t]*\n?"),
    re.compile(r"(?ms)^[ \t]*~~~.*?^[ \t]*~~~[ \t]*\n?"),
]
MARKDOWN_PREFIX_PATTERN = re.compile(r"(?m)^[ \t]*(#{1,6}|[-*+]|>|\d+\.)[ \t]*")
LINK_PATTERN = re.compile(r"\[([^\]]+)\]\([^)]+\)")
WHITESPACE_PATTERN = re.compile(r"\s+")
PARAGRAPH_SPLIT_PATTERN = re.compile(r"\n\s*\n+")
SENTENCE_PUNCTUATION_PATTERN = re.compile(r"[.!?。！？]")
SECTION_HEADING_PATTERN = re.compile(r"^(?:\d+(?:\.\d+)*)[.)、 ]")
HEADER_LIKE_MARKERS = (
    "file header",
    "檔案標籤區",
    "摘要區",
    "abstract",
)
HEADER_LIKE_PREFIXES = (
    "[卷名]：",
    "[主題]：",
    "[輸出模式]：",
    "[參照文件]：",
    "[版本]：",
    "[作者]：",
    "[狀態]：",
    "文件名稱：",
    "文件版本：",
    "所屬專案：",
    "卷別：",
    "覆蓋章節：",
    "文件層級：",
    "關聯文件：",
)
DOCX_OPENING_BLOCK_LIMIT = 3
DOCX_MIN_PARAGRAPH_COUNT = 4
DOCX_MIN_MEANINGFUL_CHARS = 100
BODY_BLOCK_MIN_MEANINGFUL_CHARS = 20
DEFAULT_PARAGRAPH_MIN_MEANINGFUL_CHARS = 12
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?。！？])\s+")


class SummaryArtifactNotFoundError(Exception):
    """Raised when a document does not have a stored summary artifact."""


def utc_now_precise() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def strip_code_fences(text: str) -> str:
    cleaned = text
    for pattern in CODE_FENCE_PATTERNS:
        cleaned = pattern.sub("\n", cleaned)
    return cleaned


def normalize_markdown_text(text: str) -> str:
    without_links = LINK_PATTERN.sub(r"\1", text)
    without_prefixes = MARKDOWN_PREFIX_PATTERN.sub("", without_links)
    return without_prefixes.strip()


def collapse_whitespace(text: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", text).strip()


def count_meaningful_chars(text: str) -> int:
    return len(re.sub(r"[\W_]+", "", text, flags=re.UNICODE))


def build_candidate_paragraphs(text: str) -> list[str]:
    paragraphs = []
    for paragraph in PARAGRAPH_SPLIT_PATTERN.split(text):
        collapsed = collapse_whitespace(normalize_markdown_text(paragraph))
        if collapsed:
            paragraphs.append(collapsed)
    return paragraphs


def is_header_like_paragraph(paragraph: str) -> bool:
    meaningful_chars = count_meaningful_chars(paragraph)
    lowered = paragraph.casefold()

    if any(marker in lowered for marker in HEADER_LIKE_MARKERS):
        return True

    if paragraph.startswith("[") or paragraph.startswith("【"):
        return True

    if any(paragraph.startswith(prefix) for prefix in HEADER_LIKE_PREFIXES):
        return True

    if SECTION_HEADING_PATTERN.match(paragraph) and meaningful_chars <= 60:
        return True

    if meaningful_chars <= 30 and not SENTENCE_PUNCTUATION_PATTERN.search(paragraph):
        return True

    return False


def build_opening_blocks(paragraphs: list[str]) -> list[tuple[str, bool]]:
    blocks: list[tuple[str, bool]] = []
    current_block: list[str] = []
    current_is_header_like: bool | None = None

    for paragraph in paragraphs:
        is_header_like = is_header_like_paragraph(paragraph)
        if current_is_header_like is None:
            current_block = [paragraph]
            current_is_header_like = is_header_like
            continue

        if current_is_header_like and is_header_like:
            current_block.append(paragraph)
            continue

        blocks.append((" ".join(current_block).strip(), current_is_header_like))
        current_block = [paragraph]
        current_is_header_like = is_header_like

    if current_block and current_is_header_like is not None:
        blocks.append((" ".join(current_block).strip(), current_is_header_like))

    return blocks


def is_large_structured_docx(paragraphs: list[str]) -> bool:
    if len(paragraphs) < DOCX_MIN_PARAGRAPH_COUNT:
        return False
    return sum(count_meaningful_chars(paragraph) for paragraph in paragraphs) >= DOCX_MIN_MEANINGFUL_CHARS


def select_docx_opening_body_block(paragraphs: list[str]) -> str:
    if not is_large_structured_docx(paragraphs):
        return ""

    opening_blocks = build_opening_blocks(paragraphs)[:DOCX_OPENING_BLOCK_LIMIT]
    for block_text, is_header_like in opening_blocks:
        if is_header_like:
            continue
        if count_meaningful_chars(block_text) >= BODY_BLOCK_MIN_MEANINGFUL_CHARS:
            return block_text

    return ""


def select_meaningful_paragraph(text: str, *, file_type: str | None = None) -> str:
    paragraphs = build_candidate_paragraphs(text)

    if file_type == "docx":
        opening_body_block = select_docx_opening_body_block(paragraphs)
        if opening_body_block:
            return opening_body_block

    for paragraph in paragraphs:
        if count_meaningful_chars(paragraph) >= DEFAULT_PARAGRAPH_MIN_MEANINGFUL_CHARS:
            return paragraph

    return paragraphs[0] if paragraphs else ""


def build_extractive_summary(content: str, *, file_type: str | None = None) -> str:
    without_code = strip_code_fences(content)
    paragraph = select_meaningful_paragraph(without_code, file_type=file_type)
    if not paragraph:
        return ""

    sentences = [sentence.strip() for sentence in SENTENCE_SPLIT_PATTERN.split(paragraph) if sentence.strip()]
    if not sentences:
        return paragraph

    return " ".join(sentences[:3]).strip()


def create_summary_artifact(connection: sqlite3.Connection, document_id: str) -> dict[str, str]:
    document = get_document(connection, document_id)
    timestamp = utc_now_precise()
    artifact_id = f"sum_{uuid4().hex}"
    summary_text = build_extractive_summary(document["content"], file_type=document["file_type"])

    connection.execute(
        """
        INSERT INTO summary_artifacts (
            id, document_id, method, source_content_hash, summary_text, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            artifact_id,
            document_id,
            "extractive_v1",
            document["content_hash"],
            summary_text,
            timestamp,
        ),
    )
    create_audit_event(
        connection,
        action_id=None,
        event_type="summary_generated",
        event_payload={
            "document_id": document_id,
            "artifact_id": artifact_id,
            "method": "extractive_v1",
            "source_content_hash": document["content_hash"],
        },
        created_at=timestamp,
    )
    return {
        "id": artifact_id,
        "document_id": document_id,
        "method": "extractive_v1",
        "source_content_hash": document["content_hash"],
        "summary_text": summary_text,
        "created_at": timestamp,
    }


def get_latest_summary_artifact(connection: sqlite3.Connection, document_id: str) -> dict[str, str]:
    get_document(connection, document_id)

    row = connection.execute(
        """
        SELECT id, document_id, method, source_content_hash, summary_text, created_at
        FROM summary_artifacts
        WHERE document_id = ?
        ORDER BY created_at DESC, rowid DESC
        LIMIT 1
        """,
        (document_id,),
    ).fetchone()

    if row is None:
        raise SummaryArtifactNotFoundError(document_id)

    return {
        "id": row["id"],
        "document_id": row["document_id"],
        "method": row["method"],
        "source_content_hash": row["source_content_hash"],
        "summary_text": row["summary_text"],
        "created_at": row["created_at"],
    }

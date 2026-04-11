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


def select_meaningful_paragraph(text: str) -> str:
    paragraphs = [normalize_markdown_text(paragraph) for paragraph in re.split(r"\n\s*\n+", text)]

    for paragraph in paragraphs:
        collapsed = WHITESPACE_PATTERN.sub(" ", paragraph).strip()
        meaningful_chars = re.sub(r"[\W_]+", "", collapsed, flags=re.UNICODE)
        if len(meaningful_chars) >= 12:
            return collapsed

    for paragraph in paragraphs:
        collapsed = WHITESPACE_PATTERN.sub(" ", paragraph).strip()
        if collapsed:
            return collapsed

    return ""


def build_extractive_summary(content: str) -> str:
    without_code = strip_code_fences(content)
    paragraph = select_meaningful_paragraph(without_code)
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
    summary_text = build_extractive_summary(document["content"])

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

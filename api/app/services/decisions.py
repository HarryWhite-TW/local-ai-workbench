from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from api.app.services.audit import create_audit_event
from api.app.services.documents import get_document

ALGORITHM_REVISION = "source_line_cues_r1"
DECISION_METHOD = "explicit_decision_v1"
MAX_DECISIONS = 20
MAX_DECISION_TEXT_LENGTH = 500

ATX_HEADING_PATTERN = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$")
FENCE_PATTERN = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
LIST_MARKER_PATTERN = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+(.+?)\s*$")
WHITESPACE_PATTERN = re.compile(r"\s+")
LABELED_DECISION_PATTERN = re.compile(
    r"^(?:decision|decided|approved|selected|chosen|決策|決定|決議|已決定|核准)"
    r"\s*(?::|：|-|—)\s*(.+)$",
    re.IGNORECASE,
)
ENGLISH_SENTENCE_PATTERN = re.compile(
    r"^(?:(?:we|the team|team|the project|project)\s+(?:have\s+|has\s+)?decided\s+(?:that\s+|to\s+)"
    r"|it\s+was\s+decided\s+that\s+|the\s+decision\s+is\s+(?:that\s+|to\s+))(.+)$",
    re.IGNORECASE,
)
CHINESE_SENTENCE_PATTERN = re.compile(r"^(?:(?:我們|團隊|本專案|專案)?\s*(?:已)?決定)\s*(.+)$")
NON_DECISION_PATTERN = re.compile(
    r"^(?:proposed\s+decision|proposal|recommendation|pending\s+decision|decision\s+pending|"
    r"no\s+decision|not\s+decided|undecided|tbd|to\s+be\s+decided|建議|提案|尚未決定|待決定)",
    re.IGNORECASE,
)
DECISION_SECTION_TITLES = {
    "decision",
    "decisions",
    "decision record",
    "decisions made",
    "決策",
    "決策事項",
    "決定事項",
    "決議",
}


class DecisionArtifactNotFoundError(Exception):
    """Raised when a document does not have a stored decision artifact."""


def utc_now_precise() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def normalize_inline_text(text: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", text).strip()


def normalize_heading(line: str) -> str | None:
    match = ATX_HEADING_PATTERN.match(line)
    heading = match.group(1) if match else line.strip().rstrip(":：")
    normalized = normalize_inline_text(heading).casefold()
    return normalized if normalized in DECISION_SECTION_TITLES else None


def strip_list_marker(line: str) -> tuple[str, bool]:
    match = LIST_MARKER_PATTERN.match(line)
    if match:
        return normalize_inline_text(match.group(1)), True
    return normalize_inline_text(line), False


def extract_cued_decision(candidate: str) -> str | None:
    if not candidate or NON_DECISION_PATTERN.match(candidate):
        return None

    for pattern in (LABELED_DECISION_PATTERN, ENGLISH_SENTENCE_PATTERN, CHINESE_SENTENCE_PATTERN):
        match = pattern.match(candidate)
        if match:
            decision_text = normalize_inline_text(match.group(1))
            if decision_text and not NON_DECISION_PATTERN.match(decision_text):
                return decision_text[:MAX_DECISION_TEXT_LENGTH]
    return None


def decision_fingerprint(text: str) -> str:
    return "".join(character for character in text.casefold() if character.isalnum())


def build_explicit_decisions(content: str) -> list[dict[str, Any]]:
    normalized_content = content.replace("\r\n", "\n").replace("\r", "\n")
    if normalized_content.startswith("\ufeff"):
        normalized_content = normalized_content[1:]

    decisions: list[dict[str, Any]] = []
    fingerprints: set[str] = set()
    inside_fence = False
    fence_character = ""
    fence_length = 0
    inside_decision_section = False
    section_prose_taken = False

    for line_number, raw_line in enumerate(normalized_content.split("\n"), start=1):
        fence_match = FENCE_PATTERN.match(raw_line)
        if fence_match:
            marker = fence_match.group(1)
            if not inside_fence:
                inside_fence = True
                fence_character = marker[0]
                fence_length = len(marker)
            elif marker[0] == fence_character and len(marker) >= fence_length:
                inside_fence = False
                fence_character = ""
                fence_length = 0
            continue
        if inside_fence:
            continue

        atx_heading = ATX_HEADING_PATTERN.match(raw_line)
        if atx_heading:
            inside_decision_section = normalize_heading(raw_line) is not None
            section_prose_taken = False
            continue

        if normalize_heading(raw_line) is not None:
            inside_decision_section = True
            section_prose_taken = False
            continue

        candidate, is_list_item = strip_list_marker(raw_line)
        if not candidate:
            continue

        decision_text = extract_cued_decision(candidate)
        if decision_text is None and inside_decision_section and (is_list_item or not section_prose_taken):
            if not NON_DECISION_PATTERN.match(candidate):
                decision_text = candidate[:MAX_DECISION_TEXT_LENGTH]
            if not is_list_item:
                section_prose_taken = True
        if decision_text is None:
            continue

        fingerprint = decision_fingerprint(decision_text)
        if not fingerprint or fingerprint in fingerprints:
            continue
        fingerprints.add(fingerprint)
        decisions.append(
            {
                "decision_text": decision_text,
                "evidence_quote": raw_line.strip(),
                "source_line_start": line_number,
                "source_line_end": line_number,
            }
        )
        if len(decisions) >= MAX_DECISIONS:
            break

    return decisions


def create_decision_artifact(connection: sqlite3.Connection, document_id: str) -> dict[str, Any]:
    document = get_document(connection, document_id)
    timestamp = utc_now_precise()
    artifact_id = f"dec_{uuid4().hex}"
    decisions = build_explicit_decisions(str(document["content"]))

    connection.execute(
        """
        INSERT INTO decision_artifacts (
            id, document_id, method, source_content_hash, decisions_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            artifact_id,
            document_id,
            DECISION_METHOD,
            document["content_hash"],
            json.dumps(decisions, ensure_ascii=False, separators=(",", ":")),
            timestamp,
        ),
    )
    create_audit_event(
        connection,
        action_id=None,
        event_type="decisions_extracted",
        event_payload={
            "document_id": document_id,
            "artifact_id": artifact_id,
            "method": DECISION_METHOD,
            "algorithm_revision": ALGORITHM_REVISION,
            "source_content_hash": document["content_hash"],
            "decision_count": len(decisions),
        },
        created_at=timestamp,
    )
    return {
        "id": artifact_id,
        "document_id": document_id,
        "method": DECISION_METHOD,
        "source_content_hash": str(document["content_hash"]),
        "decisions": decisions,
        "created_at": timestamp,
    }


def get_latest_decision_artifact(connection: sqlite3.Connection, document_id: str) -> dict[str, Any]:
    get_document(connection, document_id)
    row = connection.execute(
        """
        SELECT id, document_id, method, source_content_hash, decisions_json, created_at
        FROM decision_artifacts
        WHERE document_id = ?
        ORDER BY created_at DESC, rowid DESC
        LIMIT 1
        """,
        (document_id,),
    ).fetchone()
    if row is None:
        raise DecisionArtifactNotFoundError(document_id)

    return {
        "id": row["id"],
        "document_id": row["document_id"],
        "method": row["method"],
        "source_content_hash": row["source_content_hash"],
        "decisions": json.loads(row["decisions_json"]),
        "created_at": row["created_at"],
    }

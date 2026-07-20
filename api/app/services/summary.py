from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from api.app.services.audit import create_audit_event
from api.app.services.documents import get_document

ALGORITHM_REVISION = "structured_source_units_r1"
SUMMARY_METHOD = "extractive_v1"
TITLE_MAX_LENGTH = 160
ROLE_EVIDENCE_MAX_LENGTH = 240
KEY_POINT_MAX_LENGTH = 280
SUMMARY_MAX_LENGTH = 1600
MAX_KEY_POINTS = 4
MIN_MEANINGFUL_CHARS = 10
ROLE_INSUFFICIENCY = "Insufficient source content to identify role or purpose."
KEY_POINT_INSUFFICIENCY = "Insufficient source content to extract key points."

ATX_HEADING_PATTERN = re.compile(r"^[ \t]{0,3}(#{1,6})[ \t]+(.+?)[ \t]*$")
FENCE_OPEN_PATTERN = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})(?:[^`]*)$")
BULLET_PATTERN = re.compile(r"^[ \t]*[-*+][ \t]+(.+?)\s*$")
NUMBERED_PATTERN = re.compile(r"^[ \t]*\d+[.)][ \t]+(.+?)\s*$")
ARROW_PATTERN = re.compile(r"(?:->|=>|→|⇒)")
LINK_PATTERN = re.compile(r"\[([^\]]+)\]\([^)]+\)")
WHITESPACE_PATTERN = re.compile(r"\s+")
SENTENCE_PUNCTUATION_PATTERN = re.compile(r"[.!?。！？]")
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?。！？])\s+")
SAFE_BOUNDARY_PATTERN = re.compile(r"[.!?。！？;；:：,，、]")
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


class SummaryArtifactNotFoundError(Exception):
    """Raised when a document does not have a stored summary artifact."""


def utc_now_precise() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def normalize_source_text(text: str) -> str:
    if text.startswith("\ufeff"):
        text = text[1:]
    return text.replace("\r\n", "\n").replace("\r", "\n")


def strip_code_fences(text: str) -> str:
    retained_lines: list[str] = []
    fence_character: str | None = None
    fence_length = 0

    for line in text.split("\n"):
        match = FENCE_OPEN_PATTERN.match(line)
        if fence_character is None:
            if match:
                marker = match.group(1)
                fence_character = marker[0]
                fence_length = len(marker)
                continue
            retained_lines.append(line)
            continue

        stripped = line.strip()
        if stripped and set(stripped) == {fence_character} and len(stripped) >= fence_length:
            fence_character = None
            fence_length = 0

    return "\n".join(retained_lines)


def normalize_display_text(text: str) -> str:
    without_links = LINK_PATTERN.sub(r"\1", text)
    return WHITESPACE_PATTERN.sub(" ", without_links).strip()


def count_meaningful_chars(text: str) -> int:
    return len(re.sub(r"[\W_]+", "", text, flags=re.UNICODE))


def parse_atx_heading(line: str) -> str | None:
    match = ATX_HEADING_PATTERN.match(line)
    if not match:
        return None

    heading = re.sub(r"[ \t]+#+[ \t]*$", "", match.group(2))
    normalized = normalize_display_text(heading)
    return normalized or None


def truncate_at_boundary(text: str, maximum: int) -> str:
    normalized = normalize_display_text(text)
    if len(normalized) <= maximum:
        return normalized

    candidate = normalized[:maximum]
    safe_boundaries = [match.end() for match in SAFE_BOUNDARY_PATTERN.finditer(candidate)]
    if safe_boundaries:
        boundary = safe_boundaries[-1]
        if boundary >= maximum // 2:
            return candidate[:boundary].rstrip()

    hard_limit = maximum - 1
    whitespace_boundary = candidate.rfind(" ", maximum // 2, hard_limit)
    if whitespace_boundary != -1:
        return candidate[:whitespace_boundary].rstrip() + "…"
    return candidate[:hard_limit].rstrip() + "…"


def build_candidate_paragraphs(text: str) -> list[str]:
    return [normalize_display_text(part) for part in re.split(r"\n\s*\n+", text) if normalize_display_text(part)]


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

    for block_text, is_header_like in build_opening_blocks(paragraphs)[:DOCX_OPENING_BLOCK_LIMIT]:
        if not is_header_like and count_meaningful_chars(block_text) >= BODY_BLOCK_MIN_MEANINGFUL_CHARS:
            return block_text
    return ""


def split_sentences(text: str) -> list[str]:
    normalized = normalize_display_text(text)
    if not normalized:
        return []
    return [sentence.strip() for sentence in SENTENCE_SPLIT_PATTERN.split(normalized) if sentence.strip()]


def build_source_units(text: str, *, file_type: str | None) -> tuple[list[str], list[tuple[str, str]]]:
    headings: list[str] = []
    units: list[tuple[str, str]] = []
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return
        paragraph = normalize_display_text(" ".join(paragraph_lines))
        paragraph_lines.clear()
        if not paragraph:
            return
        kind = "header" if file_type == "docx" and is_header_like_paragraph(paragraph) else "prose"
        for sentence in split_sentences(paragraph):
            units.append((kind, sentence))

    for line in text.split("\n"):
        if not line.strip():
            flush_paragraph()
            continue

        heading = parse_atx_heading(line)
        if heading is not None:
            flush_paragraph()
            headings.append(heading)
            continue

        bullet_match = BULLET_PATTERN.match(line)
        if bullet_match:
            flush_paragraph()
            units.append(("list", normalize_display_text(bullet_match.group(1))))
            continue

        numbered_match = NUMBERED_PATTERN.match(line)
        if numbered_match:
            flush_paragraph()
            units.append(("list", normalize_display_text(numbered_match.group(1))))
            continue

        normalized_line = normalize_display_text(line)
        if normalized_line.endswith((":", "：")):
            flush_paragraph()
            units.append(("lead_in", normalized_line))
            continue

        if ARROW_PATTERN.search(normalized_line):
            flush_paragraph()
            units.append(("arrow", normalized_line))
            continue

        paragraph_lines.append(line)

    flush_paragraph()
    return headings, units


def normalized_fingerprint(text: str) -> str:
    return "".join(character for character in text.casefold() if character.isalnum())


def are_near_duplicates(left: str, right: str) -> bool:
    left_fingerprint = normalized_fingerprint(left)
    right_fingerprint = normalized_fingerprint(right)
    if not left_fingerprint or not right_fingerprint:
        return False
    if left_fingerprint == right_fingerprint:
        return True

    shorter, longer = sorted((left_fingerprint, right_fingerprint), key=len)
    if len(shorter) >= 20 and shorter in longer and len(shorter) / len(longer) >= 0.85:
        return True

    left_tokens = set(re.findall(r"\w+", left.casefold(), flags=re.UNICODE))
    right_tokens = set(re.findall(r"\w+", right.casefold(), flags=re.UNICODE))
    union = left_tokens | right_tokens
    return len(union) >= 4 and len(left_tokens & right_tokens) / len(union) >= 0.9


def select_title(
    headings: list[str],
    units: list[tuple[str, str]],
    *,
    content: str,
    file_type: str | None,
    scanned_title: str | None,
) -> str:
    if headings:
        return truncate_at_boundary(headings[0], TITLE_MAX_LENGTH)

    paragraphs = build_candidate_paragraphs(content)
    if file_type == "docx" and paragraphs:
        opening = paragraphs[0]
        if is_header_like_paragraph(opening):
            return truncate_at_boundary(opening, TITLE_MAX_LENGTH)

    normalized_scanned_title = normalize_display_text(scanned_title or "")
    if normalized_scanned_title:
        return truncate_at_boundary(normalized_scanned_title, TITLE_MAX_LENGTH)

    for kind, unit in units:
        if kind != "header" and count_meaningful_chars(unit) >= MIN_MEANINGFUL_CHARS:
            return truncate_at_boundary(unit, TITLE_MAX_LENGTH)
    return "Untitled document"


def select_role_evidence(
    units: list[tuple[str, str]],
    *,
    content: str,
    file_type: str | None,
) -> str:
    if file_type == "docx":
        opening_body = select_docx_opening_body_block(build_candidate_paragraphs(content))
        if opening_body:
            opening_sentences = split_sentences(opening_body)
            if opening_sentences:
                return truncate_at_boundary(opening_sentences[0], ROLE_EVIDENCE_MAX_LENGTH)

    for index, (kind, unit) in enumerate(units):
        if count_meaningful_chars(unit) < MIN_MEANINGFUL_CHARS:
            continue
        if kind == "prose":
            return truncate_at_boundary(unit, ROLE_EVIDENCE_MAX_LENGTH)
        if kind == "lead_in" and any(later_kind in {"list", "prose", "arrow"} for later_kind, _ in units[index + 1 :]):
            return truncate_at_boundary(unit, ROLE_EVIDENCE_MAX_LENGTH)
    return ROLE_INSUFFICIENCY


def apply_coverage_strategy(points: list[str]) -> list[str]:
    if len(points) <= MAX_KEY_POINTS:
        return points
    last_index = len(points) - 1
    selected_indexes = [(slot * last_index) // (MAX_KEY_POINTS - 1) for slot in range(MAX_KEY_POINTS)]
    return [points[index] for index in selected_indexes]


def select_key_points(units: list[tuple[str, str]], *, title: str, role_evidence: str) -> list[str]:
    selected: list[str] = []
    excluded = [title]
    if role_evidence != ROLE_INSUFFICIENCY:
        excluded.append(role_evidence)

    for kind, unit in units:
        if kind not in {"list", "prose", "arrow"}:
            continue
        normalized = normalize_display_text(unit)
        if normalized.endswith((":", "：")) or count_meaningful_chars(normalized) < MIN_MEANINGFUL_CHARS:
            continue
        if any(are_near_duplicates(normalized, existing) for existing in [*excluded, *selected]):
            continue
        selected.append(truncate_at_boundary(normalized, KEY_POINT_MAX_LENGTH))

    return apply_coverage_strategy(selected)


def build_extractive_summary(
    content: str,
    *,
    file_type: str | None = None,
    scanned_title: str | None = None,
) -> str:
    normalized_content = normalize_source_text(content)
    without_code = strip_code_fences(normalized_content)
    headings, units = build_source_units(without_code, file_type=file_type)
    title = select_title(
        headings,
        units,
        content=without_code,
        file_type=file_type,
        scanned_title=scanned_title,
    )
    role_evidence = select_role_evidence(units, content=without_code, file_type=file_type)
    key_points = select_key_points(units, title=title, role_evidence=role_evidence)
    rendered_points = key_points or [KEY_POINT_INSUFFICIENCY]

    summary = (
        f"Title: {title}\n\n"
        f"Role / purpose evidence:\n{role_evidence}\n\n"
        "Key points:\n"
        + "\n".join(f"- {point}" for point in rendered_points)
    )
    if len(summary) > SUMMARY_MAX_LENGTH:
        raise AssertionError("Structured summary exceeded its bounded output contract.")
    return summary


def create_summary_artifact(connection: sqlite3.Connection, document_id: str) -> dict[str, str]:
    document = get_document(connection, document_id)
    timestamp = utc_now_precise()
    artifact_id = f"sum_{uuid4().hex}"
    summary_text = build_extractive_summary(
        str(document["content"]),
        file_type=str(document["file_type"]),
        scanned_title=str(document["title"]),
    )

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
            SUMMARY_METHOD,
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
            "method": SUMMARY_METHOD,
            "algorithm_revision": ALGORITHM_REVISION,
            "source_content_hash": document["content_hash"],
        },
        created_at=timestamp,
    )
    return {
        "id": artifact_id,
        "document_id": document_id,
        "method": SUMMARY_METHOD,
        "source_content_hash": str(document["content_hash"]),
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

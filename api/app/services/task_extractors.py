from __future__ import annotations

import re

HEADING_PATTERN = re.compile(r"^\s{0,3}(?:#{1,6}\s+)?(?P<heading>[A-Za-z][A-Za-z0-9 \-]+):?\s*$")
BULLET_PATTERN = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)(?P<text>.+?)\s*$")
WHITESPACE_PATTERN = re.compile(r"\s+")
REQUIREMENTS_SECTION_REASONS = {
    "requirements": "requirements_heading",
    "functional requirements": "requirements_heading",
    "non-functional requirements": "requirements_heading",
    "acceptance criteria": "acceptance_criteria_heading",
    "constraints": "constraints_heading",
    "deliverables": "deliverables_heading",
}
MODAL_REASON_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bmust\b", re.IGNORECASE), "modal_must"),
    (re.compile(r"\bshall\b", re.IGNORECASE), "modal_shall"),
    (re.compile(r"\brequired\b", re.IGNORECASE), "required_marker"),
    (re.compile(r"\bneed to\b", re.IGNORECASE), "need_to_marker"),
]


def collapse_whitespace(text: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", text).strip()


def normalize_requirement_text(text: str) -> str:
    return collapse_whitespace(text.strip(" -\t"))


def get_heading_reason(line: str) -> str | None:
    match = HEADING_PATTERN.match(line)
    if not match:
        return None

    heading = collapse_whitespace(match.group("heading")).casefold()
    return REQUIREMENTS_SECTION_REASONS.get(heading)


def get_bullet_text(line: str) -> str | None:
    match = BULLET_PATTERN.match(line)
    if match is None:
        return None
    return normalize_requirement_text(match.group("text"))


def get_modal_reason(text: str) -> str | None:
    for pattern, reason in MODAL_REASON_PATTERNS:
        if pattern.search(text):
            return reason
    return None


def should_capture_needs_to(*, text: str, in_requirement_section: bool, is_bullet: bool) -> bool:
    lowered = text.casefold()
    if "need to" not in lowered:
        return True
    return in_requirement_section or is_bullet


def build_requirement_item(text: str, source_excerpt: str, match_reason: str) -> dict[str, str]:
    return {
        "text": normalize_requirement_text(text),
        "source_excerpt": collapse_whitespace(source_excerpt),
        "match_reason": match_reason,
    }


def dedupe_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for item in items:
        key = (item["text"].casefold(), item["match_reason"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return deduped


def extract_requirements_v1(content: str, *, file_type: str | None = None) -> dict[str, object]:
    del file_type

    items: list[dict[str, str]] = []
    current_heading_reason: str | None = None

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        heading_reason = get_heading_reason(line)
        if heading_reason is not None:
            current_heading_reason = heading_reason
            continue

        if HEADING_PATTERN.match(line):
            current_heading_reason = None
            continue

        bullet_text = get_bullet_text(raw_line)
        normalized_text = bullet_text if bullet_text is not None else normalize_requirement_text(line)
        if not normalized_text:
            continue

        modal_reason = get_modal_reason(normalized_text)
        is_bullet = bullet_text is not None
        in_requirement_section = current_heading_reason is not None

        if in_requirement_section and is_bullet:
            items.append(build_requirement_item(normalized_text, normalized_text, current_heading_reason))
            continue

        if modal_reason is None:
            continue

        if not should_capture_needs_to(
            text=normalized_text,
            in_requirement_section=in_requirement_section,
            is_bullet=is_bullet,
        ):
            continue

        if is_bullet:
            match_reason = "bulleted_requirement"
        else:
            match_reason = modal_reason

        items.append(build_requirement_item(normalized_text, normalized_text, match_reason))

    return {
        "method": "extract_requirements_v1",
        "items": dedupe_items(items),
    }

"""Read-only Task Packet v1 structural validator."""

from __future__ import annotations

from typing import Any

SLICE_NAME = "read_only_task_surface_resolver_and_packet_validator"
SUMMARY_PROTOCOL = "lawb.local_runner.task_surface_validation_summary.v1"
TASK_PACKET_PROTOCOL = "lawb.local_runner.task_packet.v1"

REQUIRED_TOP_LEVEL_FIELDS = (
    "protocol",
    "packet_id",
    "logical_issue",
    "phase",
    "action_type",
    "risk_level",
    "repository",
    "branch",
    "expected_head",
    "allowed_files",
    "forbidden_operations",
    "approval",
    "payload",
    "result_target",
    "stop_condition",
)

REQUIRED_NESTED_FIELDS = (
    ("approval", "required"),
    ("payload", "kind"),
    ("result_target", "github_issue"),
    ("result_target", "marker"),
)

LIST_FIELDS = ("allowed_files", "forbidden_operations")


def _base_summary() -> dict:
    return {
        "protocol": SUMMARY_PROTOCOL,
        "result": "blocked",
        "slice_name": SLICE_NAME,
        "task_surface_reference_checked": True,
        "active_task_packet_count": 1,
        "task_packet_boundary_markers_valid": True,
        "task_packet_protocol_valid": False,
        "logical_issue_matches_expected": False,
        "phase_matches_expected": False,
        "required_fields_present": False,
        "codex_side_action_executed": False,
        "repo_files_modified": False,
        "result_packet_written": False,
        "github_write_performed": False,
        "commit_performed": False,
        "push_performed": False,
        "errors": [],
        "next_recommended_action": "chatgpt_review",
    }


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None", "~"}:
        return None
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value


def _parse_line_oriented_packet(packet_text: str) -> dict:
    parsed: dict[str, Any] = {}
    stack: list[tuple[int, Any, dict[str, Any] | None, str | None]] = [
        (-1, parsed, None, None)
    ]

    for raw_line in packet_text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        while stack and indent <= stack[-1][0]:
            stack.pop()

        if stripped.startswith("- "):
            item = stripped[2:].strip()
            current_indent, current_container, parent, parent_key = stack[-1]
            if not isinstance(current_container, list):
                if parent is None or parent_key is None:
                    continue
                current_container = []
                parent[parent_key] = current_container
                stack[-1] = (current_indent, current_container, parent, parent_key)
            current_container.append(_parse_scalar(item))
            continue

        if ":" not in stripped:
            continue

        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()

        parent = stack[-1][1]
        if not isinstance(parent, dict):
            continue

        if value == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child, parent, key))
        else:
            parent[key] = _parse_scalar(value)

    return parsed


def _has_nested(parsed: dict, path: tuple[str, str]) -> bool:
    parent, child = path
    return isinstance(parsed.get(parent), dict) and child in parsed[parent]


def validate_task_packet(packet_text: str, expected: dict | None = None) -> dict:
    """Validate extracted Task Packet v1 content without executing anything."""
    summary = _base_summary()
    expected = expected or {}

    if not isinstance(packet_text, str):
        summary["errors"].append("packet_text_not_string")
        return summary

    parsed = _parse_line_oriented_packet(packet_text)
    missing_fields = [
        field for field in REQUIRED_TOP_LEVEL_FIELDS if field not in parsed
    ]
    missing_fields.extend(
        ".".join(path) for path in REQUIRED_NESTED_FIELDS if not _has_nested(parsed, path)
    )
    unknown_fields = [
        field for field in parsed if field not in set(REQUIRED_TOP_LEVEL_FIELDS)
    ]
    invalid_list_fields = [
        field
        for field in LIST_FIELDS
        if field in parsed and (not isinstance(parsed[field], list) or not parsed[field])
    ]

    protocol = parsed.get("protocol")
    summary["task_packet_protocol_valid"] = protocol == TASK_PACKET_PROTOCOL
    if protocol is None:
        summary["errors"].append("protocol_missing")
    elif protocol != TASK_PACKET_PROTOCOL:
        summary["errors"].append("invalid_task_packet_protocol")

    if missing_fields:
        summary["errors"].append("required_fields_missing")
        summary["missing_fields"] = missing_fields
    else:
        summary["required_fields_present"] = True

    if unknown_fields:
        summary["errors"].append("unknown_top_level_fields")
        summary["unknown_fields"] = unknown_fields

    if invalid_list_fields:
        summary["errors"].append("invalid_list_fields")
        summary["invalid_list_fields"] = invalid_list_fields

    logical_issue = parsed.get("logical_issue")
    phase = parsed.get("phase")

    if "logical_issue" in expected:
        summary["logical_issue_matches_expected"] = (
            logical_issue == expected["logical_issue"]
            or str(logical_issue) == str(expected["logical_issue"])
        )
        if not summary["logical_issue_matches_expected"]:
            summary["errors"].append("logical_issue_mismatch")
    else:
        summary["logical_issue_matches_expected"] = logical_issue is not None

    if "phase" in expected:
        summary["phase_matches_expected"] = phase == expected["phase"]
        if not summary["phase_matches_expected"]:
            summary["errors"].append("phase_mismatch")
    else:
        summary["phase_matches_expected"] = phase is not None

    if not summary["errors"]:
        summary["result"] = "success"

    return summary


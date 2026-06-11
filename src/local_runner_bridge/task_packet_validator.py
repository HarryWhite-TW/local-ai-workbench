"""Read-only Task Packet v1 structural validator."""

from __future__ import annotations

from typing import Any

SLICE_NAME = "read_only_task_surface_resolver_and_packet_validator"
SUMMARY_PROTOCOL = "lawb.local_runner.task_surface_validation_summary.v1"
TASK_PACKET_PROTOCOL_V1 = "lawb.local_runner.task_packet.v1"
TASK_PACKET_PROTOCOL_V1_1 = "lawb.local_runner.task_packet.v1.1"
TASK_PACKET_PROTOCOL = TASK_PACKET_PROTOCOL_V1
ACCEPTED_TASK_PACKET_PROTOCOLS = {TASK_PACKET_PROTOCOL_V1, TASK_PACKET_PROTOCOL_V1_1}

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

V1_1_REQUIRED_TOP_LEVEL_FIELDS = (
    "task_mode",
    "objective",
    "max_allowed_files",
    "context_scope",
    "repair_attempt_limit",
    "verification_command_policy",
    "verification_commands",
    "scope_expansion_allowed",
)

REQUIRED_NESTED_FIELDS = (
    ("approval", "required"),
    ("payload", "kind"),
    ("result_target", "github_issue"),
    ("result_target", "marker"),
)

LIST_FIELDS = ("allowed_files", "forbidden_operations")
V1_1_LIST_FIELDS = (*LIST_FIELDS, "context_scope", "verification_commands")
V1_1_NON_EMPTY_LIST_FIELDS = (*LIST_FIELDS, "context_scope")
V1_1_TASK_MODES = {"PLAN_ONLY", "PATCH_ONLY", "VERIFY_ONLY", "DOCS_ONLY"}
V1_1_REPAIR_ATTEMPT_LIMITS = {0, 1}
V1_1_VERIFICATION_COMMAND_POLICIES = {
    "explicit_only",
    "not_required",
    "forbidden",
}


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
    if value == "[]":
        return []
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


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_v1_1_discipline(parsed: dict, summary: dict) -> None:
    task_mode = parsed.get("task_mode")
    objective = parsed.get("objective")
    max_allowed_files = parsed.get("max_allowed_files")
    allowed_files = parsed.get("allowed_files")
    context_scope = parsed.get("context_scope")
    repair_attempt_limit = parsed.get("repair_attempt_limit")
    verification_command_policy = parsed.get("verification_command_policy")
    verification_commands = parsed.get("verification_commands")
    scope_expansion_allowed = parsed.get("scope_expansion_allowed")

    if task_mode not in V1_1_TASK_MODES:
        summary["errors"].append("invalid_task_mode")

    if not isinstance(objective, str) or not objective.strip():
        summary["errors"].append("invalid_objective")

    if not _is_integer(max_allowed_files) or max_allowed_files <= 0:
        summary["errors"].append("invalid_max_allowed_files")
    elif isinstance(allowed_files, list) and len(allowed_files) > max_allowed_files:
        summary["errors"].append("allowed_files_exceed_max_allowed_files")

    if not isinstance(context_scope, list) or not context_scope:
        summary["errors"].append("invalid_context_scope")

    if (
        not _is_integer(repair_attempt_limit)
        or repair_attempt_limit not in V1_1_REPAIR_ATTEMPT_LIMITS
    ):
        summary["errors"].append("invalid_repair_attempt_limit")

    if verification_command_policy not in V1_1_VERIFICATION_COMMAND_POLICIES:
        summary["errors"].append("invalid_verification_command_policy")

    if not isinstance(verification_commands, list):
        summary["errors"].append("invalid_verification_commands")
    elif (
        verification_command_policy == "explicit_only"
        and not verification_commands
    ):
        summary["errors"].append("verification_commands_required")

    if scope_expansion_allowed is not False:
        summary["errors"].append("scope_expansion_allowed_must_be_false")


def validate_task_packet(packet_text: str, expected: dict | None = None) -> dict:
    """Validate extracted Task Packet content without executing anything."""
    summary = _base_summary()
    expected = expected or {}

    if not isinstance(packet_text, str):
        summary["errors"].append("packet_text_not_string")
        return summary

    parsed = _parse_line_oriented_packet(packet_text)
    protocol = parsed.get("protocol")
    required_top_level_fields = list(REQUIRED_TOP_LEVEL_FIELDS)
    if protocol == TASK_PACKET_PROTOCOL_V1_1:
        required_top_level_fields.extend(V1_1_REQUIRED_TOP_LEVEL_FIELDS)

    missing_fields = [field for field in required_top_level_fields if field not in parsed]
    missing_fields.extend(
        ".".join(path) for path in REQUIRED_NESTED_FIELDS if not _has_nested(parsed, path)
    )
    known_top_level_fields = set(required_top_level_fields)
    unknown_fields = [field for field in parsed if field not in known_top_level_fields]
    list_fields = V1_1_LIST_FIELDS if protocol == TASK_PACKET_PROTOCOL_V1_1 else LIST_FIELDS
    non_empty_list_fields = (
        V1_1_NON_EMPTY_LIST_FIELDS
        if protocol == TASK_PACKET_PROTOCOL_V1_1
        else LIST_FIELDS
    )
    invalid_list_fields = [
        field
        for field in list_fields
        if field in parsed
        and (
            not isinstance(parsed[field], list)
            or (field in non_empty_list_fields and not parsed[field])
        )
    ]

    summary["task_packet_protocol_valid"] = protocol in ACCEPTED_TASK_PACKET_PROTOCOLS
    if protocol is None:
        summary["errors"].append("protocol_missing")
    elif protocol not in ACCEPTED_TASK_PACKET_PROTOCOLS:
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

    if protocol == TASK_PACKET_PROTOCOL_V1_1:
        _validate_v1_1_discipline(parsed, summary)

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


"""Local-only bounded Writeback Approval Record validator."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

SUMMARY_PROTOCOL = "lawb.approval_record_local_validation_summary.v1"
ALLOWED_WRITE_MODES = {"dry_run_only"}
ALLOWED_TARGET_TYPES = {"github_issue_comment", "local_review_file"}
DISALLOWED_TARGET_TYPES = {
    "broad_issue_scan",
    "latest_issue",
    "next_issue",
    "multiple_issues",
    "pull_request",
    "merge",
    "label_change",
    "issue_close",
}
REQUIRED_FIELDS = (
    "approval_record_version",
    "approval_id",
    "source_preview_id",
    "source_result_surface_id",
    "source_task_reference",
    "writeback_target_type",
    "writeback_target_reference",
    "chatgpt_readback_completed",
    "approved_by_user",
    "approval_timestamp",
    "approved_write_mode",
    "allowed_next_step",
    "forbidden_actions",
    "external_side_effect_allowed",
    "created_at",
)
REQUIRED_FORBIDDEN_ACTIONS = (
    "github_writeback_implementation",
    "github_comment_write",
    "github_issue_body_update",
    "result_packet_write_implementation",
    "codex_side_action_execution",
    "runner_behavior",
    "dispatcher_behavior",
    "watcher_behavior",
    "broad_issue_scan",
    "next_latest_issue_inference",
    "autonomous_execution",
    "automatic_commit",
    "automatic_push",
    "pr_creation",
    "merge",
    "issue_close",
    "label_change",
    "approval_chaining",
    "real_write_mode",
)
AMBIGUOUS_TARGET_FIELDS = (
    "writeback_target_references",
    "writeback_targets",
    "targets",
)
TOKEN_VALUE_TERMS = (
    "ghp_",
    "gho_",
    "ghu_",
    "ghs_",
    "github_pat_",
    "bearer ",
    "authorization:",
    "api_key=",
    "access_token=",
)
UNSAFE_REQUEST_TERMS = {
    "github_writeback_implementation",
    "github_writeback",
    "github writeback",
    "github_comment_write",
    "github_comment",
    "github comment",
    "github_issue_body_update",
    "issue body update",
    "result_packet_write_implementation",
    "result_packet_write",
    "result packet write",
    "codex_side_action_execution",
    "runner_behavior",
    "dispatcher_behavior",
    "watcher_behavior",
    "issue_close",
    "issue close",
    "label_change",
    "label change",
    "pr_creation",
    "pull_request",
    "pull request",
    "merge",
    "approval_chaining",
    "real_write_mode",
}
INFERENCE_TERMS = {
    "previous_conversation",
    "previous conversation",
    "commit_success",
    "commit success",
    "push_success",
    "push success",
    "validation_success",
    "validation success",
    "dry_run_preview_success",
    "dry-run preview success",
    "dry run preview success",
}
REQUEST_FIELD_NAMES = (
    "requested_actions",
    "requested_behavior",
    "requested_behaviors",
    "requested_side_effects",
    "approved_actions",
    "approved_behavior",
    "approved_behaviors",
    "writeback_request",
    "operation_request",
)
INFERENCE_FIELD_NAMES = (
    "approval_basis",
    "approval_inferred_from",
    "inferred_from",
    "approval_source",
)


def _as_lower_text(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_")


def _value_contains_token(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    lowered = value.lower()
    return any(term in lowered for term in TOKEN_VALUE_TERMS)


def _contains_token_value(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_contains_token_value(item) for item in value.values())
    if isinstance(value, list | tuple | set):
        return any(_contains_token_value(item) for item in value)
    return _value_contains_token(value)


def _redact_token_text(value: Any) -> Any:
    if isinstance(value, str) and _value_contains_token(value):
        return "[REDACTED]"
    return value


def _contains_text_term(value: Any, terms: set[str]) -> bool:
    if isinstance(value, Mapping):
        return any(_contains_text_term(item, terms) for item in value.values())
    if isinstance(value, list | tuple | set):
        return any(_contains_text_term(item, terms) for item in value)
    if not isinstance(value, str):
        return False
    lowered = value.lower()
    normalized = lowered.replace("-", "_")
    return any(term in lowered or term in normalized for term in terms)


def _has_multiple_targets(record: Mapping[str, Any]) -> bool:
    if any(field in record for field in AMBIGUOUS_TARGET_FIELDS):
        return True

    reference = record.get("writeback_target_reference")
    if isinstance(reference, list | tuple | set):
        return len(reference) != 1

    target_type = record.get("writeback_target_type")
    if isinstance(target_type, list | tuple | set):
        return len(target_type) != 1

    return False


def _target_is_inferred(record: Mapping[str, Any]) -> bool:
    target_type = _as_lower_text(record.get("writeback_target_type"))
    reference = _as_lower_text(record.get("writeback_target_reference"))
    inferred_terms = ("latest", "next", "inferred", "search_result", "scan")
    if target_type in DISALLOWED_TARGET_TYPES:
        return True
    return any(term in reference for term in inferred_terms)


def _base_summary(record: Mapping[str, Any] | None = None) -> dict[str, Any]:
    record = record or {}
    return {
        "protocol": SUMMARY_PROTOCOL,
        "result": "blocked",
        "validation_result": "blocked",
        "approval_record_version": _redact_token_text(
            record.get("approval_record_version")
        ),
        "approval_id": _redact_token_text(record.get("approval_id")),
        "source_preview_id": _redact_token_text(record.get("source_preview_id")),
        "source_result_surface_id": _redact_token_text(
            record.get("source_result_surface_id")
        ),
        "source_task_reference": _redact_token_text(
            record.get("source_task_reference")
        ),
        "writeback_target_type": record.get("writeback_target_type"),
        "writeback_target_reference": _redact_token_text(
            record.get("writeback_target_reference")
        ),
        "required_fields_present": False,
        "chatgpt_readback_gate_satisfied": False,
        "user_approval_gate_satisfied": False,
        "approved_write_mode": record.get("approved_write_mode"),
        "forbidden_actions_present": False,
        "external_side_effect_allowed": False,
        "blocked_reasons": [],
        "github_write_performed": False,
        "result_packet_written": False,
        "codex_side_action_executed": False,
        "runner_invoked": False,
        "dispatcher_invoked": False,
        "watcher_invoked": False,
        "broad_scan_performed": False,
        "next_latest_issue_inference_performed": False,
        "commit_performed": False,
        "push_performed": False,
        "pr_created": False,
        "merge_performed": False,
        "issue_closed": False,
        "label_changed": False,
        "next_recommended_step": "chatgpt_review",
    }


def _add_block(summary: dict[str, Any], reason: str) -> None:
    if reason not in summary["blocked_reasons"]:
        summary["blocked_reasons"].append(reason)


def _validate_required_fields(
    record: Mapping[str, Any], summary: dict[str, Any]
) -> None:
    missing_fields = [field for field in REQUIRED_FIELDS if field not in record]
    if missing_fields:
        _add_block(summary, "required_fields_missing")
        summary["missing_fields"] = missing_fields
        return
    summary["required_fields_present"] = True


def _validate_target(record: Mapping[str, Any], summary: dict[str, Any]) -> None:
    target_type = record.get("writeback_target_type")
    target_reference = record.get("writeback_target_reference")
    normalized_type = _as_lower_text(target_type)

    if _has_multiple_targets(record):
        _add_block(summary, "multiple_targets_present")

    if normalized_type not in ALLOWED_TARGET_TYPES:
        _add_block(summary, "writeback_target_type_not_allowed")

    if normalized_type in DISALLOWED_TARGET_TYPES:
        _add_block(summary, "disallowed_target_type")

    if not isinstance(target_reference, str) or not target_reference.strip():
        _add_block(summary, "writeback_target_reference_missing")

    if _target_is_inferred(record):
        _add_block(summary, "target_inferred_or_broad")


def _validate_gates(record: Mapping[str, Any], summary: dict[str, Any]) -> None:
    readback = record.get("chatgpt_readback_completed") is True
    approved = record.get("approved_by_user") is True
    summary["chatgpt_readback_gate_satisfied"] = readback
    summary["user_approval_gate_satisfied"] = approved

    if not readback:
        _add_block(summary, "chatgpt_readback_gate_not_satisfied")
    if not approved:
        _add_block(summary, "user_approval_gate_not_satisfied")

    if not isinstance(record.get("source_preview_id"), str) or not record.get(
        "source_preview_id", ""
    ).strip():
        _add_block(summary, "source_preview_id_missing")

    if record.get("approved_write_mode") not in ALLOWED_WRITE_MODES:
        _add_block(summary, "approved_write_mode_not_allowed")

    if record.get("external_side_effect_allowed") is not False:
        _add_block(summary, "external_side_effect_allowed_not_false")


def _validate_forbidden_actions(
    record: Mapping[str, Any], summary: dict[str, Any]
) -> None:
    actions = record.get("forbidden_actions")
    if not isinstance(actions, list) or not actions:
        _add_block(summary, "forbidden_actions_missing")
        return

    action_set = {_as_lower_text(action) for action in actions if isinstance(action, str)}
    missing_actions = [
        action for action in REQUIRED_FORBIDDEN_ACTIONS if action not in action_set
    ]
    if missing_actions:
        _add_block(summary, "required_forbidden_actions_missing")
        summary["missing_forbidden_actions"] = missing_actions
    else:
        summary["forbidden_actions_present"] = True


def _validate_unsafe_requests(
    record: Mapping[str, Any], summary: dict[str, Any]
) -> None:
    for field in REQUEST_FIELD_NAMES:
        if field in record and _contains_text_term(record[field], UNSAFE_REQUEST_TERMS):
            _add_block(summary, "forbidden_action_requested")

    for field in INFERENCE_FIELD_NAMES:
        if field in record and _contains_text_term(record[field], INFERENCE_TERMS):
            _add_block(summary, "approval_inferred_from_evidence_or_conversation")

    flags = record.get("safety_flags") or record.get("required_safety_flags")
    if isinstance(flags, Mapping):
        unsafe_true_flags = (
            "github_write_performed",
            "result_packet_written",
            "codex_side_action_executed",
            "runner_invoked",
            "dispatcher_invoked",
            "watcher_invoked",
            "broad_issue_scan_performed",
            "next_latest_issue_inference_performed",
            "pr_created",
            "merge_performed",
            "issue_closed",
            "label_changed",
            "approval_chaining_attempted",
        )
        if any(flags.get(flag) is True for flag in unsafe_true_flags):
            _add_block(summary, "forbidden_action_requested")


def validate_approval_record(record: Mapping[str, Any] | Any) -> dict[str, Any]:
    """Validate one local approval record without side effects."""
    if not isinstance(record, Mapping):
        summary = _base_summary()
        _add_block(summary, "approval_record_not_object")
        return summary

    summary = _base_summary(record)
    _validate_required_fields(record, summary)
    _validate_target(record, summary)
    _validate_gates(record, summary)
    _validate_forbidden_actions(record, summary)
    _validate_unsafe_requests(record, summary)

    if _contains_token_value(record):
        _add_block(summary, "token_value_detected")

    if not summary["blocked_reasons"]:
        summary["result"] = "success"
        summary["validation_result"] = "success"
        summary["next_recommended_step"] = "bounded_writeback_planning"

    summary["external_side_effect_allowed"] = False
    return summary


def validate_approval_record_json(approval_record_json: str) -> dict[str, Any]:
    """Parse and validate a local approval record JSON string."""
    if not isinstance(approval_record_json, str):
        summary = _base_summary()
        _add_block(summary, "approval_record_json_not_string")
        return summary

    try:
        record = json.loads(approval_record_json.lstrip("\ufeff"))
    except json.JSONDecodeError:
        summary = _base_summary()
        _add_block(summary, "approval_record_json_parse_failed")
        return summary

    return validate_approval_record(record)

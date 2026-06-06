"""Local-only bounded Writeback Readiness Gate validator."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

SUMMARY_PROTOCOL = "lawb.writeback_readiness_gate_local_validation_summary.v1"
ALLOWED_WRITE_MODES = {"dry_run_only"}
REQUIRED_FIELDS = (
    "readiness_gate_version",
    "readiness_id",
    "source_task_reference",
    "source_result_surface_id",
    "writeback_target_reference",
    "target_contract_validation_result",
    "dry_run_preview_result",
    "chatgpt_readback_completed",
    "approval_record_validation_result",
    "approved_write_mode",
    "external_side_effect_allowed",
    "real_write_mode_allowed",
    "readiness_result",
    "blocked_reasons",
    "next_recommended_step",
    "created_at",
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
    "broad_issue_scan",
    "broad issue scan",
    "next_latest_issue_inference",
    "latest_issue",
    "latest issue",
    "next_issue",
    "next issue",
    "automatic_commit",
    "automatic_push",
    "pr_creation",
    "pull_request",
    "pull request",
    "merge",
    "issue_close",
    "issue close",
    "label_change",
    "label change",
    "approval_chaining",
    "real_write_mode",
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
    "target_basis",
    "target_inferred_from",
    "readiness_basis",
    "readiness_inferred_from",
    "inferred_from",
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

    return False


def _target_is_inferred(record: Mapping[str, Any]) -> bool:
    reference = _as_lower_text(record.get("writeback_target_reference"))
    inferred_terms = ("latest", "next", "inferred", "search_result", "scan")
    if any(term in reference for term in inferred_terms):
        return True

    return any(
        field in record and _contains_text_term(record[field], UNSAFE_REQUEST_TERMS)
        for field in INFERENCE_FIELD_NAMES
    )


def _base_summary(record: Mapping[str, Any] | None = None) -> dict[str, Any]:
    record = record or {}
    return {
        "protocol": SUMMARY_PROTOCOL,
        "result": "blocked",
        "validation_result": "blocked",
        "readiness_gate_version": _redact_token_text(
            record.get("readiness_gate_version")
        ),
        "readiness_id": _redact_token_text(record.get("readiness_id")),
        "source_task_reference": _redact_token_text(
            record.get("source_task_reference")
        ),
        "source_result_surface_id": _redact_token_text(
            record.get("source_result_surface_id")
        ),
        "writeback_target_reference": _redact_token_text(
            record.get("writeback_target_reference")
        ),
        "target_contract_validation_result": record.get(
            "target_contract_validation_result"
        ),
        "dry_run_preview_result": record.get("dry_run_preview_result"),
        "chatgpt_readback_completed": record.get("chatgpt_readback_completed"),
        "approval_record_validation_result": record.get(
            "approval_record_validation_result"
        ),
        "approved_write_mode": record.get("approved_write_mode"),
        "external_side_effect_allowed": False,
        "real_write_mode_allowed": False,
        "required_fields_present": False,
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


def _validate_required_values(
    record: Mapping[str, Any], summary: dict[str, Any]
) -> None:
    if not isinstance(record.get("source_task_reference"), str) or not record.get(
        "source_task_reference", ""
    ).strip():
        _add_block(summary, "source_task_reference_missing")

    if not isinstance(record.get("source_result_surface_id"), str) or not record.get(
        "source_result_surface_id", ""
    ).strip():
        _add_block(summary, "source_result_surface_id_missing")

    if not isinstance(record.get("writeback_target_reference"), str) or not record.get(
        "writeback_target_reference", ""
    ).strip():
        _add_block(summary, "writeback_target_reference_missing")

    if record.get("readiness_result") != "pass":
        _add_block(summary, "readiness_result_not_pass")

    if record.get("target_contract_validation_result") != "success":
        _add_block(summary, "target_contract_validation_not_success")

    if record.get("dry_run_preview_result") != "success":
        _add_block(summary, "dry_run_preview_not_success")

    if record.get("approval_record_validation_result") != "success":
        _add_block(summary, "approval_record_validation_not_success")

    if record.get("chatgpt_readback_completed") is not True:
        _add_block(summary, "chatgpt_readback_not_completed")

    if record.get("approved_write_mode") not in ALLOWED_WRITE_MODES:
        _add_block(summary, "approved_write_mode_not_allowed")

    if record.get("external_side_effect_allowed") is not False:
        _add_block(summary, "external_side_effect_allowed_not_false")

    if record.get("real_write_mode_allowed") is not False:
        _add_block(summary, "real_write_mode_allowed_not_false")


def _validate_target(record: Mapping[str, Any], summary: dict[str, Any]) -> None:
    if _has_multiple_targets(record):
        _add_block(summary, "multiple_targets_present")
    if _target_is_inferred(record):
        _add_block(summary, "target_inferred_or_broad")


def _validate_unsafe_requests(
    record: Mapping[str, Any], summary: dict[str, Any]
) -> None:
    for field in REQUEST_FIELD_NAMES:
        if field in record and _contains_text_term(record[field], UNSAFE_REQUEST_TERMS):
            _add_block(summary, "forbidden_action_requested")

    flags = record.get("safety_flags") or record.get("required_safety_flags")
    if isinstance(flags, Mapping):
        unsafe_true_flags = {
            "github_write_performed": "github_writeback_requested",
            "github_comment_written": "github_writeback_requested",
            "github_issue_body_updated": "github_writeback_requested",
            "result_packet_written": "result_packet_write_requested",
            "codex_side_action_executed": "codex_side_action_requested",
            "runner_invoked": "runner_behavior_requested",
            "dispatcher_invoked": "dispatcher_behavior_requested",
            "watcher_invoked": "watcher_behavior_requested",
            "broad_issue_scan_performed": "broad_issue_scan_requested",
            "next_latest_issue_inference_performed": (
                "next_latest_issue_inference_requested"
            ),
            "pr_created": "pr_creation_requested",
            "merge_performed": "merge_requested",
            "issue_closed": "issue_close_requested",
            "label_changed": "label_change_requested",
            "approval_chaining_attempted": "approval_chaining_requested",
        }
        for flag, reason in unsafe_true_flags.items():
            if flags.get(flag) is True:
                _add_block(summary, reason)

    if record.get("broad_issue_scan_requested") is True:
        _add_block(summary, "broad_issue_scan_requested")
    if record.get("next_latest_issue_inference_requested") is True:
        _add_block(summary, "next_latest_issue_inference_requested")


def validate_readiness_gate(record: Mapping[str, Any] | Any) -> dict[str, Any]:
    """Validate one local readiness gate record without side effects."""
    if not isinstance(record, Mapping):
        summary = _base_summary()
        _add_block(summary, "readiness_record_not_object")
        return summary

    summary = _base_summary(record)
    _validate_required_fields(record, summary)
    _validate_required_values(record, summary)
    _validate_target(record, summary)
    _validate_unsafe_requests(record, summary)

    if _contains_token_value(record):
        _add_block(summary, "token_value_detected")

    if not summary["blocked_reasons"]:
        summary["result"] = "success"
        summary["validation_result"] = "success"
        summary["next_recommended_step"] = "chatgpt_review"

    summary["external_side_effect_allowed"] = False
    summary["real_write_mode_allowed"] = False
    return summary


def validate_readiness_gate_json(readiness_gate_json: str) -> dict[str, Any]:
    """Parse and validate a local readiness gate JSON string."""
    if not isinstance(readiness_gate_json, str):
        summary = _base_summary()
        _add_block(summary, "readiness_gate_json_not_string")
        return summary

    try:
        record = json.loads(readiness_gate_json.lstrip("\ufeff"))
    except json.JSONDecodeError:
        summary = _base_summary()
        _add_block(summary, "readiness_gate_json_parse_failed")
        return summary

    return validate_readiness_gate(record)

"""Local-only Writeback Implementation Boundary validator."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

SUMMARY_PROTOCOL = "lawb.writeback_implementation_boundary_local_validation_summary.v1"
REQUIRED_FIELDS = (
    "boundary_version",
    "boundary_id",
    "future_candidate_issue",
    "future_risk_lane_required",
    "first_possible_writeback_type",
    "allowed_target_type",
    "allowed_target_reference_mode",
    "source_readiness_id",
    "source_preview_id",
    "source_result_surface_id",
    "required_preconditions",
    "required_runtime_gates",
    "forbidden_scope",
    "future_audit_shape",
    "real_write_indicators",
    "implementation_allowed_now",
    "writeback_allowed_now",
    "result_packet_write_allowed_now",
    "runner_dispatcher_watcher_allowed_now",
    "next_recommended_step",
    "created_at",
)
REAL_WRITE_INDICATORS = (
    "writeback_attempted",
    "writeback_performed",
    "github_comment_written",
    "github_issue_body_updated",
    "result_packet_written",
    "runner_invoked",
    "dispatcher_invoked",
    "watcher_invoked",
    "issue_closed",
    "label_changed",
    "pr_created",
    "merge_performed",
    "token_value_printed",
    "token_value_written",
)
AMBIGUOUS_TARGET_FIELDS = (
    "writeback_target_references",
    "writeback_targets",
    "targets",
    "target_references",
    "target_reference_list",
)
TARGET_REFERENCE_FIELDS = (
    "writeback_target_reference",
    "target_reference",
    "allowed_target_reference",
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
    "github_issue_body_update",
    "issue_body_update",
    "issue body update",
    "result_packet_write",
    "result packet write",
    "result_packet_write_implementation",
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
    "issue_close",
    "issue close",
    "close issue",
    "label_change",
    "label change",
    "pr_creation",
    "pull_request",
    "pull request",
    "merge",
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
    "boundary_basis",
    "boundary_inferred_from",
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


def _lookup_nested(record: Mapping[str, Any], *field_names: str) -> Any:
    for name in field_names:
        if name in record:
            return record[name]

    future_audit_shape = record.get("future_audit_shape")
    if isinstance(future_audit_shape, Mapping):
        for name in field_names:
            if name in future_audit_shape:
                return future_audit_shape[name]

    required_runtime_gates = record.get("required_runtime_gates")
    if isinstance(required_runtime_gates, Mapping):
        for name in field_names:
            if name in required_runtime_gates:
                return required_runtime_gates[name]

    return None


def _has_multiple_targets(record: Mapping[str, Any]) -> bool:
    if any(field in record for field in AMBIGUOUS_TARGET_FIELDS):
        return True

    for section_name in ("future_audit_shape", "required_runtime_gates"):
        section = record.get(section_name)
        if not isinstance(section, Mapping):
            continue
        if any(field in section for field in AMBIGUOUS_TARGET_FIELDS):
            return True
        target_count = section.get("writeback_target_count")
        if target_count is not None and target_count != 1:
            return True

    for field in TARGET_REFERENCE_FIELDS:
        reference = _lookup_nested(record, field)
        if isinstance(reference, list | tuple | set):
            return len(reference) != 1

    return False


def _target_is_inferred(record: Mapping[str, Any]) -> bool:
    inferred_terms = ("latest", "next", "inferred", "search_result", "scan")
    for field in TARGET_REFERENCE_FIELDS:
        reference = _as_lower_text(_lookup_nested(record, field))
        if any(term in reference for term in inferred_terms):
            return True

    return any(
        field in record and _contains_text_term(record[field], UNSAFE_REQUEST_TERMS)
        for field in INFERENCE_FIELD_NAMES
    )


def _real_write_indicator_value(
    record: Mapping[str, Any], indicator: str
) -> Any:
    if indicator in record:
        return record[indicator]

    real_write_indicators = record.get("real_write_indicators")
    if isinstance(real_write_indicators, Mapping) and indicator in real_write_indicators:
        return real_write_indicators[indicator]

    future_audit_shape = record.get("future_audit_shape")
    if isinstance(future_audit_shape, Mapping) and indicator in future_audit_shape:
        return future_audit_shape[indicator]

    required_runtime_gates = record.get("required_runtime_gates")
    if isinstance(required_runtime_gates, Mapping) and indicator in required_runtime_gates:
        return required_runtime_gates[indicator]

    return None


def _real_write_indicators_all_false(record: Mapping[str, Any]) -> bool:
    return all(_real_write_indicator_value(record, field) is False for field in REAL_WRITE_INDICATORS)


def _base_summary(record: Mapping[str, Any] | None = None) -> dict[str, Any]:
    record = record or {}
    return {
        "protocol": SUMMARY_PROTOCOL,
        "result": "blocked",
        "validation_result": "blocked",
        "boundary_version": _redact_token_text(record.get("boundary_version")),
        "boundary_id": _redact_token_text(record.get("boundary_id")),
        "future_candidate_issue": record.get("future_candidate_issue"),
        "future_risk_lane_required": record.get("future_risk_lane_required"),
        "first_possible_writeback_type": record.get("first_possible_writeback_type"),
        "allowed_target_type": record.get("allowed_target_type"),
        "allowed_target_reference_mode": record.get("allowed_target_reference_mode"),
        "source_readiness_id": _redact_token_text(record.get("source_readiness_id")),
        "source_preview_id": _redact_token_text(record.get("source_preview_id")),
        "source_result_surface_id": _redact_token_text(
            record.get("source_result_surface_id")
        ),
        "implementation_allowed_now": record.get("implementation_allowed_now"),
        "writeback_allowed_now": record.get("writeback_allowed_now"),
        "result_packet_write_allowed_now": record.get("result_packet_write_allowed_now"),
        "runner_dispatcher_watcher_allowed_now": record.get(
            "runner_dispatcher_watcher_allowed_now"
        ),
        "required_fields_present": False,
        "real_write_indicators_all_false": False,
        "blocked_reasons": [],
        "github_write_performed": False,
        "github_comment_written": False,
        "github_issue_body_updated": False,
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
    if not isinstance(record.get("boundary_id"), str) or not record.get(
        "boundary_id", ""
    ).strip():
        _add_block(summary, "boundary_id_missing")

    if not isinstance(record.get("source_readiness_id"), str) or not record.get(
        "source_readiness_id", ""
    ).strip():
        _add_block(summary, "source_readiness_id_missing")

    if not isinstance(record.get("source_preview_id"), str) or not record.get(
        "source_preview_id", ""
    ).strip():
        _add_block(summary, "source_preview_id_missing")

    if not isinstance(record.get("source_result_surface_id"), str) or not record.get(
        "source_result_surface_id", ""
    ).strip():
        _add_block(summary, "source_result_surface_id_missing")

    if record.get("future_risk_lane_required") != "strict":
        _add_block(summary, "future_risk_lane_required_not_strict")

    if record.get("first_possible_writeback_type") != "github_issue_comment":
        _add_block(summary, "first_possible_writeback_type_not_allowed")

    if record.get("allowed_target_type") != "explicit_single_github_issue_comment":
        _add_block(summary, "allowed_target_type_not_allowed")

    if record.get("allowed_target_reference_mode") != "explicit_only":
        _add_block(summary, "allowed_target_reference_mode_not_explicit_only")

    if record.get("implementation_allowed_now") is not False:
        _add_block(summary, "implementation_allowed_now_not_false")

    if record.get("writeback_allowed_now") is not False:
        _add_block(summary, "writeback_allowed_now_not_false")

    if record.get("result_packet_write_allowed_now") is not False:
        _add_block(summary, "result_packet_write_allowed_now_not_false")

    if record.get("runner_dispatcher_watcher_allowed_now") is not False:
        _add_block(summary, "runner_dispatcher_watcher_allowed_now_not_false")


def _validate_target(record: Mapping[str, Any], summary: dict[str, Any]) -> None:
    if _has_multiple_targets(record):
        _add_block(summary, "multiple_targets_present")
    if _target_is_inferred(record):
        _add_block(summary, "target_inferred_or_broad")


def _validate_real_write_indicators(
    record: Mapping[str, Any], summary: dict[str, Any]
) -> None:
    for indicator in REAL_WRITE_INDICATORS:
        if _real_write_indicator_value(record, indicator) is True:
            _add_block(summary, f"{indicator}_not_false")

    if not _real_write_indicators_all_false(record):
        _add_block(summary, "real_write_indicators_not_all_false")
        return

    summary["real_write_indicators_all_false"] = True


def _validate_unsafe_requests(
    record: Mapping[str, Any], summary: dict[str, Any]
) -> None:
    for field in REQUEST_FIELD_NAMES:
        if field in record and _contains_text_term(record[field], UNSAFE_REQUEST_TERMS):
            _add_block(summary, "forbidden_action_requested")

    for section_name in ("forbidden_scope", "required_runtime_gates", "future_audit_shape"):
        section = record.get(section_name)
        if isinstance(section, Mapping) and _contains_text_term(section, UNSAFE_REQUEST_TERMS):
            # These sections may legitimately name forbidden behavior as false/blocked
            # fields, so only boolean true values are handled below.
            pass

    unsafe_true_flags = {
        "github_issue_body_update": "github_issue_body_update_requested",
        "github_issue_body_update_requested": "github_issue_body_update_requested",
        "result_packet_write": "result_packet_write_requested",
        "result_packet_write_requested": "result_packet_write_requested",
        "runner": "runner_behavior_requested",
        "runner_behavior_requested": "runner_behavior_requested",
        "dispatcher": "dispatcher_behavior_requested",
        "dispatcher_behavior_requested": "dispatcher_behavior_requested",
        "watcher": "watcher_behavior_requested",
        "watcher_behavior_requested": "watcher_behavior_requested",
        "broad_issue_scan": "broad_issue_scan_requested",
        "broad_issue_scan_requested": "broad_issue_scan_requested",
        "latest_next_issue_inference": "next_latest_issue_inference_requested",
        "next_latest_issue_inference_requested": (
            "next_latest_issue_inference_requested"
        ),
        "issue_close": "issue_close_requested",
        "issue_close_requested": "issue_close_requested",
        "label_change": "label_change_requested",
        "label_change_requested": "label_change_requested",
        "pr_creation": "pr_creation_requested",
        "pr_creation_requested": "pr_creation_requested",
        "merge": "merge_requested",
        "merge_requested": "merge_requested",
        "approval_chaining_attempted": "approval_chaining_requested",
    }
    for section_name in ("required_runtime_gates", "safety_flags"):
        section = record.get(section_name)
        if not isinstance(section, Mapping):
            continue
        for flag, reason in unsafe_true_flags.items():
            if section.get(flag) is True:
                _add_block(summary, reason)

    if record.get("broad_issue_scan_requested") is True:
        _add_block(summary, "broad_issue_scan_requested")
    if record.get("next_latest_issue_inference_requested") is True:
        _add_block(summary, "next_latest_issue_inference_requested")


def validate_writeback_implementation_boundary(
    record: Mapping[str, Any] | Any,
) -> dict[str, Any]:
    """Validate one local writeback implementation boundary record."""
    if not isinstance(record, Mapping):
        summary = _base_summary()
        _add_block(summary, "boundary_record_not_object")
        return summary

    summary = _base_summary(record)
    _validate_required_fields(record, summary)
    _validate_required_values(record, summary)
    _validate_target(record, summary)
    _validate_real_write_indicators(record, summary)
    _validate_unsafe_requests(record, summary)

    if _contains_token_value(record):
        _add_block(summary, "token_value_detected")

    if not summary["blocked_reasons"]:
        summary["result"] = "success"
        summary["validation_result"] = "success"
        summary["next_recommended_step"] = "chatgpt_review"

    summary["github_write_performed"] = False
    summary["github_comment_written"] = False
    summary["github_issue_body_updated"] = False
    summary["result_packet_written"] = False
    summary["codex_side_action_executed"] = False
    summary["runner_invoked"] = False
    summary["dispatcher_invoked"] = False
    summary["watcher_invoked"] = False
    return summary


def validate_writeback_implementation_boundary_json(
    boundary_json: str,
) -> dict[str, Any]:
    """Parse and validate a local boundary record JSON string."""
    if not isinstance(boundary_json, str):
        summary = _base_summary()
        _add_block(summary, "boundary_json_not_string")
        return summary

    try:
        record = json.loads(boundary_json.lstrip("\ufeff"))
    except json.JSONDecodeError:
        summary = _base_summary()
        _add_block(summary, "boundary_json_parse_failed")
        return summary

    return validate_writeback_implementation_boundary(record)

"""Local-only Writeback Target Contract validator."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

SUMMARY_PROTOCOL = "lawb.writeback_target_contract_local_validation_summary.v1"

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
ALLOWED_WRITE_MODES = {"dry_run_only"}

REQUIRED_FIELDS = (
    "contract_version",
    "writeback_target_type",
    "writeback_target_reference",
    "source_result_surface_id",
    "source_task_reference",
    "approved_by_user",
    "approval_timestamp",
    "chatgpt_readback_completed",
    "dry_run_required",
    "write_mode",
    "safe_preview_required",
    "forbidden_actions",
    "required_safety_flags",
    "abort_conditions",
    "next_recommended_step",
)

REQUIRED_SAFETY_FLAGS = (
    "exact_single_target_confirmed",
    "chatgpt_readback_completed",
    "explicit_user_approval_present",
    "safe_preview_completed",
    "token_value_printed",
    "token_value_written",
    "broad_issue_scan_performed",
    "next_latest_issue_inference_performed",
    "automatic_issue_close_performed",
    "automatic_label_change_performed",
    "pr_created",
    "merge_performed",
    "approval_chaining_attempted",
)

REQUIRED_FORBIDDEN_ACTIONS = (
    "github_writeback_implementation",
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
)

AMBIGUOUS_TARGET_FIELDS = (
    "writeback_target_references",
    "writeback_targets",
    "targets",
)

UNSAFE_REQUEST_TERMS = {
    "broad_issue_scan",
    "broad issue scan",
    "latest_issue",
    "latest issue",
    "next_issue",
    "next issue",
    "next_latest_issue_inference",
    "issue_close",
    "issue close",
    "close issue",
    "label_change",
    "label change",
    "pull_request",
    "pull request",
    "pr_creation",
    "merge",
}

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


def _base_summary(contract: Mapping[str, Any] | None = None) -> dict[str, Any]:
    contract = contract or {}
    contract_version = contract.get("contract_version")
    target_reference = contract.get("writeback_target_reference")

    if _value_contains_token(contract_version):
        contract_version = "[REDACTED]"
    if _value_contains_token(target_reference):
        target_reference = "[REDACTED]"

    return {
        "protocol": SUMMARY_PROTOCOL,
        "result": "blocked",
        "validation_result": "blocked",
        "contract_version": contract_version,
        "writeback_target_type": contract.get("writeback_target_type"),
        "writeback_target_reference": target_reference,
        "required_fields_present": False,
        "approval_gate_satisfied": False,
        "chatgpt_readback_gate_satisfied": False,
        "dry_run_required": False,
        "forbidden_actions_present": False,
        "blocked_reasons": [],
        "external_side_effect_allowed": False,
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
        "next_recommended_action": "chatgpt_review",
    }


def _add_block(summary: dict[str, Any], reason: str) -> None:
    if reason not in summary["blocked_reasons"]:
        summary["blocked_reasons"].append(reason)


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


def _contains_unsafe_request(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_contains_unsafe_request(item) for item in value.values())
    if isinstance(value, list | tuple | set):
        return any(_contains_unsafe_request(item) for item in value)
    if not isinstance(value, str):
        return False
    lowered = value.lower()
    return any(term in lowered for term in UNSAFE_REQUEST_TERMS)


def _has_multiple_targets(contract: Mapping[str, Any]) -> bool:
    if any(field in contract for field in AMBIGUOUS_TARGET_FIELDS):
        return True

    reference = contract.get("writeback_target_reference")
    if isinstance(reference, list | tuple | set):
        return len(reference) != 1

    target_type = contract.get("writeback_target_type")
    if isinstance(target_type, list | tuple | set):
        return len(target_type) != 1

    return False


def _target_is_inferred(contract: Mapping[str, Any]) -> bool:
    target_type = _as_lower_text(contract.get("writeback_target_type"))
    reference = _as_lower_text(contract.get("writeback_target_reference"))
    inferred_terms = ("latest", "next", "inferred", "search_result", "scan")
    if target_type in DISALLOWED_TARGET_TYPES:
        return True
    return any(term in reference for term in inferred_terms)


def _validate_required_fields(
    contract: Mapping[str, Any], summary: dict[str, Any]
) -> None:
    missing_fields = [field for field in REQUIRED_FIELDS if field not in contract]
    if missing_fields:
        _add_block(summary, "required_fields_missing")
        summary["missing_fields"] = missing_fields
        return
    summary["required_fields_present"] = True


def _validate_target(contract: Mapping[str, Any], summary: dict[str, Any]) -> None:
    target_type = contract.get("writeback_target_type")
    target_reference = contract.get("writeback_target_reference")
    normalized_type = _as_lower_text(target_type)

    if _has_multiple_targets(contract):
        _add_block(summary, "multiple_targets_present")

    if normalized_type not in ALLOWED_TARGET_TYPES:
        _add_block(summary, "writeback_target_type_not_allowed")

    if normalized_type in DISALLOWED_TARGET_TYPES:
        _add_block(summary, "disallowed_target_type")

    if not isinstance(target_reference, str) or not target_reference.strip():
        _add_block(summary, "writeback_target_reference_missing")

    if _target_is_inferred(contract):
        _add_block(summary, "target_inferred_or_broad")

    target_fields = {
        "writeback_target_type": target_type,
        "writeback_target_reference": target_reference,
    }
    if _contains_unsafe_request(target_fields):
        _add_block(summary, "forbidden_target_or_action_requested")


def _validate_gates(contract: Mapping[str, Any], summary: dict[str, Any]) -> None:
    approved = contract.get("approved_by_user") is True
    readback = contract.get("chatgpt_readback_completed") is True
    dry_run_required = contract.get("dry_run_required") is True

    summary["approval_gate_satisfied"] = approved
    summary["chatgpt_readback_gate_satisfied"] = readback
    summary["dry_run_required"] = dry_run_required

    if not approved:
        _add_block(summary, "approval_gate_not_satisfied")
    if not readback:
        _add_block(summary, "chatgpt_readback_gate_not_satisfied")
    if "dry_run_required" not in contract:
        _add_block(summary, "dry_run_required_missing")
    elif not dry_run_required:
        _add_block(summary, "dry_run_required_not_true")

    if contract.get("write_mode") not in ALLOWED_WRITE_MODES:
        _add_block(summary, "write_mode_not_allowed")


def _validate_forbidden_actions(
    contract: Mapping[str, Any], summary: dict[str, Any]
) -> None:
    actions = contract.get("forbidden_actions")
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


def _validate_safety_flags(
    contract: Mapping[str, Any], summary: dict[str, Any]
) -> None:
    flags = contract.get("required_safety_flags")
    if not isinstance(flags, Mapping):
        _add_block(summary, "required_safety_flags_missing")
        return

    missing_flags = [field for field in REQUIRED_SAFETY_FLAGS if field not in flags]
    if missing_flags:
        _add_block(summary, "required_safety_flags_missing")
        summary["missing_safety_flags"] = missing_flags

    if flags.get("broad_issue_scan_performed") is True:
        _add_block(summary, "broad_issue_scan_requested")
    if flags.get("next_latest_issue_inference_performed") is True:
        _add_block(summary, "next_latest_issue_inference_requested")
    if flags.get("automatic_issue_close_performed") is True:
        _add_block(summary, "issue_close_requested")
    if flags.get("automatic_label_change_performed") is True:
        _add_block(summary, "label_change_requested")
    if flags.get("pr_created") is True:
        _add_block(summary, "pr_creation_requested")
    if flags.get("merge_performed") is True:
        _add_block(summary, "merge_requested")
    if flags.get("approval_chaining_attempted") is True:
        _add_block(summary, "approval_chaining_requested")
    if flags.get("token_value_printed") is True or flags.get("token_value_written") is True:
        _add_block(summary, "token_value_print_or_write_requested")


def _validate_abort_conditions(
    contract: Mapping[str, Any], summary: dict[str, Any]
) -> None:
    abort_conditions = contract.get("abort_conditions")
    if not isinstance(abort_conditions, list) or not abort_conditions:
        _add_block(summary, "abort_conditions_missing")


def validate_writeback_target_contract(contract: Mapping[str, Any] | Any) -> dict[str, Any]:
    """Validate one local Writeback Target Contract without side effects."""
    if not isinstance(contract, Mapping):
        summary = _base_summary()
        _add_block(summary, "contract_not_object")
        return summary

    summary = _base_summary(contract)

    _validate_required_fields(contract, summary)
    _validate_target(contract, summary)
    _validate_gates(contract, summary)
    _validate_forbidden_actions(contract, summary)
    _validate_safety_flags(contract, summary)
    _validate_abort_conditions(contract, summary)

    if _contains_token_value(contract):
        _add_block(summary, "token_value_detected")

    if _contains_unsafe_request(contract.get("requested_actions")):
        _add_block(summary, "forbidden_action_requested")

    if not summary["blocked_reasons"]:
        summary["result"] = "success"
        summary["validation_result"] = "success"

    summary["external_side_effect_allowed"] = False
    return summary


def validate_writeback_target_contract_json(contract_json: str) -> dict[str, Any]:
    """Parse and validate a local Writeback Target Contract JSON string."""
    if not isinstance(contract_json, str):
        summary = _base_summary()
        _add_block(summary, "contract_json_not_string")
        return summary

    try:
        contract = json.loads(contract_json.lstrip("\ufeff"))
    except json.JSONDecodeError:
        summary = _base_summary()
        _add_block(summary, "contract_json_parse_failed")
        return summary

    return validate_writeback_target_contract(contract)

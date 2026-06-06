"""Local-only Writeback Dry-Run Preview builder."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

PREVIEW_VERSION = "lawb.writeback_dry_run_preview.v1"
ALLOWED_WRITE_MODE = "dry_run_only"
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
REQUIRED_CONTRACT_FIELDS = (
    "source_result_surface_id",
    "source_task_reference",
    "writeback_target_type",
    "writeback_target_reference",
    "write_mode",
    "forbidden_actions",
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
    "github_comment",
    "github comment",
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
    "writeback_request",
    "operation_request",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _requested_unsafe_behavior(*values: Any) -> bool:
    for value in values:
        if not isinstance(value, Mapping):
            continue
        for field in REQUEST_FIELD_NAMES:
            if field in value and _contains_unsafe_request(value[field]):
                return True

        flags = value.get("safety_flags") or value.get("required_safety_flags")
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
                return True
    return False


def _base_preview(
    *,
    contract: Mapping[str, Any] | None = None,
    validation_summary: Mapping[str, Any] | None = None,
    preview_content: Any = "",
    preview_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    contract = contract or {}
    validation_summary = validation_summary or {}
    return {
        "preview_version": PREVIEW_VERSION,
        "preview_id": preview_id or f"preview-{uuid4()}",
        "result": "blocked",
        "source_result_surface_id": _redact_token_text(
            contract.get("source_result_surface_id")
        ),
        "source_task_reference": _redact_token_text(contract.get("source_task_reference")),
        "writeback_target_type": contract.get("writeback_target_type"),
        "writeback_target_reference": _redact_token_text(
            contract.get("writeback_target_reference")
        ),
        "contract_validation_result": validation_summary.get("validation_result"),
        "write_mode": contract.get("write_mode"),
        "preview_content": _redact_token_text(preview_content),
        "safe_preview_summary": "Local dry-run preview only. No external write performed.",
        "forbidden_actions": contract.get("forbidden_actions") or [],
        "safety_flags": {
            "external_side_effect_allowed": False,
            "token_value_printed": False,
            "token_value_written": False,
            "authorization_header_included": False,
            "hidden_environment_value_included": False,
            "secret_value_included": False,
            "broad_issue_scan_performed": False,
            "next_latest_issue_inference_performed": False,
            "github_write_performed": False,
            "result_packet_written": False,
            "codex_side_action_executed": False,
            "runner_invoked": False,
            "dispatcher_invoked": False,
            "watcher_invoked": False,
            "pr_created": False,
            "merge_performed": False,
            "issue_closed": False,
            "label_changed": False,
            "approval_chaining_attempted": False,
        },
        "requires_chatgpt_readback": True,
        "requires_user_approval": True,
        "external_side_effect_allowed": False,
        "blocked_reasons": [],
        "next_recommended_step": "chatgpt_readback_then_user_decision",
        "created_at": created_at or _now_iso(),
    }


def _add_block(preview: dict[str, Any], reason: str) -> None:
    if reason not in preview["blocked_reasons"]:
        preview["blocked_reasons"].append(reason)


def _validate_inputs(
    preview: dict[str, Any],
    *,
    contract: Mapping[str, Any] | Any,
    validation_summary: Mapping[str, Any] | Any,
    result_surface_summary: Mapping[str, Any] | Any,
    preview_content: Any,
) -> None:
    if not isinstance(contract, Mapping):
        _add_block(preview, "contract_not_object")
        return

    if not isinstance(validation_summary, Mapping):
        _add_block(preview, "contract_validation_summary_missing")
    elif validation_summary.get("validation_result") != "success":
        _add_block(preview, "contract_validation_failed")

    if not isinstance(result_surface_summary, Mapping):
        _add_block(preview, "source_result_surface_summary_missing")

    missing_fields = [field for field in REQUIRED_CONTRACT_FIELDS if field not in contract]
    if missing_fields:
        _add_block(preview, "required_fields_missing")
        preview["missing_fields"] = missing_fields

    target_type = _as_lower_text(contract.get("writeback_target_type"))
    if target_type not in ALLOWED_TARGET_TYPES:
        _add_block(preview, "writeback_target_type_not_allowed")
    if target_type in DISALLOWED_TARGET_TYPES:
        _add_block(preview, "disallowed_target_type")

    if _has_multiple_targets(contract):
        _add_block(preview, "multiple_targets_present")
    if _target_is_inferred(contract):
        _add_block(preview, "target_inferred_or_broad")

    if contract.get("write_mode") != ALLOWED_WRITE_MODE:
        _add_block(preview, "write_mode_not_allowed")
        preview["write_mode"] = ALLOWED_WRITE_MODE

    if not isinstance(contract.get("forbidden_actions"), list) or not contract.get(
        "forbidden_actions"
    ):
        _add_block(preview, "forbidden_actions_missing")

    if not isinstance(preview_content, str) or not preview_content.strip():
        _add_block(preview, "safe_preview_content_missing")

    if validation_summary and validation_summary.get("external_side_effect_allowed") is not False:
        _add_block(preview, "external_side_effect_allowed_not_false")

    if _contains_token_value(
        {
            "contract": contract,
            "validation_summary": validation_summary,
            "result_surface_summary": result_surface_summary,
            "preview_content": preview_content,
        }
    ):
        _add_block(preview, "token_value_detected")
        preview["preview_content"] = "[REDACTED]"

    if _requested_unsafe_behavior(contract, validation_summary, result_surface_summary):
        _add_block(preview, "forbidden_action_requested")


def build_writeback_dry_run_preview(
    contract: Mapping[str, Any] | Any,
    validation_summary: Mapping[str, Any] | Any,
    result_surface_summary: Mapping[str, Any] | Any,
    preview_content: str,
    *,
    preview_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build one local dry-run preview dictionary without side effects."""
    preview = _base_preview(
        contract=contract if isinstance(contract, Mapping) else None,
        validation_summary=(
            validation_summary if isinstance(validation_summary, Mapping) else None
        ),
        preview_content=preview_content,
        preview_id=preview_id,
        created_at=created_at,
    )

    _validate_inputs(
        preview,
        contract=contract,
        validation_summary=validation_summary,
        result_surface_summary=result_surface_summary,
        preview_content=preview_content,
    )

    if not preview["blocked_reasons"]:
        preview["result"] = "success"
        preview["contract_validation_result"] = "success"

    preview["write_mode"] = ALLOWED_WRITE_MODE
    preview["requires_chatgpt_readback"] = True
    preview["requires_user_approval"] = True
    preview["external_side_effect_allowed"] = False
    preview["safety_flags"]["external_side_effect_allowed"] = False
    return preview


def build_writeback_dry_run_preview_from_json(
    contract_json: str,
    result_surface_summary_json: str,
    preview_content: str,
    *,
    preview_id: str | None = None,
    created_at: str | None = None,
    validation_summary_json: str | None = None,
) -> dict[str, Any]:
    """Parse local JSON inputs and build one dry-run preview dictionary."""
    try:
        contract = json.loads(contract_json.lstrip("\ufeff"))
    except (AttributeError, json.JSONDecodeError):
        return build_writeback_dry_run_preview(
            {},
            {"validation_result": "blocked", "external_side_effect_allowed": False},
            {},
            preview_content,
            preview_id=preview_id,
            created_at=created_at,
        ) | {"blocked_reasons": ["contract_json_parse_failed"]}

    try:
        result_surface_summary = json.loads(result_surface_summary_json.lstrip("\ufeff"))
    except (AttributeError, json.JSONDecodeError):
        return build_writeback_dry_run_preview(
            contract,
            {"validation_result": "blocked", "external_side_effect_allowed": False},
            {},
            preview_content,
            preview_id=preview_id,
            created_at=created_at,
        ) | {"blocked_reasons": ["result_surface_json_parse_failed"]}

    if validation_summary_json is None:
        from local_runner_bridge.writeback_target_contract import (
            validate_writeback_target_contract,
        )

        validation_summary = validate_writeback_target_contract(contract)
    else:
        try:
            validation_summary = json.loads(validation_summary_json.lstrip("\ufeff"))
        except (AttributeError, json.JSONDecodeError):
            validation_summary = {
                "validation_result": "blocked",
                "external_side_effect_allowed": False,
                "blocked_reasons": ["validation_summary_json_parse_failed"],
            }

    return build_writeback_dry_run_preview(
        contract,
        validation_summary,
        result_surface_summary,
        preview_content,
        preview_id=preview_id,
        created_at=created_at,
    )

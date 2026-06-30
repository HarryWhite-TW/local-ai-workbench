"""RV2-03 A3 read-only publication preflight."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from local_runner_bridge.b4d_smoke_manifest import INBOX_ISSUE, REPOSITORY, validate_manifest
from local_runner_bridge.bridge_operator_b1 import (
    LocalReadiness,
    check_local_readiness,
    run_bridge_operator_b1_dry_run,
)
from local_runner_bridge.bridge_operator_b3 import read_processed_request_records

PROTOCOL = "lawb.rv2_03_publication_preflight.v1"
MAX_EXECUTION_TTL_SECONDS = 1200
SAFE_WAIT_REASONS = frozenset(
    {
        "missing_request",
        "missing_current_request",
        "no_current_request_after_consumption",
    }
)


def run_publication_preflight(
    manifest: Any,
    *,
    repo_root: str | Path,
    state_dir: str | Path | None = None,
    github_client: Any | None = None,
    local_checker: Any | None = None,
    now_utc: datetime | Callable[[], datetime] | None = None,
    b1_runner: Callable[..., dict[str, Any]] = run_bridge_operator_b1_dry_run,
) -> dict[str, Any]:
    """Validate one manifest and current Inbox state before Approval A publication.

    This function is read-only: it validates data, reads existing processed
    history if present, and delegates Inbox classification to B1. It never
    writes GitHub comments, modifies B3 state, or invokes B2/B3/Dispatcher/Runner.
    """
    evaluated_at = _normalize_now(now_utc() if callable(now_utc) else now_utc)
    result = _base_result(evaluated_at)

    validation = validate_manifest(manifest, now=evaluated_at)
    result["manifest_validation"] = _manifest_validation_telemetry(validation)
    if validation.get("valid") is not True:
        _block(result, "invalid_manifest")
        return result

    preview = validation["preview"]
    canonical = validation["canonical_manifest"]
    result["manifest_sha256"] = preview["manifest_sha256"]
    result["binding"] = preview["binding"]

    expires = _parse_utc_basic(canonical["expires"])
    if expires is None:
        _block(result, "invalid_manifest_expiry")
        return result
    remaining_ttl_seconds = (expires - evaluated_at).total_seconds()
    result["remaining_ttl_seconds"] = remaining_ttl_seconds
    if remaining_ttl_seconds <= 0:
        _block(result, "execution_ttl_not_positive")
        return result
    if remaining_ttl_seconds > MAX_EXECUTION_TTL_SECONDS:
        _block(result, "execution_ttl_too_long")
        return result

    readiness = _run_local_readiness_check(repo_root, local_checker)
    result["local_readiness_telemetry"] = _local_readiness_telemetry(readiness)
    readiness_errors = _validate_local_readiness(readiness, repo_root, canonical)
    if readiness_errors:
        for reason in readiness_errors:
            _block(result, reason)
        return result

    state_root = _resolve_state_dir(state_dir)
    result["state_dir"] = str(state_root) if state_root is not None else None
    if state_root is None:
        _block(result, "localappdata_missing")
        return result

    processed_path = state_root / "processed_requests.jsonl"
    try:
        consumed_request_records = (
            read_processed_request_records(processed_path) if processed_path.exists() else {}
        )
    except (OSError, json.JSONDecodeError, ValueError):
        _block(result, "corrupted_processed_history")
        return result
    result["processed_request_count"] = len(consumed_request_records)

    try:
        b1_summary = b1_runner(
            inbox_issue=INBOX_ISSUE,
            repo_root=repo_root,
            repository=REPOSITORY,
            github_client=github_client,
            local_checker=lambda _repo_root: readiness,
            now_utc=evaluated_at,
            consumed_request_ids=consumed_request_records,
        )
    except Exception as error:
        b1_summary = {
            "result": "blocked",
            "blocked_reasons": ["github_read_unavailable"],
            "github_read_error_type": type(error).__name__,
        }
    result["inbox_telemetry"] = _inbox_telemetry(b1_summary, evaluated_at)

    if _publication_is_safe(b1_summary):
        result["result"] = "success"
        result["publication_safe"] = True
        result["blocked_reasons"] = []
        result["approval_a"] = preview["approval_a"]
        result["next_required_action"] = "human_review_approval_a"
        return result

    reasons = list(b1_summary.get("blocked_reasons", []))
    if b1_summary.get("result") == "success" and int(b1_summary.get("current_request_count") or 0) > 0:
        reasons = ["current_request_already_present"]
    elif _looks_like_inconsistent_safe_wait(b1_summary):
        reasons = ["unexpected_b1_result"]
    elif not reasons:
        reasons = ["unexpected_b1_result"]
    for reason in reasons:
        _block(result, str(reason))
    return result


def _publication_is_safe(b1_summary: dict[str, Any]) -> bool:
    reasons = b1_summary.get("blocked_reasons")
    if not isinstance(reasons, list):
        return False
    reason_values = [str(reason) for reason in reasons]
    return (
        b1_summary.get("result") == "blocked"
        and len(reason_values) == 1
        and reason_values[0] in SAFE_WAIT_REASONS
        and b1_summary.get("current_request_count") == 0
        and b1_summary.get("fixed_inbox_read_performed") is True
        and b1_summary.get("github_read_available") is True
        and b1_summary.get("repository") == REPOSITORY
        and b1_summary.get("configured_inbox_issue") == INBOX_ISSUE
    )


def _looks_like_inconsistent_safe_wait(b1_summary: dict[str, Any]) -> bool:
    reasons = b1_summary.get("blocked_reasons")
    if not isinstance(reasons, list):
        return True
    return any(str(reason) in SAFE_WAIT_REASONS for reason in reasons)


def _base_result(evaluated_at: datetime) -> dict[str, Any]:
    return {
        "protocol": PROTOCOL,
        "result": "blocked",
        "publication_safe": False,
        "blocked_reasons": [],
        "evaluated_at_utc": _format_time(evaluated_at),
        "max_execution_ttl_seconds": MAX_EXECUTION_TTL_SECONDS,
        "remaining_ttl_seconds": None,
        "manifest_sha256": None,
        "binding": None,
        "approval_a": None,
        "inbox_telemetry": _empty_inbox_telemetry(evaluated_at),
        "local_readiness_telemetry": _empty_local_readiness_telemetry(),
        "manifest_validation": None,
        "state_dir": None,
        "processed_request_count": 0,
        "safety": _safety(),
        "next_required_action": "stop_and_review",
    }


def _manifest_validation_telemetry(validation: dict[str, Any]) -> dict[str, Any]:
    return {
        "valid": bool(validation.get("valid")),
        "errors": list(validation.get("errors", [])),
        "warnings": list(validation.get("warnings", [])),
    }


def _empty_inbox_telemetry(evaluated_at: datetime) -> dict[str, Any]:
    return {
        "b1_result": None,
        "b1_blocked_reasons": [],
        "evaluated_at_utc": _format_time(evaluated_at),
        "current_request_count": 0,
        "consumed_request_count": 0,
        "expired_request_count": 0,
        "selected_request_state": None,
        "selected_inbox_comment_id": None,
        "selected_request_id": None,
        "selected_expiry": None,
        "request_lifecycle": [],
    }


def _empty_local_readiness_telemetry() -> dict[str, Any]:
    return {
        "check_performed": False,
        "repo_root": None,
        "branch": None,
        "head": None,
        "clean": None,
        "gh_available": None,
        "gh_authenticated": None,
        "gh_read_available": None,
        "errors": [],
    }


def _local_readiness_telemetry(readiness: LocalReadiness | None) -> dict[str, Any]:
    if readiness is None:
        telemetry = _empty_local_readiness_telemetry()
        telemetry["check_performed"] = True
        telemetry["errors"] = ["local_readiness_unavailable"]
        return telemetry
    return {
        "check_performed": True,
        "repo_root": readiness.repo_root,
        "branch": readiness.branch,
        "head": readiness.head,
        "clean": readiness.clean,
        "gh_available": readiness.gh_available,
        "gh_authenticated": readiness.gh_authenticated,
        "gh_read_available": readiness.gh_read_available,
        "errors": list(readiness.errors),
    }


def _run_local_readiness_check(
    repo_root: str | Path,
    local_checker: Callable[[str | Path], LocalReadiness] | None,
) -> LocalReadiness | None:
    checker = local_checker or check_local_readiness
    try:
        return checker(repo_root)
    except Exception:
        return None


def _validate_local_readiness(
    readiness: LocalReadiness | None,
    repo_root: str | Path,
    canonical: dict[str, Any],
) -> list[str]:
    if readiness is None:
        return ["local_readiness_unavailable"]
    reasons: list[str] = []
    if readiness.repo_root != str(Path(repo_root).resolve()):
        reasons.append("wrong_repo_root")
    if readiness.branch != canonical["branch"]:
        reasons.append("wrong_branch")
    if readiness.head != canonical["head"]:
        reasons.append("wrong_head")
    if readiness.clean is not True:
        reasons.append("dirty_repository")
    if readiness.gh_available is not True:
        reasons.append("missing_github_cli")
    if readiness.gh_authenticated is not True or readiness.gh_read_available is not True:
        reasons.append("github_read_unavailable")
    return reasons


def _inbox_telemetry(b1_summary: dict[str, Any], evaluated_at: datetime) -> dict[str, Any]:
    return {
        "b1_result": b1_summary.get("result"),
        "b1_blocked_reasons": list(b1_summary.get("blocked_reasons", [])),
        "evaluated_at_utc": b1_summary.get("evaluated_at_utc") or _format_time(evaluated_at),
        "current_request_count": int(b1_summary.get("current_request_count") or 0),
        "consumed_request_count": int(b1_summary.get("consumed_request_count") or 0),
        "expired_request_count": int(b1_summary.get("expired_request_count") or 0),
        "selected_request_state": b1_summary.get("selected_request_state"),
        "selected_inbox_comment_id": b1_summary.get("inbox_comment_id"),
        "selected_request_id": b1_summary.get("request_id"),
        "selected_expiry": b1_summary.get("expires"),
        "request_lifecycle": list(b1_summary.get("request_lifecycle", [])),
    }


def _safety() -> dict[str, bool]:
    return {
        "github_write_performed": False,
        "b2_invoked": False,
        "b3_loop_invoked": False,
        "dispatcher_invoked": False,
        "runner_invoked": False,
        "codex_invoked": False,
        "stage_performed": False,
        "commit_performed": False,
        "push_performed": False,
    }


def _block(result: dict[str, Any], reason: str) -> None:
    if reason not in result["blocked_reasons"]:
        result["blocked_reasons"].append(reason)
    result["result"] = "blocked"
    result["publication_safe"] = False
    result["approval_a"] = None
    result["next_required_action"] = "stop_and_review"


def _resolve_state_dir(state_dir: str | Path | None) -> Path | None:
    if state_dir is not None:
        return Path(state_dir)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    return Path(local_app_data) / "LocalAIWorkbench" / "BridgeOperator"


def _parse_utc_basic(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _normalize_now(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_manifest_sha256(canonical_manifest: dict[str, Any]) -> str:
    compact = json.dumps(canonical_manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()

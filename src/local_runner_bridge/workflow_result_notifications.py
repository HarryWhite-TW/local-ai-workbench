"""Restart-safe notifications for newly persisted Bridge terminal settlements."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from local_runner_bridge.bridge_operator_lifecycle_state import (
    LifecycleEvidenceError,
    write_durable_json,
    write_exclusive_json,
)


NOTIFICATION_STATE_PROTOCOL = "lawb.workflow_result_notifications.v1"
PROCESSED_REQUEST_PROTOCOL = "lawb.bridge_operator_b3_processed_request.v1"
NOTIFICATION_ID_PROTOCOL = "lawb.workflow_result_notification_id.v1"
NOTIFICATION_STATE_FILE = "workflow_result_notifications.json"
PROCESSED_REQUEST_FILE = "processed_requests.jsonl"

COMPLETED_SUCCESS = "completed_success"
COMPLETED_NON_SUCCESS = "completed_non_success"
ATTENTION_REQUIRED = "attention_required"

SUBMITTING = "submitting"
SUBMITTED = "submitted"
AMBIGUOUS = "ambiguous"

WINDOWS_APP_NOTIFICATION_HELPER_PROTOCOL = (
    "lawb.windows_app_notification_helper.v1"
)
WINDOWS_APP_NOTIFICATION_HELPER_RELATIVE_PATH = Path(
    "LocalAIWorkbench/NotificationAdapterV1/app/LocalAIWorkbench.NotificationHelper.exe"
)


@dataclass(frozen=True)
class NotificationSubmission:
    """The observable result of asking a desktop surface to show a notification."""

    status: str
    detail: str
    api_submission_confirmed: bool
    user_visible_delivery_confirmed: bool = False
    operation: str | None = None
    stage: str | None = None
    bootstrap_status: str | None = None
    register_status: str | None = None
    notification_setting: str | None = None
    show_attempted: bool = False
    show_returned: bool = False
    cleanup_status: str | None = None
    error_type: str | None = None
    error_hresult: str | None = None
    cleanup_error_type: str | None = None
    cleanup_error_hresult: str | None = None


def submit_windows_desktop_notification(
    title: str,
    message: str,
) -> NotificationSubmission:
    """Submit through the bounded Windows App SDK helper without claiming visibility."""
    if os.name != "nt":
        return NotificationSubmission(AMBIGUOUS, "windows_required", False)

    helper_path = _windows_app_notification_helper_path()
    if helper_path is None:
        return NotificationSubmission(
            AMBIGUOUS,
            "windows_app_notification_helper_path_unavailable",
            False,
        )
    if not helper_path.is_file():
        return NotificationSubmission(
            AMBIGUOUS,
            "windows_app_notification_helper_not_found",
            False,
        )

    title_b64 = base64.b64encode(title.encode("utf-8")).decode("ascii")
    message_b64 = base64.b64encode(message.encode("utf-8")).decode("ascii")
    try:
        completed = subprocess.run(
            [
                str(helper_path),
                "--title-base64",
                title_b64,
                "--message-base64",
                message_b64,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(helper_path.parent),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        progress, _ = _parse_windows_app_notification_helper_output(
            _text_output(error.stdout)
        )
        if progress is not None and progress.get("event_name") == "show_attempted":
            return _submission_from_show_attempted_progress(progress)
        return NotificationSubmission(
            AMBIGUOUS,
            "windows_app_notification_helper_timeout",
            False,
            operation="submit",
            stage="startup",
        )
    except OSError:
        return NotificationSubmission(
            AMBIGUOUS,
            "windows_app_notification_helper_start_failed",
            False,
            operation="submit",
            stage="bootstrap",
            bootstrap_status="failed",
        )

    progress, receipt = _parse_windows_app_notification_helper_output(completed.stdout)
    submission = _submission_from_windows_app_notification_receipt(
        receipt,
        completed.returncode,
    )
    if submission is not None:
        return submission
    if progress is not None and progress.get("event_name") == "show_attempted":
        return _submission_from_show_attempted_progress(progress)
    if completed.returncode != 0:
        return NotificationSubmission(
            AMBIGUOUS,
            "windows_app_notification_helper_nonzero_exit",
            False,
            operation="submit",
            stage="startup",
        )
    return NotificationSubmission(
        AMBIGUOUS,
        "windows_app_notification_helper_receipt_invalid",
        False,
        operation="submit",
        stage="startup",
    )


def _windows_app_notification_helper_path() -> Path | None:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    return Path(local_app_data) / WINDOWS_APP_NOTIFICATION_HELPER_RELATIVE_PATH


def _parse_windows_app_notification_helper_output(
    raw: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    progress = None
    receipt = None
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except (TypeError, json.JSONDecodeError):
            return None, None
        if (
            not isinstance(payload, dict)
            or payload.get("protocol") != WINDOWS_APP_NOTIFICATION_HELPER_PROTOCOL
        ):
            return None, None
        if payload.get("record_type") == "event":
            if progress is not None:
                return None, None
            progress = payload
        elif payload.get("record_type") == "receipt":
            if receipt is not None:
                return None, None
            receipt = payload
        else:
            return None, None
    return progress, receipt


def _submission_from_windows_app_notification_receipt(
    receipt: dict[str, Any] | None,
    returncode: int,
) -> NotificationSubmission | None:
    if receipt is None or receipt.get("operation") != "submit":
        return None
    status = receipt.get("status")
    detail = receipt.get("detail")
    stage = receipt.get("stage")
    bootstrap_status = receipt.get("bootstrap_status")
    register_status = receipt.get("register_status")
    setting = receipt.get("notification_setting")
    cleanup_status = receipt.get("cleanup_status")
    show_attempted = receipt.get("show_attempted")
    show_returned = receipt.get("show_returned")
    api_confirmed = receipt.get("api_submission_confirmed")
    visible_confirmed = receipt.get("user_visible_delivery_confirmed")
    optional_strings = (
        "error_type",
        "error_hresult",
        "cleanup_error_type",
        "cleanup_error_hresult",
    )
    if (
        status not in {SUBMITTED, AMBIGUOUS}
        or not isinstance(detail, str)
        or not detail
        or not isinstance(stage, str)
        or bootstrap_status
        not in {"not_attempted", "started", "succeeded", "failed", "unsupported"}
        or register_status not in {"not_attempted", "succeeded", "failed"}
        or (setting is not None and not isinstance(setting, str))
        or cleanup_status not in {"not_attempted", "started", "succeeded", "failed"}
        or type(show_attempted) is not bool
        or type(show_returned) is not bool
        or type(api_confirmed) is not bool
        or visible_confirmed is not False
        or any(
            receipt.get(key) is not None and not isinstance(receipt.get(key), str)
            for key in optional_strings
        )
        or (show_returned and not show_attempted)
        or (api_confirmed and not show_returned)
    ):
        return None
    if status == SUBMITTED:
        if (
            returncode != 0
            or not api_confirmed
            or not show_returned
            or cleanup_status != "succeeded"
        ):
            return None
    elif returncode == 0:
        return None

    return NotificationSubmission(
        status,
        detail,
        api_confirmed,
        False,
        operation="submit",
        stage=stage,
        bootstrap_status=bootstrap_status,
        register_status=register_status,
        notification_setting=setting,
        show_attempted=show_attempted,
        show_returned=show_returned,
        cleanup_status=cleanup_status,
        error_type=receipt.get("error_type"),
        error_hresult=receipt.get("error_hresult"),
        cleanup_error_type=receipt.get("cleanup_error_type"),
        cleanup_error_hresult=receipt.get("cleanup_error_hresult"),
    )


def _submission_from_show_attempted_progress(
    progress: dict[str, Any],
) -> NotificationSubmission:
    return NotificationSubmission(
        AMBIGUOUS,
        "windows_app_notification_show_outcome_unknown",
        False,
        False,
        operation="submit",
        stage="show",
        bootstrap_status=(
            progress.get("bootstrap_status")
            if isinstance(progress.get("bootstrap_status"), str)
            else None
        ),
        register_status=(
            progress.get("register_status")
            if isinstance(progress.get("register_status"), str)
            else None
        ),
        notification_setting=(
            progress.get("notification_setting")
            if isinstance(progress.get("notification_setting"), str)
            else None
        ),
        show_attempted=True,
        show_returned=False,
        cleanup_status="not_attempted",
    )


def _text_output(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def process_new_workflow_result_notifications(
    *,
    state_dir: str | Path,
    operator_session_id: str,
    submitter: Callable[[str, str], NotificationSubmission] | None = None,
    now_utc: Callable[[], datetime] | datetime | None = None,
) -> dict[str, Any]:
    """Notify only for complete processed-request records after activation."""
    state_root = Path(state_dir)
    state_path = state_root / NOTIFICATION_STATE_FILE
    processed_path = state_root / PROCESSED_REQUEST_FILE
    result = {
        "status": "idle",
        "activation_created": False,
        "records_considered": 0,
        "submitted_count": 0,
        "ambiguous_count": 0,
        "last_notification_id": None,
    }
    try:
        raw = processed_path.read_bytes() if processed_path.exists() else b""
    except OSError:
        result["status"] = "source_unavailable"
        result["ambiguous_count"] = 1
        return result

    if not state_path.exists():
        state = _new_state(raw, _now(now_utc))
        try:
            write_exclusive_json(state_path, state)
        except FileExistsError:
            pass
        except (OSError, LifecycleEvidenceError):
            result["status"] = "activation_write_failed"
            result["ambiguous_count"] = 1
            return result
        else:
            result["status"] = "activated"
            result["activation_created"] = True
            return result

    try:
        state = _load_state(state_path)
    except (OSError, ValueError, LifecycleEvidenceError):
        result["status"] = "notification_state_invalid"
        result["ambiguous_count"] = 1
        return result

    if state["source_status"] != "ok":
        result["status"] = "source_history_ambiguous"
        result["ambiguous_count"] = 1
        return result
    recovered_submissions = 0
    recovered_at = _format_time(_now(now_utc))
    for entry in state["notifications"].values():
        if entry["status"] == SUBMITTING:
            entry["status"] = AMBIGUOUS
            entry["detail"] = "prior_submission_outcome_unknown"
            entry["api_submission_confirmed"] = False
            entry["user_visible_delivery_confirmed"] = False
            entry["updated_at_utc"] = recovered_at
            recovered_submissions += 1
    if recovered_submissions:
        try:
            _persist_state(state_path, state, operator_session_id)
        except (OSError, LifecycleEvidenceError):
            result["status"] = "notification_state_write_failed"
            result["ambiguous_count"] = recovered_submissions
            return result
        result["ambiguous_count"] += recovered_submissions

    scan_offset = state["scan_offset"]
    if len(raw) < scan_offset or _sha256(raw[:scan_offset]) != state["source_prefix_sha256"]:
        result["status"] = "source_history_ambiguous"
        result["ambiguous_count"] = 1
        _record_source_ambiguity(
            state_path,
            state,
            operator_session_id,
            _now(now_utc),
        )
        return result
    tail = raw[scan_offset:]
    if tail and not tail.endswith(b"\n"):
        result["status"] = "source_append_incomplete"
        result["ambiguous_count"] = 1
        return result

    submit = submitter or submit_windows_desktop_notification
    offset = scan_offset
    for encoded_line in tail.splitlines(keepends=True):
        next_offset = offset + len(encoded_line)
        try:
            record = _parse_eligible_record(encoded_line)
        except ValueError:
            result["status"] = "source_record_invalid"
            result["ambiguous_count"] += 1
            return result
        notification_id = notification_identity(record)
        result["records_considered"] += 1
        result["last_notification_id"] = notification_id
        existing = state["notifications"].get(notification_id)
        if existing is not None:
            state["scan_offset"] = next_offset
            state["source_prefix_sha256"] = _sha256(raw[:next_offset])
            state["last_scan_at_utc"] = _format_time(_now(now_utc))
            try:
                _persist_state(state_path, state, operator_session_id)
            except (OSError, LifecycleEvidenceError):
                result["status"] = "notification_state_write_failed"
                result["ambiguous_count"] += 1
                return result
            offset = next_offset
            continue

        classification = classify_processed_request(record)
        title, message = notification_text(record, classification)
        submitted_at = _format_time(_now(now_utc))
        state["notifications"][notification_id] = {
            "notification_id": notification_id,
            "target_repository": record["target_repository"],
            "request_id": record["request_id"],
            "target_issue": record["target_issue"],
            "classification": classification,
            "status": SUBMITTING,
            "detail": "submission_started_delivery_unknown",
            "api_submission_confirmed": False,
            "user_visible_delivery_confirmed": False,
            "operation": "submit",
            "stage": "adapter",
            "bootstrap_status": None,
            "register_status": None,
            "notification_setting": None,
            "show_attempted": False,
            "show_returned": False,
            "cleanup_status": None,
            "error_type": None,
            "error_hresult": None,
            "cleanup_error_type": None,
            "cleanup_error_hresult": None,
            "submission_started_at_utc": submitted_at,
            "updated_at_utc": submitted_at,
            "title": title,
            "message": message,
        }
        state["scan_offset"] = next_offset
        state["source_prefix_sha256"] = _sha256(raw[:next_offset])
        state["last_scan_at_utc"] = submitted_at
        try:
            _persist_state(state_path, state, operator_session_id)
        except (OSError, LifecycleEvidenceError):
            result["status"] = "notification_state_write_failed"
            result["ambiguous_count"] += 1
            return result

        try:
            submission = submit(title, message)
        except Exception:
            submission = NotificationSubmission(
                AMBIGUOUS,
                "notification_submitter_raised",
                False,
                False,
            )
        if not isinstance(submission, NotificationSubmission) or submission.status not in {
            SUBMITTED,
            AMBIGUOUS,
        }:
            submission = NotificationSubmission(
                AMBIGUOUS,
                "notification_submitter_result_invalid",
                False,
                False,
            )
        entry = state["notifications"][notification_id]
        entry["status"] = submission.status
        entry["detail"] = submission.detail
        entry["api_submission_confirmed"] = submission.api_submission_confirmed
        entry["user_visible_delivery_confirmed"] = False
        entry["operation"] = submission.operation
        entry["stage"] = submission.stage
        entry["bootstrap_status"] = submission.bootstrap_status
        entry["register_status"] = submission.register_status
        entry["notification_setting"] = submission.notification_setting
        entry["show_attempted"] = submission.show_attempted
        entry["show_returned"] = submission.show_returned
        entry["cleanup_status"] = submission.cleanup_status
        entry["error_type"] = submission.error_type
        entry["error_hresult"] = submission.error_hresult
        entry["cleanup_error_type"] = submission.cleanup_error_type
        entry["cleanup_error_hresult"] = submission.cleanup_error_hresult
        entry["updated_at_utc"] = _format_time(_now(now_utc))
        try:
            _persist_state(state_path, state, operator_session_id)
        except (OSError, LifecycleEvidenceError):
            result["status"] = "submission_outcome_persist_failed"
            result["ambiguous_count"] += 1
            return result
        if submission.status == SUBMITTED:
            result["submitted_count"] += 1
        else:
            result["ambiguous_count"] += 1
        offset = next_offset

    if result["ambiguous_count"]:
        result["status"] = AMBIGUOUS
    elif result["submitted_count"]:
        result["status"] = SUBMITTED
    return result


def notification_identity(record: dict[str, Any]) -> str:
    """Return a deterministic identity bound to the settled request."""
    identity = json.dumps(
        [
            NOTIFICATION_ID_PROTOCOL,
            record["target_repository"],
            record["request_id"],
            record["target_issue"],
            record["target_dispatch_request_id"],
        ],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(identity).hexdigest()


def classify_processed_request(record: dict[str, Any]) -> str:
    """Map a validated durable settlement to notification-only meaning."""
    if record["result_verified"] is True:
        if record["terminal_result"] == "success":
            return COMPLETED_SUCCESS
        if record["terminal_result"] in {"failure", "blocked"}:
            return COMPLETED_NON_SUCCESS
    if (
        record["result_verified"] is False
        and record.get("completion_source") == "dispatcher_outcome"
        and record.get("dispatcher_execution_reach") == "rejected_before_runner"
        and record["terminal_result"] == "blocked"
    ):
        return ATTENTION_REQUIRED
    raise ValueError("processed_request_not_notification_eligible")


def notification_text(
    record: dict[str, Any],
    classification: str,
) -> tuple[str, str]:
    """Build bounded text that never claims ChatGPT technical acceptance."""
    issue = record["target_issue"]
    request_id = record["request_id"]
    if classification == COMPLETED_SUCCESS:
        title = "Local AI Workbench: execution completed"
        lead = "Execution completed successfully"
    elif classification == COMPLETED_NON_SUCCESS:
        title = "Local AI Workbench: execution needs attention"
        lead = "Execution completed with a non-success result"
    elif classification == ATTENTION_REQUIRED:
        title = "Local AI Workbench: attention required"
        lead = "A structured pre-Runner rejection requires attention; no Runner or Codex success is claimed"
    else:
        raise ValueError("notification_classification_invalid")
    return (
        title,
        f"{lead} for Issue #{issue} ({request_id}). "
        "Execution result is awaiting ChatGPT review.",
    )


def _new_state(raw: bytes, now: datetime) -> dict[str, Any]:
    offset = len(raw)
    return {
        "protocol": NOTIFICATION_STATE_PROTOCOL,
        "activated_at_utc": _format_time(now),
        "activation_offset": offset,
        "scan_offset": offset,
        "source_prefix_sha256": _sha256(raw),
        "source_status": "ok",
        "last_scan_at_utc": _format_time(now),
        "notifications": {},
    }


def _load_state(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("notification_state_invalid") from error
    if not isinstance(payload, dict) or payload.get("protocol") != NOTIFICATION_STATE_PROTOCOL:
        raise ValueError("notification_state_invalid")
    for key in ("activation_offset", "scan_offset"):
        if type(payload.get(key)) is not int or payload[key] < 0:
            raise ValueError("notification_state_invalid")
    if payload["scan_offset"] < payload["activation_offset"]:
        raise ValueError("notification_state_invalid")
    prefix_hash = payload.get("source_prefix_sha256")
    if not isinstance(prefix_hash, str) or len(prefix_hash) != 64:
        raise ValueError("notification_state_invalid")
    if payload.get("source_status") not in {"ok", "ambiguous"}:
        raise ValueError("notification_state_invalid")
    notifications = payload.get("notifications")
    if not isinstance(notifications, dict):
        raise ValueError("notification_state_invalid")
    for notification_id, entry in notifications.items():
        if (
            not isinstance(notification_id, str)
            or len(notification_id) != 64
            or not isinstance(entry, dict)
            or entry.get("notification_id") != notification_id
            or entry.get("status") not in {SUBMITTING, SUBMITTED, AMBIGUOUS}
        ):
            raise ValueError("notification_state_invalid")
    return payload


def _parse_eligible_record(encoded_line: bytes) -> dict[str, Any]:
    try:
        line = encoded_line.decode("utf-8").strip()
        payload = json.loads(line, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("processed_request_invalid") from error
    if not isinstance(payload, dict):
        raise ValueError("processed_request_invalid")
    required = (
        "request_id",
        "target_repository",
        "target_issue",
        "target_dispatch_request_id",
        "result_verified",
        "terminal_result",
        "terminal_settlement",
    )
    if (
        payload.get("protocol") != PROCESSED_REQUEST_PROTOCOL
        or payload.get("lifecycle_state") != "CONSUMED"
        or not all(key in payload for key in required)
        or not isinstance(payload["request_id"], str)
        or not payload["request_id"]
        or not isinstance(payload["target_repository"], str)
        or not payload["target_repository"]
        or type(payload["target_issue"]) is not int
        or payload["target_issue"] <= 0
        or not isinstance(payload["target_dispatch_request_id"], str)
        or not payload["target_dispatch_request_id"]
        or payload["terminal_result"] not in {"success", "failure", "blocked"}
        or payload["terminal_settlement"]
        != (
            "settled_success"
            if payload["terminal_result"] == "success"
            else "settled_non_success"
        )
    ):
        raise ValueError("processed_request_invalid")
    classify_processed_request(payload)
    return payload


def _persist_state(path: Path, state: dict[str, Any], operator_session_id: str) -> None:
    write_durable_json(path, state, operator_session_id=operator_session_id)


def _record_source_ambiguity(
    path: Path,
    state: dict[str, Any],
    operator_session_id: str,
    now: datetime,
) -> None:
    state["source_status"] = "ambiguous"
    state["last_scan_at_utc"] = _format_time(now)
    try:
        _persist_state(path, state, operator_session_id)
    except (OSError, LifecycleEvidenceError):
        pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError("duplicate_json_key")
        payload[key] = value
    return payload


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _now(value: Callable[[], datetime] | datetime | None) -> datetime:
    current = value() if callable(value) else value
    current = current or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )

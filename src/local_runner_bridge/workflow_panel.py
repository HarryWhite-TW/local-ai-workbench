"""Localhost-only, read-only Workflow lifecycle and activity panel."""

from __future__ import annotations

import argparse
import json
import os
import threading
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

from local_runner_bridge.bridge_operator_b3 import (
    DEFAULT_REPOSITORY,
    FAILURE_PROTOCOL,
    read_processed_request_records,
)
from local_runner_bridge.bridge_operator_lifecycle_state import (
    DISPATCHED_NOT_LOCALLY_SETTLED,
    PREPARED,
    PROCESSED,
    REJECTED_BEFORE_RUNNER,
    LifecycleEvidenceError,
    load_in_flight,
    load_review_candidate,
    parse_utc,
)
from local_runner_bridge.workflow_observability import (
    EVENT_PROTOCOL,
    MAX_REPLAY_EVENTS,
    EventStore,
    ObservationError,
    ObservationHTTPServer,
    ObservationRequestHandler,
    validate_request_id,
)


PANEL_PROTOCOL = "lawb.workflow_panel.v1"
STATE_PROTOCOL = "lawb.bridge_operator_b3_state.v1"
HEARTBEAT_PROTOCOL = "lawb.bridge_operator_b3_heartbeat.v1"
MAX_STATE_FILE_BYTES = 1_048_576
MAX_PROCESSED_HISTORY_BYTES = 8_388_608
DEFAULT_HEARTBEAT_STALE_SECONDS = 90.0

_SAFE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,79}$")
_SCAN_RESULTS = {
    "eligible_request_detected",
    "expired_request_observed",
    "no_eligible_request",
    "scan_blocked",
}
_PICKUP_DECISIONS = {"ready_for_pickup", "not_eligible", "expired", "blocked"}
_OBSERVABLE_ACTIONS = {"maybe-status-check", "run-reviewbundle", "read-final-audit"}

_ASSET_ROUTES = {
    "/": ("workflow_panel.html", "text/html; charset=utf-8"),
    "/workflow_panel.js": ("workflow_panel.js", "text/javascript; charset=utf-8"),
    "/workflow_panel.css": ("workflow_panel.css", "text/css; charset=utf-8"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _read_source(path: Path, *, protocol: str) -> tuple[str, dict[str, Any] | None]:
    if not path.exists():
        return "missing", None
    try:
        size = path.stat().st_size
        if size > MAX_STATE_FILE_BYTES:
            return "invalid", None
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return "invalid", None
    if not isinstance(value, dict) or value.get("protocol") != protocol:
        return "invalid", None
    return "available", value


def _safe_text(value: Any, *, limit: int = 160) -> str | None:
    if not isinstance(value, str) or not value or len(value) > limit:
        return None
    if any(ord(character) < 32 for character in value):
        return None
    return value


def _safe_positive_integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def _safe_nonnegative_number(value: Any, *, maximum: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if 0 <= number <= maximum else None


def _safe_request_id(value: Any) -> str | None:
    try:
        return validate_request_id(value)
    except ObservationError:
        return None


def _safe_code(value: Any) -> str | None:
    return value if isinstance(value, str) and _SAFE_CODE_PATTERN.fullmatch(value) else None


def _parse_observed_time(value: Any) -> datetime | None:
    parsed = parse_utc(value)
    if parsed is not None:
        return parsed
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _inbox_scan_observation(
    heartbeat: dict[str, Any] | None,
) -> tuple[str, dict[str, Any] | None]:
    if heartbeat is None:
        return "missing", None
    keys = {
        "last_inbox_scan_at_utc",
        "last_inbox_scan_cycle",
        "last_inbox_scan_result",
        "last_inbox_scan_reason",
        "eligible_request_count",
        "last_inbox_request",
    }
    present = {key for key in keys if heartbeat.get(key) is not None}
    if not present:
        return "missing", None
    if present != keys - {"last_inbox_request"} and present != keys:
        return "invalid", None

    observed_at = _safe_text(heartbeat.get("last_inbox_scan_at_utc"), limit=64)
    cycle = _safe_positive_integer(heartbeat.get("last_inbox_scan_cycle"))
    result = heartbeat.get("last_inbox_scan_result")
    reason = _safe_code(heartbeat.get("last_inbox_scan_reason"))
    eligible_count = heartbeat.get("eligible_request_count")
    if (
        observed_at is None
        or parse_utc(observed_at) is None
        or cycle is None
        or result not in _SCAN_RESULTS
        or reason is None
        or isinstance(eligible_count, bool)
        or not isinstance(eligible_count, int)
        or not 0 <= eligible_count <= 1
    ):
        return "invalid", None

    request_value = heartbeat.get("last_inbox_request")
    request = None
    if request_value is not None:
        if not isinstance(request_value, dict):
            return "invalid", None
        request_id = _safe_request_id(request_value.get("request_id"))
        target_issue = _safe_positive_integer(request_value.get("target_issue"))
        action = request_value.get("requested_action")
        expires = _safe_text(request_value.get("expires"), limit=64)
        request_observed_at = _safe_text(
            request_value.get("observed_at_utc"), limit=64
        )
        decision = request_value.get("pickup_decision")
        request_reason = _safe_code(request_value.get("reason"))
        expires_time = _parse_observed_time(expires)
        if (
            request_id is None
            or target_issue is None
            or action not in _OBSERVABLE_ACTIONS
            or expires is None
            or expires_time is None
            or request_observed_at is None
            or parse_utc(request_observed_at) is None
            or decision not in _PICKUP_DECISIONS
            or request_reason is None
        ):
            return "invalid", None
        request = {
            "request_id": request_id,
            "issue_number": target_issue,
            "action": action,
            "observed_at_utc": request_observed_at,
            "expires_at_utc": expires_time.isoformat().replace("+00:00", "Z"),
            "pickup_decision": decision,
            "reason": request_reason,
        }
    if result in {"eligible_request_detected", "expired_request_observed"} and request is None:
        return "invalid", None
    if result == "eligible_request_detected" and eligible_count != 1:
        return "invalid", None
    if result != "eligible_request_detected" and eligible_count != 0:
        return "invalid", None
    return "available", {
        "observed_at_utc": observed_at,
        "cycle": cycle,
        "result": result,
        "reason": reason,
        "eligible_request_count": eligible_count,
        "request": request,
    }


def _age_seconds(value: Any, *, now: datetime) -> float | None:
    parsed = parse_utc(value)
    if parsed is None:
        return None
    return max(0.0, (now - parsed).total_seconds())


def _operator_health(
    heartbeat: dict[str, Any] | None,
    *,
    heartbeat_status: str,
    in_flight: dict[str, Any] | None,
    now: datetime,
) -> tuple[str, float | None, float]:
    if heartbeat is None:
        return ("offline" if heartbeat_status == "missing" else "unknown", None, DEFAULT_HEARTBEAT_STALE_SECONDS)
    age = _age_seconds(heartbeat.get("updated_at_utc"), now=now)
    interval = _safe_nonnegative_number(
        heartbeat.get("configured_poll_interval_seconds"), maximum=3600.0
    )
    stale_after = max(DEFAULT_HEARTBEAT_STALE_SECONDS, (interval or 30.0) * 3)
    if in_flight is not None:
        timeout = _safe_nonnegative_number(
            heartbeat.get("configured_timeout_seconds"), maximum=86_400.0
        )
        if timeout is not None:
            stale_after = max(stale_after, timeout + (interval or 30.0))
    status = _safe_text(heartbeat.get("status"))
    if status in {"stopped", "max_cycles_completed"}:
        return "offline", age, stale_after
    if age is None:
        return "unknown", None, stale_after
    if age > stale_after:
        return "stale", age, stale_after
    return "online", age, stale_after


def _valid_operator_source(value: dict[str, Any] | None, *, heartbeat: bool) -> bool:
    if value is None:
        return False
    counter_key = "cycle" if heartbeat else "cycles_completed"
    counter = value.get(counter_key)
    return (
        _safe_text(value.get("status")) is not None
        and _safe_text(value.get("mode")) is not None
        and parse_utc(value.get("updated_at_utc")) is not None
        and isinstance(counter, int)
        and not isinstance(counter, bool)
        and counter >= 0
    )


def _operator_state(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "status": _safe_text(value.get("status")),
        "mode": _safe_text(value.get("mode")),
        "repository": _safe_text(value.get("repo")),
        "cycles_completed": value.get("cycles_completed")
        if isinstance(value.get("cycles_completed"), int)
        and not isinstance(value.get("cycles_completed"), bool)
        and value["cycles_completed"] >= 0
        else None,
        "updated_at_utc": _safe_text(value.get("updated_at_utc")),
    }


def _heartbeat_state(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "status": _safe_text(value.get("status")),
        "mode": _safe_text(value.get("mode")),
        "cycle": value.get("cycle")
        if isinstance(value.get("cycle"), int)
        and not isinstance(value.get("cycle"), bool)
        and value["cycle"] >= 0
        else None,
        "updated_at_utc": _safe_text(value.get("updated_at_utc")),
        "configured_poll_interval_seconds": _safe_nonnegative_number(
            value.get("configured_poll_interval_seconds"), maximum=3600.0
        ),
        "configured_timeout_seconds": _safe_nonnegative_number(
            value.get("configured_timeout_seconds"), maximum=86_400.0
        ),
    }


def _in_flight_lifecycle(in_flight: dict[str, Any]) -> dict[str, str]:
    stage = in_flight["stage"]
    terminal = in_flight.get("terminal_evidence")
    terminal_result = terminal.get("result") if isinstance(terminal, dict) else None
    if stage == REJECTED_BEFORE_RUNNER or terminal_result in {"failure", "blocked"}:
        visible_stage = "BLOCKED_OR_FAILED"
    elif stage == PROCESSED and terminal_result == "success":
        visible_stage = (
            "WAITING_FOR_CHATGPT_REVIEW"
            if in_flight.get("action") == "run-reviewbundle"
            else "COMPLETED_OR_LAST_COMPLETED"
        )
    elif stage == PREPARED:
        visible_stage = "DISPATCHING"
    else:
        visible_stage = "RUNNING"
    return {
        "stage": visible_stage,
        "certainty": "verified",
        "basis": f"in_flight:{stage}",
    }


def _read_processed_source(
    path: Path, *, repository: str
) -> tuple[str, dict[str, dict[str, Any]]]:
    if not path.exists():
        return "missing", {}
    try:
        if path.stat().st_size > MAX_PROCESSED_HISTORY_BYTES:
            return "invalid", {}
        return "available", read_processed_request_records(path, repository=repository)
    except (OSError, UnicodeError, ValueError):
        return "invalid", {}


def _record_time(record: dict[str, Any]) -> datetime | None:
    for key in ("terminal_observed_at_utc", "processed_at_utc"):
        parsed = parse_utc(record.get(key))
        if parsed is not None:
            return parsed
    return None


def _latest_terminal_record(
    records: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    candidates = [
        record
        for record in records.values()
        if record.get("terminal_result") in {"success", "failure", "blocked"}
        and _record_time(record) is not None
    ]
    return max(
        candidates,
        key=lambda record: _record_time(record)
        or datetime.min.replace(tzinfo=timezone.utc),
        default=None,
    )


def _processed_lifecycle(record: dict[str, Any]) -> dict[str, str]:
    if record["terminal_result"] in {"failure", "blocked"}:
        stage = "BLOCKED_OR_FAILED"
    elif record.get("requested_action") == "run-reviewbundle":
        stage = "WAITING_FOR_CHATGPT_REVIEW"
    else:
        stage = "COMPLETED_OR_LAST_COMPLETED"
    return {
        "stage": stage,
        "certainty": "verified",
        "basis": f"processed_request:{record['terminal_result']}",
    }


def _valid_failure(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    reason = _safe_text(value.get("reason"))
    failed_at = _safe_text(value.get("failed_at_utc"))
    request_id_value = value.get("request_id")
    request_id = None if request_id_value is None else _safe_request_id(request_id_value)
    if (
        reason is None
        or failed_at is None
        or parse_utc(failed_at) is None
        or (request_id_value is not None and request_id is None)
        or value.get("current_failure_recorded") is not True
        or value.get("last_failure_json_applies_to_current_run") is not True
        or value.get("last_failure_json_status") != "current_failure"
    ):
        return None
    return {
        "request_id": request_id,
        "reason": reason,
        "failed_at_utc": failed_at,
    }


def _failure_is_current(
    failure: dict[str, Any],
    *,
    in_flight: dict[str, Any] | None,
    state: dict[str, Any] | None,
    heartbeat: dict[str, Any] | None,
    processed_records: dict[str, dict[str, Any]],
) -> bool:
    request_id = failure["request_id"]
    if in_flight is not None:
        return request_id == in_flight["request_id"]
    status_values = {
        _safe_text(source.get("status"))
        for source in (state, heartbeat)
        if source is not None
    }
    if "blocked" not in status_values:
        return False
    last_request_id = _safe_request_id(state.get("last_request_id")) if state else None
    if request_id is not None and request_id != last_request_id:
        return False
    processed = processed_records.get(request_id) if request_id is not None else None
    processed_at = _record_time(processed) if processed is not None else None
    failed_at = parse_utc(failure["failed_at_utc"])
    return processed_at is None or failed_at is None or processed_at < failed_at


def _review_candidate_matches(
    candidate: dict[str, Any] | None, record: dict[str, Any] | None
) -> bool:
    if candidate is None or record is None:
        return False
    return all(
        (
            candidate.get("target_repository") == (record.get("target_repository") or DEFAULT_REPOSITORY),
            candidate.get("target_issue") == record.get("target_issue"),
            candidate.get("dispatch_request_id") == record.get("target_dispatch_request_id"),
            candidate.get("action") == record.get("requested_action"),
            candidate.get("branch") == record.get("expected_branch"),
            candidate.get("expected_head") == record.get("expected_head"),
        )
    )


def _safe_comment_id(value: Any) -> str | None:
    if not isinstance(value, str) or not value.isascii() or not value.isdigit():
        return None
    return value if 1 <= len(value) <= 19 and not value.startswith("0") else None


def _warning_projection(
    failure: dict[str, Any] | None, request_events: list[dict[str, Any]]
) -> dict[str, Any]:
    if failure is not None:
        return {
            "status": "available",
            "code": failure["reason"],
            "source": "current_failure",
            "observed_at_utc": failure["failed_at_utc"],
        }
    for event in reversed(request_events):
        if event["kind"] not in {
            "observability.source_warning",
            "codex.turn.failed",
            "codex.command.failed",
            "codex.error",
        }:
            continue
        reason = _safe_text(event["payload"].get("reason"))
        return {
            "status": "available",
            "code": reason or event["kind"],
            "source": f"workflow_observation:{event['kind']}",
            "observed_at_utc": event["observed_at_utc"],
        }
    return {
        "status": "unavailable",
        "code": None,
        "source": None,
        "observed_at_utc": None,
    }


def _review_projection(
    record: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
    warning: dict[str, Any],
) -> dict[str, Any]:
    evidence_pointer = None
    evidence_summary = None
    if _review_candidate_matches(candidate, record):
        comment_id = _safe_comment_id(candidate.get("review_bundle_comment_id"))
        if comment_id is not None:
            evidence_pointer = f"issue_comment:{comment_id}"
            evidence_summary = (
                "Trusted review bundle; candidate manifest "
                f"{candidate['candidate_manifest_fingerprint']}"
            )
    if evidence_pointer is None and record is not None:
        comment_id = _safe_comment_id(record.get("target_result_comment_id"))
        if comment_id is not None:
            evidence_pointer = f"issue_comment:{comment_id}"
            evidence_summary = "Trusted terminal result"
    return {
        "warning_or_error": warning,
        "changed_files": {"status": "unavailable", "items": []},
        "test_summary": {"status": "unavailable", "summary": None},
        "evidence": {
            "status": "available" if evidence_pointer else "unavailable",
            "pointer": evidence_pointer,
            "summary": evidence_summary,
        },
    }


def _scan_lifecycle(scan: dict[str, Any]) -> dict[str, str]:
    stages = {
        "eligible_request_detected": "REQUEST_DETECTED",
        "expired_request_observed": "EXPIRED",
        "no_eligible_request": "NO_REQUEST_DETECTED",
        "scan_blocked": "BLOCKED_OR_FAILED",
    }
    return {
        "stage": stages[scan["result"]],
        "certainty": "observed",
        "basis": f"inbox_scan:{scan['result']}",
    }


def _next_action(stage: str, operator_health: str) -> str:
    if stage == "RUNNING":
        return "Task is running. You do not need to do anything."
    if stage == "DISPATCHING":
        return "The request is starting now. You do not need to do anything."
    if operator_health == "stale":
        return "Operator has not checked for work recently."
    if operator_health in {"offline", "unknown"}:
        return "Operator is not available, so new work will not start automatically."
    if stage == "WAITING_FOR_CHATGPT_REVIEW":
        return "Task finished and is waiting for ChatGPT review."
    if stage == "COMPLETED_OR_LAST_COMPLETED":
        return "Task completed. No action is required unless ChatGPT asks for a decision."
    if stage == "BLOCKED_OR_FAILED":
        return "The workflow is blocked or failed. Review the warning below."
    if stage == "REQUEST_DETECTED":
        return "A request was detected and is waiting to start."
    if stage == "EXPIRED":
        return "The observed request expired and will not start."
    if stage == "NO_REQUEST_DETECTED":
        return "Everything is ready. The last check found no request, so you do not need to do anything."
    if stage == "CHECKING_FOR_WORK":
        return "The Operator is checking for work now."
    return "The current request state is unknown. Wait for the next check or review the warning below."


def _system_projection(
    *,
    operator_health: str,
    lifecycle_stage: str,
    diagnostics: list[str],
    state: dict[str, Any] | None,
) -> dict[str, str]:
    operator_status = _safe_text((state or {}).get("status"))
    if operator_health in {"offline", "stale", "unknown"}:
        readiness = "unavailable"
    elif diagnostics or operator_status in {"blocked", "failed"}:
        readiness = "degraded"
    else:
        readiness = "ready"
    return {
        "readiness": readiness,
        "workflow": readiness,
        "operator": operator_health,
        "panel": "online",
        "next_action": _next_action(lifecycle_stage, operator_health),
    }


def build_workflow_snapshot(
    state_dir: Path,
    store: EventStore,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a bounded projection without treating missing evidence as completion."""

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    diagnostics: list[str] = []
    state_status, state = _read_source(state_dir / "state.json", protocol=STATE_PROTOCOL)
    heartbeat_status, heartbeat = _read_source(
        state_dir / "heartbeat.json", protocol=HEARTBEAT_PROTOCOL
    )
    if state_status == "available" and not _valid_operator_source(state, heartbeat=False):
        state_status, state = "invalid", None
    if heartbeat_status == "available" and not _valid_operator_source(
        heartbeat, heartbeat=True
    ):
        heartbeat_status, heartbeat = "invalid", None
    for name, status in (("state", state_status), ("heartbeat", heartbeat_status)):
        if status == "invalid":
            diagnostics.append(f"{name}_evidence_invalid")
    scan_status, inbox_scan = _inbox_scan_observation(heartbeat)
    if scan_status == "invalid":
        diagnostics.append("inbox_scan_observation_invalid")

    repository = (
        _safe_text(state.get("repo")) if state is not None else None
    ) or DEFAULT_REPOSITORY
    processed_status, processed_records = _read_processed_source(
        state_dir / "processed_requests.jsonl",
        repository=repository,
    )
    if processed_status == "invalid":
        diagnostics.append("processed_request_evidence_invalid")

    failure_status, failure_value = _read_source(
        state_dir / "last_failure.json", protocol=FAILURE_PROTOCOL
    )
    failure = _valid_failure(failure_value)
    if failure_status == "available" and failure is None:
        failure_status = "invalid"
        diagnostics.append("last_failure_evidence_invalid")

    review_candidate_status = "missing"
    review_candidate: dict[str, Any] | None = None
    try:
        review_candidate = load_review_candidate(state_dir / "review_candidate.json")
        if review_candidate is not None:
            review_candidate_status = "available"
    except LifecycleEvidenceError:
        review_candidate_status = "invalid"
        diagnostics.append("review_candidate_evidence_invalid")

    in_flight_status = "missing"
    in_flight: dict[str, Any] | None = None
    try:
        in_flight = load_in_flight(state_dir / "in_flight.json")
        if in_flight is not None:
            in_flight_status = "available"
    except LifecycleEvidenceError:
        in_flight_status = "invalid"
        diagnostics.append("in_flight_evidence_invalid")

    events, event_diagnostics = store.read(limit=MAX_REPLAY_EVENTS)
    diagnostics.extend(f"observation_store:{item}" for item in event_diagnostics)

    processed_record = _latest_terminal_record(processed_records)

    operator_health, heartbeat_age_seconds, heartbeat_stale_after_seconds = (
        _operator_health(
            heartbeat,
            heartbeat_status=heartbeat_status,
            in_flight=in_flight,
            now=now,
        )
    )
    scan_age_seconds = (
        _age_seconds(inbox_scan.get("observed_at_utc"), now=now)
        if inbox_scan is not None
        else None
    )
    scan_is_recent = (
        inbox_scan is not None
        and operator_health == "online"
        and scan_age_seconds is not None
        and scan_age_seconds <= heartbeat_stale_after_seconds
    )
    observed_request = inbox_scan.get("request") if inbox_scan is not None else None
    processed_time = _record_time(processed_record) if processed_record is not None else None
    scan_time = (
        parse_utc(inbox_scan.get("observed_at_utc"))
        if inbox_scan is not None
        else None
    )
    observed_request_is_current = bool(
        scan_is_recent
        and observed_request is not None
        and (
            processed_record is None
            or (
                observed_request["request_id"] != processed_record.get("request_id")
                and scan_time is not None
                and (processed_time is None or scan_time >= processed_time)
            )
        )
    )

    request_id: str | None = None
    issue_number: int | None = None
    if in_flight is not None:
        request_id = in_flight["request_id"]
        issue_number = in_flight["target_issue"]
    elif observed_request_is_current:
        request_id = observed_request["request_id"]
        issue_number = observed_request["issue_number"]
    elif processed_record is not None:
        request_id = processed_record["request_id"]
        issue_number = _safe_positive_integer(processed_record.get("target_issue"))

    applicable_failure = (
        failure
        if failure is not None
        and _failure_is_current(
            failure,
            in_flight=in_flight,
            state=state,
            heartbeat=heartbeat,
            processed_records=processed_records,
        )
        else None
    )
    if in_flight_status == "invalid":
        lifecycle = {
            "stage": "UNKNOWN",
            "certainty": "unknown",
            "basis": "in_flight_evidence_invalid",
        }
        updated_at_utc = None
        terminal_result = None
    elif applicable_failure is not None:
        lifecycle = {
            "stage": "BLOCKED_OR_FAILED",
            "certainty": "verified",
            "basis": "current_failure",
        }
        updated_at_utc = applicable_failure["failed_at_utc"]
        terminal_result = None
        request_id = applicable_failure["request_id"] or request_id
    elif in_flight is not None:
        lifecycle = _in_flight_lifecycle(in_flight)
        updated_at_utc = in_flight["updated_at_utc"]
        terminal = in_flight.get("terminal_evidence")
        terminal_result = terminal.get("result") if isinstance(terminal, dict) else None
    elif observed_request_is_current:
        lifecycle = _scan_lifecycle(inbox_scan)
        updated_at_utc = observed_request["observed_at_utc"]
        terminal_result = None
    elif processed_record is not None:
        lifecycle = _processed_lifecycle(processed_record)
        updated_at_utc = _safe_text(processed_record.get("terminal_observed_at_utc"))
        terminal_result = processed_record["terminal_result"]
    elif scan_is_recent:
        lifecycle = _scan_lifecycle(inbox_scan)
        updated_at_utc = inbox_scan["observed_at_utc"]
        terminal_result = None
    elif "blocked" in {
        _safe_text(source.get("status"))
        for source in (state, heartbeat)
        if source is not None
    }:
        lifecycle = {
            "stage": "BLOCKED_OR_FAILED",
            "certainty": "verified",
            "basis": "operator_status:blocked",
        }
        updated_at_utc = _safe_text(
            (heartbeat or {}).get("updated_at_utc")
            or (state or {}).get("updated_at_utc")
        )
        terminal_result = None
    elif operator_health == "online" and _safe_text((heartbeat or {}).get("status")) == "polling":
        lifecycle = {
            "stage": "CHECKING_FOR_WORK",
            "certainty": "observed",
            "basis": "heartbeat:polling",
        }
        updated_at_utc = _safe_text(
            (heartbeat or {}).get("updated_at_utc")
            or (state or {}).get("updated_at_utc")
        )
        terminal_result = None
    else:
        lifecycle = {
            "stage": "UNKNOWN",
            "certainty": "unknown",
            "basis": "no_current_request_evidence",
        }
        updated_at_utc = None
        terminal_result = None

    action = None
    detected_at_utc = None
    expires_at_utc = None
    pickup_decision = None
    pickup_reason = None
    matching_observed_request = (
        observed_request
        if observed_request is not None
        and request_id is not None
        and observed_request["request_id"] == request_id
        else None
    )
    if in_flight is not None:
        action = _safe_text(in_flight.get("action"))
        detected_at_utc = (
            matching_observed_request["observed_at_utc"]
            if matching_observed_request is not None
            else _safe_text(in_flight.get("prepared_at_utc"))
        )
        expires_at_utc = (
            matching_observed_request["expires_at_utc"]
            if matching_observed_request is not None
            else None
        )
        pickup_decision = "picked_up"
        pickup_reason = (
            matching_observed_request["reason"]
            if matching_observed_request is not None
            else None
        )
    elif observed_request_is_current:
        action = observed_request["action"]
        detected_at_utc = observed_request["observed_at_utc"]
        expires_at_utc = observed_request["expires_at_utc"]
        pickup_decision = observed_request["pickup_decision"]
        pickup_reason = observed_request["reason"]
    elif processed_record is not None:
        action = _safe_text(processed_record.get("requested_action"))
        detected_at_utc = (
            matching_observed_request["observed_at_utc"]
            if matching_observed_request is not None
            else _safe_text(processed_record.get("processed_at_utc"))
        )
        expires_at_utc = (
            matching_observed_request["expires_at_utc"]
            if matching_observed_request is not None
            else None
        )
        pickup_decision = "completed"
        pickup_reason = (
            matching_observed_request["reason"]
            if matching_observed_request is not None
            else None
        )

    if failure_status == "available" and applicable_failure is None:
        failure_status = "historical_not_current"
    candidate_matches = _review_candidate_matches(review_candidate, processed_record)
    if review_candidate_status == "available" and not candidate_matches:
        review_candidate_status = "historical_or_unmatched"

    request_events = [event for event in events if event["request_id"] == request_id]
    latest_event = request_events[-1] if request_events else None
    matching_events = (
        [event for event in request_events if event["run_id"] == latest_event["run_id"]]
        if latest_event is not None
        else []
    )
    warning = _warning_projection(applicable_failure, request_events)
    review = _review_projection(processed_record, review_candidate, warning)
    global_latest_event = events[-1] if events else None
    system = _system_projection(
        operator_health=operator_health,
        lifecycle_stage=lifecycle["stage"],
        diagnostics=diagnostics,
        state=state,
    )

    return {
        "protocol": PANEL_PROTOCOL,
        "mode": "read_only",
        "bind": "loopback",
        "observed_at_utc": now.isoformat().replace("+00:00", "Z"),
        "system": system,
        "current_task": {
            "request_id": request_id,
            "issue_number": issue_number,
            "action": action,
            "detected_at_utc": detected_at_utc,
            "expires_at_utc": expires_at_utc,
            "pickup_decision": pickup_decision,
            "pickup_reason": pickup_reason,
            "lifecycle": lifecycle,
            "updated_at_utc": updated_at_utc,
            "terminal_result": terminal_result,
        },
        "operator": {
            "state": _operator_state(state),
            "heartbeat": _heartbeat_state(heartbeat),
            "activity": {
                "health": operator_health,
                "heartbeat_at_utc": _safe_text((heartbeat or {}).get("updated_at_utc")),
                "heartbeat_age_seconds": round(heartbeat_age_seconds, 1)
                if heartbeat_age_seconds is not None
                else None,
                "stale_after_seconds": round(heartbeat_stale_after_seconds, 1),
                "last_check_at_utc": inbox_scan.get("observed_at_utc")
                if inbox_scan is not None
                else None,
                "last_check_age_seconds": round(scan_age_seconds, 1)
                if scan_age_seconds is not None
                else None,
                "poll_interval_seconds": _safe_nonnegative_number(
                    (heartbeat or {}).get("configured_poll_interval_seconds"),
                    maximum=3600.0,
                ),
                "cycle": (heartbeat or {}).get("cycle")
                if heartbeat is not None
                else None,
                "scan_result": inbox_scan.get("result")
                if inbox_scan is not None
                else None,
                "scan_reason": inbox_scan.get("reason")
                if inbox_scan is not None
                else None,
                "eligible_request_count": inbox_scan.get("eligible_request_count")
                if inbox_scan is not None
                else None,
                "observation_status": scan_status,
            },
        },
        "observability": {
            "protocol": EVENT_PROTOCOL,
            "event_count": len(events),
            "request_event_count": len(matching_events),
            "latest_sequence": global_latest_event["sequence"] if global_latest_event else None,
            "run_id": latest_event["run_id"] if latest_event else None,
            "stream_url": f"/events?{urlencode({'follow': '1'})}",
        },
        "review": review,
        "source_status": {
            "state": state_status,
            "heartbeat": heartbeat_status,
            "inbox_scan_observation": scan_status,
            "in_flight": in_flight_status,
            "processed_requests": processed_status,
            "last_failure": failure_status,
            "review_candidate": review_candidate_status,
            "observation_store": "available" if store.path.exists() else "missing",
        },
        "diagnostics": list(dict.fromkeys(diagnostics)),
    }


class WorkflowPanelHTTPServer(ObservationHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        *,
        state_dir: Path,
        store: EventStore,
        asset_dir: Path,
        poll_interval: float = 0.1,
        heartbeat_interval: float = 10.0,
    ) -> None:
        self.state_dir = state_dir
        self.asset_dir = asset_dir
        super().__init__(
            server_address,
            store,
            poll_interval=poll_interval,
            heartbeat_interval=heartbeat_interval,
            handler_class=WorkflowPanelRequestHandler,
        )


class WorkflowPanelRequestHandler(ObservationRequestHandler):
    server_version = "LAWbWorkflowPanel/1"

    @property
    def panel_server(self) -> WorkflowPanelHTTPServer:
        return self.server  # type: ignore[return-value]

    def _write_panel_response(
        self,
        status: int,
        body: bytes,
        content_type: str,
        *,
        head_only: bool,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _handle_get(self, *, head_only: bool) -> None:
        path = urlsplit(self.path).path
        if path in {"/api/state", "/api/snapshot"}:
            snapshot = build_workflow_snapshot(
                self.panel_server.state_dir,
                self.panel_server.store,
            )
            body = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
            self._write_panel_response(
                200,
                body,
                "application/json; charset=utf-8",
                head_only=head_only,
            )
            return
        if path == "/health":
            body = json.dumps(
                {
                    "protocol": PANEL_PROTOCOL,
                    "status": "ready",
                    "mode": "read_only",
                    "bind": "loopback",
                    "observation_protocol": EVENT_PROTOCOL,
                },
                separators=(",", ":"),
            ).encode("utf-8")
            self._write_panel_response(
                200,
                body,
                "application/json; charset=utf-8",
                head_only=head_only,
            )
            return
        asset = _ASSET_ROUTES.get(path)
        if asset is not None:
            filename, content_type = asset
            try:
                body = (self.panel_server.asset_dir / filename).read_bytes()
            except OSError:
                self._write_panel_response(
                    500,
                    b'{"error":"asset_unavailable"}',
                    "application/json; charset=utf-8",
                    head_only=head_only,
                )
                return
            self._write_panel_response(
                200,
                body,
                content_type,
                head_only=head_only,
            )
            return
        super()._handle_get(head_only=head_only)


def create_workflow_panel_server(
    state_dir: str | os.PathLike[str],
    store_path: str | os.PathLike[str],
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    asset_dir: str | os.PathLike[str] | None = None,
    poll_interval: float = 0.1,
    heartbeat_interval: float = 10.0,
) -> WorkflowPanelHTTPServer:
    if host != "127.0.0.1":
        raise ObservationError("panel_host_must_be_ipv4_loopback")
    if isinstance(port, bool) or not 0 <= port <= 65_535:
        raise ObservationError("invalid_panel_port")
    state_root = Path(state_dir)
    event_path = Path(store_path)
    assets = Path(asset_dir) if asset_dir is not None else Path(__file__).resolve().parent
    if not state_root.is_absolute():
        raise ObservationError("panel_state_dir_must_be_absolute")
    if not event_path.is_absolute():
        raise ObservationError("event_store_path_must_be_absolute")
    if not assets.is_absolute():
        raise ObservationError("panel_asset_dir_must_be_absolute")
    missing_assets = [name for name, _ in _ASSET_ROUTES.values() if not (assets / name).is_file()]
    if missing_assets:
        raise ObservationError("panel_assets_missing")
    return WorkflowPanelHTTPServer(
        (host, port),
        state_dir=state_root,
        store=EventStore(event_path),
        asset_dir=assets,
        poll_interval=poll_interval,
        heartbeat_interval=heartbeat_interval,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Serve the read-only local Workflow Panel on IPv4 loopback."
    )
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--store", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--lifetime-seconds", type=float)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.lifetime_seconds is not None and not 0 < args.lifetime_seconds <= 86_400:
        parser.error("--lifetime-seconds must be greater than 0 and at most 86400")
    server = create_workflow_panel_server(
        args.state_dir,
        args.store,
        host=args.host,
        port=args.port,
    )
    ready = {
        "protocol": PANEL_PROTOCOL,
        "status": "ready",
        "url": f"http://127.0.0.1:{server.server_address[1]}/",
        "mode": "read_only",
        "bind": "loopback",
    }
    print(json.dumps(ready, separators=(",", ":")), flush=True)
    lifetime_timer = None
    if args.lifetime_seconds is not None:
        lifetime_timer = threading.Timer(args.lifetime_seconds, server.shutdown)
        lifetime_timer.daemon = True
        lifetime_timer.start()
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        if lifetime_timer is not None:
            lifetime_timer.cancel()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

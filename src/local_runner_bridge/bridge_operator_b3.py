"""Bridge Operator B3 foreground bounded loop."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from local_runner_bridge.bridge_operator_b1 import (
    CONSUMED,
    DEFAULT_REPOSITORY,
    GitHubApiClient,
    SUPPORTED_TARGET_REPOSITORIES,
    TRUSTED_ACTORS,
    run_bridge_operator_b1_dry_run,
)
from local_runner_bridge.bridge_operator_b2 import DEFAULT_INBOX_ISSUE
from local_runner_bridge.bridge_operator_b2 import (
    DEFAULT_TIMEOUT_SECONDS,
    DISPATCHER_FAILED_BEFORE_RUNNER,
    DISPATCHER_FAILED_BEFORE_RUNNER_EXIT_CODE,
    DISPATCHER_REJECTED_BEFORE_RUNNER,
    DISPATCHER_REJECTED_BEFORE_RUNNER_EXIT_CODE,
    DISPATCHER_RUNNER_MAY_HAVE_STARTED,
    DispatcherInvocationResult,
    build_dispatcher_command,
    build_relay_dispatch_contract,
    default_dispatcher_invoker,
)
from local_runner_bridge.durable_evidence_provider import GitHubIssueCommentEvidenceProvider
from local_runner_bridge.durable_evidence_reconciliation import (
    RequestIdentity,
    ReconciliationDecision,
    resolve_durable_completion,
)
from local_runner_bridge.bridge_operator_lifecycle_state import (
    DISPATCHED_NOT_LOCALLY_SETTLED,
    PREPARED,
    PROCESSED,
    REJECTED_BEFORE_RUNNER,
    LifecycleEvidenceError,
    append_jsonl_durable,
    capture_current_process_identity,
    create_lock_payload,
    inspect_expected_process,
    inspect_lock_file,
    load_in_flight,
    new_in_flight_payload,
    new_review_candidate_payload,
    parse_utc,
    quarantine_lock,
    remove_exact_json,
    updated_in_flight_payload,
    validate_process_identity,
    validate_session_id,
    write_or_replace_review_candidate,
    write_durable_json,
    write_exclusive_json,
)
from local_runner_bridge.workflow_result_notifications import (
    NotificationSubmission,
    process_new_workflow_result_notifications,
)

SUMMARY_PROTOCOL = "lawb.bridge_operator_b3_dry_run_loop_summary.v1"
HEARTBEAT_PROTOCOL = "lawb.bridge_operator_b3_heartbeat.v1"
STATE_PROTOCOL = "lawb.bridge_operator_b3_state.v1"
OBSERVATION_PROTOCOL = "lawb.bridge_operator_b3_dry_run_observation.v1"
PROCESSED_REQUEST_PROTOCOL = "lawb.bridge_operator_b3_processed_request.v1"
FAILURE_PROTOCOL = "lawb.bridge_operator_b3_failure.v1"
REVIEW_CANDIDATE_FILENAME = "review_candidate.json"
ROUTING_FILENAME = "repository_routing.json"
ROUTING_PROTOCOL_V1 = "lawb.bridge_operator_local_routing.v1"
ROUTING_PROTOCOL_V2 = "lawb.bridge_operator_local_routing.v2"
EXECUTION_TARGETS_DIRECTORY = "execution-targets"
DISPATCHER_OUTCOME_COMPLETION_SOURCE = "dispatcher_outcome"
B3A_MODE = "b3a-dry-run"
B3B_MODE = "b3b-maybe-status-check"
B3C_MODE = "b3c-run-reviewbundle"
B3B_ALLOWED_ACTION = "maybe-status-check"
B3C_ALLOWED_ACTION = "run-reviewbundle"
B3C_FINAL_AUDIT_ACTION = "read-final-audit"
SAME_NODE_LAUNCHER_BINDING_ENV = "LAWB_SAME_NODE_CONTINUATION_BINDING"
SAME_NODE_LAUNCHER_BINDING_PROTOCOL = (
    "lawb.same_node_exact_candidate_continuation_launcher_binding.v1"
)

DEFAULT_MAX_CYCLES_LIMIT = 960
DEFAULT_MAX_POLL_INTERVAL_SECONDS = 3600.0
DEFAULT_READ_RETRY_COUNT = 2
HEALTH_PROBE_REQUEST_EXPIRY_SECONDS = 300
HEALTH_PROBE_RESULT_TIMEOUT_SECONDS = 120
HEALTH_PROBE_TO_REAL_TASK_SECONDS = 60
NONFATAL_REQUEST_REJECTION_REASONS = frozenset(
    {
        "health_probe_expiry_invalid",
        "health_probe_expired",
        "health_probe_expiry_exceeds_5_minutes",
    }
)
SAFE_WAIT_B1_REASONS = frozenset(
    {
        "missing_request",
        "missing_current_request",
        "no_current_request_after_consumption",
    }
)
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{2,127}$")


def run_bridge_operator_b3_dry_run_loop(
    *,
    repo_root: str | Path,
    control_repo_root: str | Path | None = None,
    repository: str = DEFAULT_REPOSITORY,
    inbox_issue: int = DEFAULT_INBOX_ISSUE,
    max_cycles: int = 1,
    poll_interval_seconds: float = 0.0,
    state_dir: str | Path | None = None,
    github_client: Any | None = None,
    target_github_client: Any | None = None,
    local_checker: Any | None = None,
    now_utc: Callable[[], datetime] | datetime | None = None,
    sleeper: Callable[[float], None] | None = None,
    read_retry_count: int = DEFAULT_READ_RETRY_COUNT,
    mode: str = B3A_MODE,
    dispatcher_invoker: Any | None = None,
    timeout_seconds: int | None = None,
    durable_evidence_provider: Any | None = None,
    operator_session_id: str | None = None,
    process_identity: dict[str, Any] | None = None,
    process_probe: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    lifecycle_fault_injector: Callable[[str], None] | None = None,
    workflow_notifications_enabled: bool | None = None,
    notification_submitter: Callable[[str, str], NotificationSubmission] | None = None,
    status_progress_reporter: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run a visible bounded loop, dry-run by default."""
    control_root = Path(control_repo_root if control_repo_root is not None else repo_root).resolve()
    target_root = Path(repo_root).resolve()
    summary = _base_summary(repository, inbox_issue, control_root, target_root, mode)
    summary["configured_max_cycles"] = max_cycles
    summary["configured_poll_interval_seconds"] = poll_interval_seconds
    configured_timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else DEFAULT_TIMEOUT_SECONDS
    )
    summary["configured_timeout_seconds"] = configured_timeout
    notifications_enabled = (
        workflow_notifications_enabled
        if workflow_notifications_enabled is not None
        else os.environ.get("LAWB_WORKFLOW_RESULT_NOTIFICATIONS_ENABLED") == "1"
    )
    summary["workflow_notifications_enabled"] = notifications_enabled
    started_at = _now(now_utc)
    session_id = operator_session_id or uuid4().hex
    try:
        session_id = validate_session_id(session_id)
        current_process_identity = validate_process_identity(
            process_identity or capture_current_process_identity()
        )
    except LifecycleEvidenceError as error:
        _block(summary, str(error))
        return _finalize_summary(summary)
    summary["operator_session_id"] = session_id
    summary["process_identity"] = current_process_identity
    summary["started_at_utc"] = _format_time(started_at)
    valid_for_seconds = max(
        float(configured_timeout),
        float(max_cycles) * float(poll_interval_seconds),
    )
    summary["valid_until_utc"] = _format_time(
        started_at + timedelta(seconds=valid_for_seconds)
    )
    sleep = sleeper or time.sleep
    lock_acquired = False
    lock_path: Path | None = None
    owned_lock_payload: dict[str, Any] | None = None
    in_flight_path: Path | None = None
    startup_recovery_non_success = False

    state_root = _resolve_state_dir(state_dir)
    if state_root is None:
        _block(summary, "localappdata_missing")
        return _finalize_summary(summary)
    summary["state_dir"] = str(state_root)

    validation_error = _validate_loop_config(
        repository=repository,
        inbox_issue=inbox_issue,
        max_cycles=max_cycles,
        poll_interval_seconds=poll_interval_seconds,
        read_retry_count=read_retry_count,
        mode=mode,
    )
    if validation_error is not None:
        _block(summary, validation_error)
        return _finalize_summary(summary)

    try:
        state_root.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        _block(summary, "state_dir_unavailable")
        summary["state_error_type"] = type(error).__name__
        return _finalize_summary(summary)
    summary["historical_last_failure_file_present"] = (state_root / "last_failure.json").exists()

    try:
        _validate_state_files(state_root)
    except ValueError as error:
        _block(summary, str(error))
        _record_failure(state_root, summary, str(error), _now(now_utc))
        _write_log(state_root, "failed", str(error), summary)
        return _finalize_summary(summary)

    control_client = github_client or GitHubApiClient(DEFAULT_REPOSITORY)
    target_client = target_github_client
    if target_client is None:
        target_client = (
            control_client
            if repository == DEFAULT_REPOSITORY
            else GitHubApiClient(repository)
        )

    lock_path = state_root / "operator.lock"
    in_flight_path = state_root / "in_flight.json"
    probe = process_probe or inspect_expected_process
    try:
        existing_in_flight = load_in_flight(in_flight_path)
    except LifecycleEvidenceError as error:
        _block(summary, str(error))
        summary["in_flight_present"] = True
        summary["exceptional_recovery_reason"] = "in_flight_invalid_manual_recovery_required"
        _record_failure(state_root, summary, str(error), _now(now_utc))
        _write_log(state_root, "blocked", str(error), summary)
        return _finalize_summary(summary)
    summary["in_flight_present"] = existing_in_flight is not None
    if existing_in_flight is not None:
        summary["in_flight_stage"] = existing_in_flight["stage"]
        summary["in_flight_operator_session_id"] = existing_in_flight[
            "operator_session_id"
        ]

    lock_assessment = inspect_lock_file(lock_path, process_probe=probe)
    _copy_lock_assessment(summary, lock_assessment)
    if lock_assessment["present"]:
        if lock_assessment["metadata_status"] != "complete":
            reason = (
                "legacy_lock_manual_recovery_required"
                if lock_assessment["metadata_status"] == "legacy"
                else "lock_metadata_invalid_manual_recovery_required"
            )
            _block(summary, reason)
            _record_failure(state_root, summary, reason, _now(now_utc))
            _write_log(state_root, "blocked", reason, summary)
            return _finalize_summary(summary)
        if not lock_assessment["quarantine_safe"]:
            reason = (
                "active_lock_present"
                if lock_assessment["process_status"] == "live"
                else "dead_lock_recovery_uncertain"
            )
            _block(summary, reason)
            _record_failure(state_root, summary, reason, _now(now_utc))
            _write_log(state_root, "blocked", reason, summary)
            return _finalize_summary(summary)
        if existing_in_flight is not None:
            if not _lock_matches_in_flight(lock_assessment, existing_in_flight):
                reason = "lock_in_flight_identity_mismatch"
                _block(summary, reason)
                summary["exceptional_recovery_reason"] = reason
                _record_failure(state_root, summary, reason, _now(now_utc))
                _write_log(state_root, "blocked", reason, summary)
                return _finalize_summary(summary)
            _process_workflow_notifications(
                state_root=state_root,
                operator_session_id=session_id,
                summary=summary,
                enabled=notifications_enabled,
                submitter=notification_submitter,
                now_utc=now_utc,
            )
            recovery = _recover_existing_in_flight(
                state_root=state_root,
                control_repo_root=control_root,
                target_repo_root=target_root,
                in_flight=existing_in_flight,
                repository=repository,
                client=target_client,
                provider=durable_evidence_provider,
                cycle=0,
                now=_now(now_utc),
                summary=summary,
            )
            _process_workflow_notifications(
                state_root=state_root,
                operator_session_id=session_id,
                summary=summary,
                enabled=notifications_enabled,
                submitter=notification_submitter,
                now_utc=now_utc,
            )
            if recovery["reason"] is not None:
                reason = str(recovery["reason"])
                _block(summary, reason)
                _record_failure(state_root, summary, reason, _now(now_utc))
                _write_log(state_root, "blocked", reason, summary)
                return _finalize_summary(summary)
            startup_recovery_non_success = bool(recovery["settled_non_success"])
            existing_in_flight = None
            summary["in_flight_present"] = False
        try:
            quarantined = quarantine_lock(
                lock_path,
                expected_sha256=str(lock_assessment["evidence_sha256"]),
                operator_session_id=str(lock_assessment["operator_session_id"]),
            )
        except (OSError, LifecycleEvidenceError) as error:
            reason = str(error) if isinstance(error, LifecycleEvidenceError) else "lock_quarantine_failed"
            _block(summary, reason)
            summary["exceptional_recovery_reason"] = reason
            _record_failure(state_root, summary, reason, _now(now_utc))
            _write_log(state_root, "blocked", reason, summary)
            return _finalize_summary(summary)
        summary["lock_quarantined"] = True
        summary["quarantined_lock_path"] = str(quarantined)
    elif existing_in_flight is not None:
        reason = "in_flight_without_lock_manual_recovery_required"
        _block(summary, reason)
        summary["exceptional_recovery_reason"] = reason
        _record_failure(state_root, summary, reason, _now(now_utc))
        _write_log(state_root, "blocked", reason, summary)
        return _finalize_summary(summary)

    try:
        owned_lock_payload = create_lock_payload(
            operator_session_id=session_id,
            process_identity=current_process_identity,
            created_at=_now(now_utc),
            repository=repository,
            inbox_issue=inbox_issue,
            mode=mode,
        )
        write_exclusive_json(lock_path, owned_lock_payload)
        lock_acquired = True
    except FileExistsError:
        _block(summary, "active_lock_present")
        _record_failure(state_root, summary, "active_lock_present", _now(now_utc))
        _write_log(state_root, "blocked", "active_lock_present", summary)
        return _finalize_summary(summary)
    except LifecycleEvidenceError as error:
        _block(summary, str(error))
        _record_failure(state_root, summary, str(error), _now(now_utc))
        _write_log(state_root, "blocked", str(error), summary)
        return _finalize_summary(summary)
    except OSError as error:
        _block(summary, "lock_unavailable")
        summary["lock_error_type"] = type(error).__name__
        _record_failure(state_root, summary, "lock_unavailable", _now(now_utc))
        _write_log(state_root, "blocked", "lock_unavailable", summary)
        return _finalize_summary(summary)

    try:
        _process_workflow_notifications(
            state_root=state_root,
            operator_session_id=session_id,
            summary=summary,
            enabled=notifications_enabled,
            submitter=notification_submitter,
            now_utc=now_utc,
        )
        summary["lock_acquired"] = True
        summary["loop_started"] = True
        summary["result"] = "success"
        summary["phase"] = "running"
        _write_state(state_root, "running", summary, _now(now_utc))
        _write_log(state_root, "started", "dry_run_loop_started", summary)

        if startup_recovery_non_success:
            reason = "restart_reconciled_terminal_non_success"
            _block(summary, reason)
            _record_failure(state_root, summary, reason, _now(now_utc))
            _write_log(state_root, "reconciled", reason, summary)
            _write_state(state_root, "blocked", summary, _now(now_utc))
            _write_heartbeat(state_root, "blocked", 0, summary, _now(now_utc))
            return _finalize_summary(summary)

        session_rejected_requests: set[tuple[str, str]] = set()
        for cycle in range(1, max_cycles + 1):
            summary["cycles_started"] = cycle
            summary["current_delegation_outcome"] = None
            if _flag_exists(state_root, "stop.flag"):
                summary["stop_requested"] = True
                summary["phase"] = "stopped"
                _write_heartbeat(state_root, "stopped", cycle, summary, _now(now_utc))
                _write_log(state_root, "stopped", "stop_flag_present", summary)
                break

            if _flag_exists(state_root, "pause.flag"):
                summary["phase"] = "paused"
                summary["pause_observed"] = True
                summary["paused_cycles"] += 1
                summary["cycles_completed"] = cycle
                _write_heartbeat(state_root, "paused", cycle, summary, _now(now_utc))
                _write_log(state_root, "paused", "pause_flag_present", summary)
            else:
                summary["phase"] = "running"
                _write_heartbeat(state_root, "polling", cycle, summary, _now(now_utc))
                b1_summary = _run_b1_with_bounded_retry(
                    state_root=state_root,
                    repo_root=repo_root,
                    repository=repository,
                    inbox_issue=inbox_issue,
                    control_client=control_client,
                    target_client=target_client,
                    local_checker=local_checker,
                    now_utc=now_utc,
                    retry_count=read_retry_count,
                    summary=summary,
                )
                summary["cycles_completed"] = cycle
                summary["last_b1_result"] = b1_summary.get("result")
                summary["last_b1_blocked_reasons"] = list(b1_summary.get("blocked_reasons", []))
                _copy_b1_identity(summary, b1_summary)
                if b1_summary.get("result") == "success":
                    summary["eligible_request_observed"] = True
                    if (
                        mode == B3C_MODE
                        and b1_summary.get("requested_action") == B3C_ALLOWED_ACTION
                    ):
                        _report_request_accepted_progress(
                            summary, status_progress_reporter
                        )
                    if mode == B3A_MODE:
                        appended = _append_observation_if_new(
                            state_root,
                            b1_summary,
                            cycle,
                            _now(now_utc),
                        )
                        summary["dry_run_observation_written"] = appended
                        summary["dry_run_duplicate_observation"] = not appended
                        _write_log(state_root, "observed", "eligible_request_dry_run_observed", summary)
                    else:
                        request_key = (
                            str(b1_summary.get("target_repository") or repository),
                            str(b1_summary.get("request_id") or ""),
                        )
                        request_rejected_this_cycle = False
                        if request_key in session_rejected_requests:
                            summary["suppressed_request_rejection_cycle_count"] += 1
                            summary["empty_or_blocked_cycles"] += 1
                            summary["current_delegation_outcome"] = (
                                "session_local_request_rejection_suppressed"
                            )
                            request_rejected_this_cycle = True
                        else:
                            reason = _delegate_b3_request(
                                state_root=state_root,
                                repo_root=target_root,
                                control_repo_root=control_root,
                                repository=repository,
                                client=target_client,
                                b1_summary=b1_summary,
                                cycle=cycle,
                                now=_now(now_utc),
                                summary=summary,
                                dispatcher_invoker=dispatcher_invoker,
                                timeout_seconds=timeout_seconds,
                                durable_evidence_provider=durable_evidence_provider,
                                operator_session_id=session_id,
                                process_identity=current_process_identity,
                                lifecycle_fault_injector=lifecycle_fault_injector,
                            )
                            _process_workflow_notifications(
                                state_root=state_root,
                                operator_session_id=session_id,
                                summary=summary,
                                enabled=notifications_enabled,
                                submitter=notification_submitter,
                                now_utc=now_utc,
                            )
                            if reason is not None:
                                if reason in NONFATAL_REQUEST_REJECTION_REASONS:
                                    session_rejected_requests.add(request_key)
                                    summary["nonfatal_request_rejection_count"] += 1
                                    summary["last_nonfatal_request_rejection_reason"] = reason
                                    summary["last_nonfatal_request_rejection_request_id"] = (
                                        request_key[1]
                                    )
                                    summary["empty_or_blocked_cycles"] += 1
                                    summary["current_delegation_outcome"] = (
                                        "request_rejected_nonfatal"
                                    )
                                    _write_log(
                                        state_root,
                                        "request_rejected",
                                        reason,
                                        summary,
                                    )
                                    request_rejected_this_cycle = True
                                else:
                                    _record_failure(
                                        state_root,
                                        summary,
                                        reason,
                                        _now(now_utc),
                                    )
                                    _write_log(state_root, "failed", reason, summary)
                                    break
                        if not request_rejected_this_cycle:
                            current_outcome = summary.get("current_delegation_outcome")
                            if current_outcome == "durable_completion_reconciled":
                                _write_log(
                                    state_root,
                                    "reconciled",
                                    "durable_completion_reconciled",
                                    summary,
                                )
                            elif current_outcome == "local_processed_request_already_seen":
                                _write_log(
                                    state_root,
                                    "already_processed",
                                    "local_processed_request_already_seen",
                                    summary,
                                )
                            elif current_outcome == "verified_dispatcher_result":
                                _write_log(
                                    state_root,
                                    "processed",
                                    "verified_dispatcher_result",
                                    summary,
                                )
                            else:
                                _write_log(
                                    state_root,
                                    "completed",
                                    "no_dispatcher_result_verified",
                                    summary,
                                )
                elif _is_github_read_failure(b1_summary):
                    _block(summary, "github_read_unavailable")
                    _record_failure(state_root, summary, "github_read_unavailable", _now(now_utc))
                    _write_log(state_root, "failed", "github_read_unavailable", summary)
                    break
                elif _is_safe_wait_b1_result(b1_summary):
                    if "no_current_request_after_consumption" in b1_summary.get(
                        "blocked_reasons", []
                    ):
                        summary["processed_request_already_seen"] = True
                    summary["empty_or_blocked_cycles"] += 1
                    _write_log(state_root, "waiting", "no_eligible_current_request", summary)
                else:
                    failure_reason = _first_b1_blocked_reason(b1_summary)
                    _block(summary, failure_reason)
                    _record_failure(state_root, summary, failure_reason, _now(now_utc))
                    _write_log(state_root, "failed", failure_reason, summary)
                    break

            if cycle < max_cycles:
                summary["sleep_call_count"] += 1
                sleep(poll_interval_seconds)

        if summary["result"] == "success" and summary["phase"] == "running":
            summary["phase"] = "max_cycles_completed"
        _finalize_summary(summary)
        _write_state(state_root, summary["phase"], summary, _now(now_utc))
        _write_heartbeat(state_root, summary["phase"], summary["cycles_completed"], summary, _now(now_utc))
        return summary
    finally:
        unresolved_in_flight = bool(
            in_flight_path is not None and in_flight_path.exists()
        )
        summary["in_flight_present"] = unresolved_in_flight
        if unresolved_in_flight:
            try:
                observed_in_flight = load_in_flight(in_flight_path)
            except LifecycleEvidenceError:
                observed_in_flight = None
            if observed_in_flight is not None:
                summary["in_flight_stage"] = observed_in_flight["stage"]
                summary["in_flight_operator_session_id"] = observed_in_flight[
                    "operator_session_id"
                ]
        if (
            lock_acquired
            and lock_path is not None
            and owned_lock_payload is not None
            and not unresolved_in_flight
        ):
            try:
                remove_exact_json(lock_path, owned_lock_payload)
            except FileNotFoundError:
                pass
            except (OSError, LifecycleEvidenceError):
                _block(summary, "lock_release_failed")


def _process_workflow_notifications(
    *,
    state_root: Path,
    operator_session_id: str,
    summary: dict[str, Any],
    enabled: bool,
    submitter: Callable[[str, str], NotificationSubmission] | None,
    now_utc: Callable[[], datetime] | datetime | None,
) -> None:
    if not enabled:
        return
    summary["workflow_notification_scan_count"] += 1
    try:
        notification_result = process_new_workflow_result_notifications(
            state_dir=state_root,
            operator_session_id=operator_session_id,
            submitter=submitter,
            now_utc=now_utc,
        )
    except Exception as error:
        summary["workflow_notification_ambiguous_count"] += 1
        summary["workflow_notification_last_status"] = (
            f"notification_processor_error:{type(error).__name__}"
        )
        return
    summary["workflow_notification_activation_created"] = bool(
        summary["workflow_notification_activation_created"]
        or notification_result.get("activation_created")
    )
    summary["workflow_notification_records_considered"] += int(
        notification_result.get("records_considered", 0)
    )
    summary["workflow_notification_submitted_count"] += int(
        notification_result.get("submitted_count", 0)
    )
    summary["workflow_notification_ambiguous_count"] += int(
        notification_result.get("ambiguous_count", 0)
    )
    summary["workflow_notification_last_status"] = notification_result.get(
        "status", "unknown"
    )
    if notification_result.get("last_notification_id") is not None:
        summary["workflow_notification_last_id"] = notification_result[
            "last_notification_id"
        ]


def _base_summary(
    repository: str,
    inbox_issue: int,
    control_repo_root: str | Path,
    target_repo_root: str | Path,
    mode: str,
) -> dict[str, Any]:
    return {
        "protocol": SUMMARY_PROTOCOL,
        "phase": "preflight",
        "result": "blocked",
        "repository": repository,
        "control_repository": DEFAULT_REPOSITORY,
        "target_repository": repository,
        "configured_inbox_issue": inbox_issue,
        "repo_root": str(target_repo_root),
        "control_repo_root": str(control_repo_root),
        "target_repo_root": str(target_repo_root),
        "state_dir": None,
        "mode": mode,
        "configured_max_cycles": None,
        "configured_poll_interval_seconds": None,
        "configured_timeout_seconds": None,
        "effective_dispatcher_timeout_seconds": None,
        "operator_session_id": None,
        "process_identity": None,
        "started_at_utc": None,
        "valid_until_utc": None,
        "health_probe_request_expiry_seconds": HEALTH_PROBE_REQUEST_EXPIRY_SECONDS,
        "health_probe_result_timeout_seconds": HEALTH_PROBE_RESULT_TIMEOUT_SECONDS,
        "health_probe_to_real_task_seconds": HEALTH_PROBE_TO_REAL_TASK_SECONDS,
        "health_probe_request_remaining_seconds": None,
        "lock_acquired": False,
        "lock_metadata_status": "not_present",
        "lock_process_status": "not_observed",
        "lock_descendant_status": "not_observed",
        "lock_quarantined": False,
        "quarantined_lock_path": None,
        "exceptional_recovery_reason": None,
        "in_flight_present": False,
        "in_flight_stage": None,
        "in_flight_operator_session_id": None,
        "restart_reconciliation_performed": False,
        "loop_started": False,
        "cycles_started": 0,
        "cycles_completed": 0,
        "paused_cycles": 0,
        "empty_or_blocked_cycles": 0,
        "sleep_call_count": 0,
        "pause_observed": False,
        "stop_requested": False,
        "eligible_request_observed": False,
        "dry_run_observation_written": False,
        "dry_run_duplicate_observation": False,
        "processed_request_written": False,
        "processed_request_already_seen": False,
        "current_delegation_outcome": None,
        "status_progress_publication": "not_requested",
        "nonfatal_request_rejection_count": 0,
        "suppressed_request_rejection_cycle_count": 0,
        "last_nonfatal_request_rejection_reason": None,
        "last_nonfatal_request_rejection_request_id": None,
        "durable_reconciliation_performed": False,
        "durable_reconciliation_read_attempts": 0,
        "durable_reconciliation_decision": None,
        "durable_reconciliation_reason": None,
        "durable_reconciliation_matched_evidence_ids": [],
        "durable_reconciliation_diagnostics": [],
        "durable_completion_reconciled": False,
        "terminal_result": None,
        "terminal_settlement": None,
        "terminal_observed_at_utc": None,
        "request_id": None,
        "inbox_comment_id": None,
        "target_issue": None,
        "target_dispatch_request_id": None,
        "requested_action": None,
        "expected_branch": None,
        "expected_head": None,
        "expires": None,
        "evaluated_at_utc": None,
        "current_request_count": 0,
        "consumed_request_count": 0,
        "expired_request_count": 0,
        "selected_request_state": None,
        "last_b1_result": None,
        "last_b1_blocked_reasons": [],
        "dispatcher_exit_code": None,
        "dispatcher_invocation_args": [],
        "dispatcher_timed_out": False,
        "dispatcher_missing": False,
        "dispatcher_stdout": "",
        "dispatcher_stderr": "",
        "dispatcher_execution_reach": None,
        "dispatcher_result_writeback_reached": False,
        "dispatcher_result_writeback_verified": False,
        "runner_reached": None,
        "codex_reached": None,
        "target_result_verified": False,
        "target_result_comment_id": None,
        "target_result_author": None,
        "workflow_notifications_enabled": False,
        "workflow_notification_scan_count": 0,
        "workflow_notification_activation_created": False,
        "workflow_notification_records_considered": 0,
        "workflow_notification_submitted_count": 0,
        "workflow_notification_ambiguous_count": 0,
        "workflow_notification_last_status": "disabled",
        "workflow_notification_last_id": None,
        "operator_direct_execution_performed": False,
        "current_failure_recorded": False,
        "current_failure_reason": None,
        "historical_last_failure_file_present": False,
        "last_failure_json_applies_to_current_run": False,
        "last_failure_json_status": "not_present",
        "current_run": {},
        "github_read_attempts": 0,
        "retry_performed": False,
        "blocked_reasons": [],
        "next_recommended_action": "chatgpt_review",
        **_safety_matrix(),
    }


def _safety_matrix() -> dict[str, bool | int]:
    return {
        "fixed_inbox_read_performed": False,
        "broad_issue_scan_performed": False,
        "latest_next_inference_performed": False,
        "dispatcher_invoked": False,
        "dispatcher_invocation_count": 0,
        "runner_invoked": False,
        "codex_invoked": False,
        "github_write_performed": False,
        "background_service_started": False,
        "commit_performed": False,
        "push_performed": False,
        "issue_closed": False,
        "label_changed": False,
        "pr_created": False,
        "merge_performed": False,
        "branch_deleted": False,
        "approval_consumed": False,
    }


def _validate_loop_config(
    *,
    repository: str,
    inbox_issue: int,
    max_cycles: int,
    poll_interval_seconds: float,
    read_retry_count: int,
    mode: str,
) -> str | None:
    if repository not in SUPPORTED_TARGET_REPOSITORIES:
        return "unsupported_target_repository"
    if inbox_issue != DEFAULT_INBOX_ISSUE:
        return "unsupported_inbox_issue"
    if not isinstance(max_cycles, int) or max_cycles < 1 or max_cycles > DEFAULT_MAX_CYCLES_LIMIT:
        return "invalid_max_cycles"
    if poll_interval_seconds < 0 or poll_interval_seconds > DEFAULT_MAX_POLL_INTERVAL_SECONDS:
        return "invalid_poll_interval_seconds"
    if read_retry_count < 0 or read_retry_count > 5:
        return "invalid_read_retry_count"
    if mode not in {B3A_MODE, B3B_MODE, B3C_MODE}:
        return "invalid_mode"
    return None


def _resolve_state_dir(state_dir: str | Path | None) -> Path | None:
    if state_dir is not None:
        return Path(state_dir)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    return Path(local_app_data) / "LocalAIWorkbench" / "BridgeOperator"


def _validate_state_files(state_dir: Path) -> None:
    state_file = state_dir / "state.json"
    if state_file.exists():
        try:
            payload = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("corrupted_state") from error
        if not isinstance(payload, dict):
            raise ValueError("corrupted_state")

    observations = state_dir / "dry_run_observations.jsonl"
    if observations.exists():
        try:
            _read_observed_request_ids(observations)
        except (OSError, json.JSONDecodeError, ValueError) as error:
            raise ValueError("corrupted_state") from error

    processed = state_dir / "processed_requests.jsonl"
    if processed.exists():
        try:
            _read_processed_request_records(processed)
        except (OSError, json.JSONDecodeError, ValueError) as error:
            raise ValueError("corrupted_state") from error


def _run_b1_with_bounded_retry(
    *,
    state_root: Path,
    repo_root: str | Path,
    repository: str,
    inbox_issue: int,
    control_client: Any,
    target_client: Any,
    local_checker: Any | None,
    now_utc: Callable[[], datetime] | datetime | None,
    retry_count: int,
    summary: dict[str, Any],
) -> dict[str, Any]:
    attempts = retry_count + 1
    last: dict[str, Any] | None = None
    for attempt in range(1, attempts + 1):
        summary["github_read_attempts"] += 1
        processed_path = state_root / "processed_requests.jsonl"
        try:
            consumed_request_ids = (
                _read_processed_request_records(processed_path, repository=repository)
                if processed_path.exists()
                else {}
            )
        except (OSError, json.JSONDecodeError, ValueError):
            return {"result": "blocked", "blocked_reasons": ["corrupted_state"]}
        try:
            last = run_bridge_operator_b1_dry_run(
                inbox_issue=inbox_issue,
                repo_root=repo_root,
                repository=repository,
                github_client=control_client,
                target_github_client=target_client,
                local_checker=local_checker,
                now_utc=_now(now_utc),
                consumed_request_ids=consumed_request_ids,
            )
        except Exception as error:
            last = {
                "result": "blocked",
                "blocked_reasons": ["github_read_unavailable"],
                "github_read_error_type": type(error).__name__,
            }
        summary["fixed_inbox_read_performed"] = bool(
            summary["fixed_inbox_read_performed"] or last.get("fixed_inbox_read_performed")
        )
        if not _is_github_read_failure(last) or attempt == attempts:
            return last
        summary["retry_performed"] = True
    return last or {"result": "blocked", "blocked_reasons": ["github_read_unavailable"]}


def _is_github_read_failure(summary: dict[str, Any]) -> bool:
    return "github_read_unavailable" in summary.get("blocked_reasons", [])


def _is_safe_wait_b1_result(summary: dict[str, Any]) -> bool:
    reasons = set(summary.get("blocked_reasons", []))
    return bool(reasons) and reasons <= SAFE_WAIT_B1_REASONS


def _first_b1_blocked_reason(summary: dict[str, Any]) -> str:
    reasons = list(summary.get("blocked_reasons", []))
    return str(reasons[0]) if reasons else "b1_validation_failed"


def _copy_lock_assessment(
    summary: dict[str, Any], assessment: dict[str, Any]
) -> None:
    summary["lock_metadata_status"] = assessment.get("metadata_status")
    summary["lock_process_status"] = assessment.get("process_status")
    summary["lock_descendant_status"] = assessment.get("descendant_status")
    summary["lock_operator_session_id"] = assessment.get(
        "operator_session_id"
    )
    summary["lock_process_identity"] = assessment.get("process_identity")
    summary["lock_descendant_pids"] = list(
        assessment.get("descendant_pids") or []
    )
    summary["exceptional_recovery_reason"] = assessment.get(
        "exceptional_recovery_reason"
    )


def _lock_matches_in_flight(
    assessment: dict[str, Any], in_flight: dict[str, Any]
) -> bool:
    return (
        assessment.get("operator_session_id")
        == in_flight.get("operator_session_id")
        and assessment.get("process_identity")
        == in_flight.get("process_identity")
        and assessment.get("repository")
        == in_flight.get("target_repository")
    )


def _reconciliation_provider(
    provider: Any | None,
    client: Any,
    repository: str,
) -> Any:
    return provider or GitHubIssueCommentEvidenceProvider(
        client,
        repository=repository,
    )


def _request_identity_from_b1(
    b1_summary: dict[str, Any], repository: str
) -> RequestIdentity:
    return RequestIdentity(
        repository=repository,
        issue_number=int(b1_summary["target_issue"]),
        surface="issue_comment",
        request_id=str(b1_summary["target_dispatch_request_id"]),
        action=str(b1_summary["requested_action"]),
        branch=str(b1_summary["expected_branch"]),
        head=str(b1_summary["expected_head"]),
    )


def _request_identity_from_in_flight(
    in_flight: dict[str, Any],
) -> RequestIdentity:
    return RequestIdentity(
        repository=str(in_flight["target_repository"]),
        issue_number=int(in_flight["target_issue"]),
        surface="issue_comment",
        request_id=str(in_flight["dispatch_request_id"]),
        action=str(in_flight["action"]),
        branch=str(in_flight["branch"]),
        head=str(in_flight["expected_head"]),
    )


def _resolve_reconciliation(
    request: RequestIdentity,
    provider: Any,
    summary: dict[str, Any],
) -> Any:
    summary["durable_reconciliation_performed"] = True
    summary["durable_reconciliation_read_attempts"] += 1
    return resolve_durable_completion(
        request,
        provider,
        frozenset(TRUSTED_ACTORS),
    )


def _terminal_evidence(reconciliation: Any, now: datetime) -> dict[str, Any]:
    terminal_result = str(reconciliation.terminal_result)
    return {
        "evidence_id": str(reconciliation.matched_evidence_ids[0]),
        "author": str(reconciliation.terminal_author),
        "result": terminal_result,
        "settlement": (
            "settled_success"
            if terminal_result == "success"
            else "settled_non_success"
        ),
        "reconciliation_decision": reconciliation.decision.value,
        "reconciliation_reason": reconciliation.reason.value,
        "observed_at_utc": _format_time(now),
    }


def _persist_review_candidate_if_available(
    *,
    state_root: Path,
    b1_summary: dict[str, Any],
    reconciliation: Any,
    now: datetime,
    operator_session_id: str,
    summary: dict[str, Any],
    control_repo_root: Path | None = None,
    target_repo_root: Path | None = None,
) -> str | None:
    """Persist only an eligible candidate whose trusted evidence matches local Git."""
    if (
        b1_summary.get("requested_action") != B3C_ALLOWED_ACTION
        or reconciliation.decision != ReconciliationDecision.COMPLETED
        or reconciliation.terminal_result != "success"
    ):
        return None
    binding_status = getattr(reconciliation, "review_candidate_binding_status", "absent")
    if binding_status == "absent":
        summary["review_candidate_state"] = "legacy_terminal_without_binding"
        return None
    if binding_status != "valid" or not reconciliation.review_candidate_binding:
        _block(summary, "review_candidate_binding_malformed")
        return "review_candidate_binding_malformed"
    binding = reconciliation.review_candidate_binding
    if binding["candidate_acceptance"] == "ineligible":
        summary["review_candidate_state"] = (
            "retained_ineligible"
            if (state_root / REVIEW_CANDIDATE_FILENAME).exists()
            else "not_written_ineligible"
        )
        summary["next_task_availability"] = "unchanged"
        return None
    changed_files = binding["changed_files"]
    if not changed_files:
        _block(summary, "review_candidate_eligibility_invalid")
        return "review_candidate_eligibility_invalid"
    if target_repo_root is None:
        _block(summary, "review_candidate_local_root_unavailable")
        return "review_candidate_local_root_unavailable"
    candidate, candidate_error = _inspect_review_candidate_worktree(
        target_repo_root,
        expected_repository=str(
            b1_summary.get("target_repository", b1_summary.get("repository"))
        ),
        expected_branch=str(b1_summary["expected_branch"]),
        expected_head=str(b1_summary["expected_head"]).lower(),
        expected_changed_files=changed_files,
    )
    if candidate_error is not None or candidate is None:
        reason = candidate_error or "review_candidate_local_binding_invalid"
        _block(summary, reason)
        return reason
    try:
        payload = new_review_candidate_payload(
            target_repository=str(b1_summary.get("target_repository", b1_summary.get("repository"))),
            target_issue=int(b1_summary["target_issue"]),
            dispatch_request_id=str(b1_summary["target_dispatch_request_id"]),
            action=B3C_ALLOWED_ACTION,
            branch=str(b1_summary["expected_branch"]),
            expected_head=str(b1_summary["expected_head"]).lower(),
            terminal_result_comment_id=str(reconciliation.matched_evidence_ids[0]),
            review_bundle_comment_id=binding["review_bundle_comment_id"],
            candidate_manifest_fingerprint=binding["candidate_manifest_fingerprint"],
            target_repo_root=candidate["root"],
            recorded_at=now,
        )
        state = write_or_replace_review_candidate(
            state_root / REVIEW_CANDIDATE_FILENAME,
            payload,
            operator_session_id=operator_session_id,
        )
    except (KeyError, TypeError, ValueError, OSError, LifecycleEvidenceError):
        _block(summary, "review_candidate_write_failed")
        return "review_candidate_write_failed"
    summary["review_candidate_state"] = state
    summary["review_candidate_parent_comment_id"] = binding["review_bundle_comment_id"]
    if (
        payload["target_repository"] == DEFAULT_REPOSITORY
        and control_repo_root is not None
        and target_repo_root is not None
    ):
        routing_path = state_root / ROUTING_FILENAME
        admission, admission_reason = _availability_routing_admission(
            routing_path, target_repo_root
        )
        if admission == "not_configured":
            summary["next_task_availability"] = "not_configured"
        elif admission_reason is not None:
            summary["next_task_availability"] = "unavailable"
            summary["next_task_availability_reason"] = admission_reason
        else:
            transition_error = _prepare_next_lawb_execution_target(
                state_root=state_root,
                control_repo_root=control_repo_root,
                candidate_repo_root=target_repo_root,
                operator_session_id=operator_session_id,
                summary=summary,
            )
            if transition_error is not None:
                summary["next_task_availability"] = "unavailable"
                summary["next_task_availability_reason"] = transition_error
            else:
                summary["next_task_availability"] = "ready"
    return None


def _normalized_lawb_origin(origin: str) -> str | None:
    value = origin.strip()
    match = re.fullmatch(
        r"https://github\.com/([^/]+/[^/]+?)(?:\.git)?/?", value, re.IGNORECASE
    )
    if match is None:
        match = re.fullmatch(
            r"(?:ssh://)?git@github\.com[:/]([^/]+/[^/]+?)(?:\.git)?", value,
            re.IGNORECASE,
        )
    return None if match is None else match.group(1).casefold()


def _git_stdout(root: Path, *arguments: str) -> tuple[str | None, str | None]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *arguments],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return None, "execution_target_git_unavailable"
    if completed.returncode != 0:
        return None, "execution_target_git_unavailable"
    return completed.stdout.strip(), None


def _inspect_clean_lawb_worktree(
    root: Path,
    *,
    expected_repository: str = DEFAULT_REPOSITORY,
) -> tuple[dict[str, str] | None, str | None]:
    if not root.is_dir():
        return None, "execution_target_root_unavailable"
    top_level, error = _git_stdout(root, "rev-parse", "--show-toplevel")
    if error is not None or top_level is None:
        return None, "execution_target_not_git_repository"
    try:
        if Path(top_level).resolve() != root.resolve():
            return None, "execution_target_git_root_mismatch"
    except OSError:
        return None, "execution_target_git_root_mismatch"
    origin, error = _git_stdout(root, "remote", "get-url", "origin")
    if (
        error is not None
        or origin is None
        or _normalized_lawb_origin(origin) != expected_repository.casefold()
    ):
        return None, "execution_target_origin_mismatch"
    branch, error = _git_stdout(root, "branch", "--show-current")
    if error is not None or branch is None or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", branch) is None:
        return None, "execution_target_branch_unreadable"
    head, error = _git_stdout(root, "rev-parse", "HEAD")
    if error is not None or head is None or re.fullmatch(r"[0-9a-fA-F]{40}", head) is None:
        return None, "execution_target_head_unreadable"
    status, error = _git_stdout(root, "status", "--porcelain=v1", "--untracked-files=all")
    if error is not None or status is None:
        return None, "execution_target_status_unreadable"
    staged, error = _git_stdout(root, "diff", "--cached", "--name-only")
    if error is not None or staged is None:
        return None, "execution_target_staged_status_unreadable"
    return {
        "root": str(root.resolve()),
        "branch": branch,
        "head": head.lower(),
        "status": status,
        "staged": staged,
    }, None


def _inspect_review_candidate_worktree(
    root: Path,
    *,
    expected_repository: str,
    expected_branch: str,
    expected_head: str,
    expected_changed_files: tuple[str, ...] | list[str],
) -> tuple[dict[str, str] | None, str | None]:
    candidate, error = _inspect_clean_lawb_worktree(
        root,
        expected_repository=expected_repository,
    )
    if error is not None or candidate is None:
        return None, error or "review_candidate_local_binding_invalid"
    if candidate["branch"] != expected_branch:
        return None, "review_candidate_branch_mismatch"
    if candidate["head"] != expected_head:
        return None, "review_candidate_head_mismatch"
    if candidate["staged"]:
        return None, "review_candidate_staged_changes_present"
    if not candidate["status"]:
        return None, "review_candidate_worktree_clean"
    unstaged, error = _git_stdout(root, "diff", "--name-only", "--")
    if error is not None or unstaged is None:
        return None, "review_candidate_status_unreadable"
    untracked, error = _git_stdout(
        root, "ls-files", "--others", "--exclude-standard"
    )
    if error is not None or untracked is None:
        return None, "review_candidate_status_unreadable"
    actual_files = tuple(
        sorted(
            {
                path
                for path in (*unstaged.splitlines(), *untracked.splitlines())
                if path
            }
        )
    )
    if actual_files != tuple(sorted(expected_changed_files)):
        return None, "review_candidate_changed_files_mismatch"
    return candidate, None


def _routing_binds_review_candidate(
    routing_path: Path, candidate_root: Path
) -> str | None:
    try:
        raw = routing_path.read_bytes()
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "execution_target_routing_configuration_invalid"
    if not isinstance(value, dict) or value.get("repository") != DEFAULT_REPOSITORY:
        return "execution_target_routing_ambiguous"
    if value.get("protocol") == ROUTING_PROTOCOL_V1:
        if set(value) != {"protocol", "repository", "target_repo_root"}:
            return "execution_target_routing_ambiguous"
        configured_root = value.get("target_repo_root")
        if not isinstance(configured_root, str):
            return "execution_target_routing_configuration_invalid"
        try:
            if Path(configured_root).resolve() != candidate_root.resolve():
                return "execution_target_routing_ambiguous"
        except OSError:
            return "execution_target_routing_configuration_invalid"
        return None
    if value.get("protocol") != ROUTING_PROTOCOL_V2 or set(value) != {
        "protocol",
        "repository",
        "selected_target",
    }:
        return "execution_target_routing_ambiguous"
    selected = value.get("selected_target")
    if not isinstance(selected, dict) or set(selected) != {
        "selection_id",
        "target_repo_root",
        "branch",
        "head",
    }:
        return "execution_target_routing_configuration_invalid"
    if (
        not isinstance(selected.get("selection_id"), str)
        or not selected["selection_id"]
        or not isinstance(selected.get("target_repo_root"), str)
        or not isinstance(selected.get("branch"), str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", selected["branch"]) is None
        or not isinstance(selected.get("head"), str)
        or re.fullmatch(r"[0-9a-fA-F]{40}", selected["head"]) is None
    ):
        return "execution_target_routing_configuration_invalid"
    try:
        if Path(selected["target_repo_root"]).resolve() != candidate_root.resolve():
            return "execution_target_routing_v2_root_mismatch"
    except OSError:
        return "execution_target_routing_configuration_invalid"
    candidate, candidate_error = _inspect_clean_lawb_worktree(candidate_root)
    if candidate_error is not None:
        return candidate_error
    if candidate is None:
        return "execution_target_candidate_unavailable"
    if selected["branch"] != candidate["branch"]:
        return "execution_target_routing_v2_branch_mismatch"
    if selected["head"].lower() != candidate["head"]:
        return "execution_target_routing_v2_head_mismatch"
    return None


def _availability_routing_admission(
    routing_path: Path, candidate_root: Path
) -> tuple[str, str | None]:
    """Admit an availability transition only from trusted local routing."""
    if not routing_path.exists():
        return "not_configured", None
    reason = _routing_binds_review_candidate(routing_path, candidate_root)
    if reason is not None:
        return "configured_unavailable", reason
    return "configured", None


def _prepare_next_lawb_execution_target(
    *,
    state_root: Path,
    control_repo_root: Path,
    candidate_repo_root: Path,
    operator_session_id: str,
    summary: dict[str, Any],
) -> str | None:
    """Prepare one local-only successor for a preserved reviewer candidate."""
    candidate, candidate_error = _inspect_clean_lawb_worktree(candidate_repo_root)
    if candidate_error is not None:
        return candidate_error
    if candidate is None:
        return "execution_target_candidate_unavailable"
    if not candidate["status"]:
        summary["execution_target_transition"] = "not_required"
        return None
    if candidate["staged"]:
        return "execution_target_candidate_staged"

    routing_path = state_root / ROUTING_FILENAME
    routing_error = _routing_binds_review_candidate(routing_path, candidate_repo_root)
    if routing_error is not None:
        return routing_error

    control, control_error = _inspect_clean_lawb_worktree(control_repo_root)
    if control_error is not None:
        return "execution_target_control_" + control_error.removeprefix("execution_target_")
    if control is None or control["status"] or control["staged"]:
        return "execution_target_control_not_clean"

    selection_material = "\n".join(
        (candidate["root"], candidate["branch"], candidate["head"], candidate["status"])
    ).encode("utf-8")
    selection_id = "candidate-" + hashlib.sha256(selection_material).hexdigest()[:16]
    branch = "codex/workflow-execution-" + selection_id.removeprefix("candidate-")
    target_root = state_root / EXECUTION_TARGETS_DIRECTORY / selection_id
    try:
        target_root.parent.mkdir(parents=True, exist_ok=True)
        if target_root.parent.resolve().parent != state_root.resolve():
            return "execution_target_path_invalid"
    except OSError:
        return "execution_target_path_unavailable"

    transition = "selected"
    if not target_root.exists():
        try:
            completed = subprocess.run(
                [
                    "git",
                    "-C",
                    str(control_repo_root),
                    "worktree",
                    "add",
                    "-b",
                    branch,
                    str(target_root),
                    control["head"],
                ],
                cwd=str(control_repo_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="strict",
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError, UnicodeError):
            return "execution_target_prepare_unavailable"
        if completed.returncode != 0:
            return "execution_target_prepare_failed"
        transition = "prepared"

    target, target_error = _inspect_clean_lawb_worktree(target_root)
    if target_error is not None or target is None:
        return target_error or "execution_target_validation_failed"
    if target["branch"] != branch:
        return "execution_target_branch_mismatch"
    if target["head"] != control["head"]:
        return "execution_target_head_mismatch"
    if target["status"]:
        return "execution_target_worktree_dirty"
    if target["staged"]:
        return "execution_target_staged_changes_present"

    routing = {
        "protocol": ROUTING_PROTOCOL_V2,
        "repository": DEFAULT_REPOSITORY,
        "selected_target": {
            "selection_id": selection_id,
            "target_repo_root": target["root"],
            "branch": target["branch"],
            "head": target["head"],
        },
    }
    try:
        write_durable_json(
            routing_path,
            routing,
            operator_session_id=operator_session_id,
        )
    except (OSError, LifecycleEvidenceError):
        return "execution_target_routing_write_failed"
    summary["execution_target_transition"] = transition
    summary["execution_target_selection_id"] = selection_id
    return None


def _dispatcher_rejection_terminal(request_id: str, now: datetime) -> dict[str, Any]:
    return {
        "evidence_id": f"local-dispatcher:{request_id}",
        "author": "local-dispatcher-v1",
        "result": "blocked",
        "settlement": "settled_non_success",
        "reconciliation_decision": "DISPATCHER_REJECTED_BEFORE_RUNNER",
        "reconciliation_reason": "STRUCTURED_PRE_RUNNER_REJECTION",
        "observed_at_utc": _format_time(now),
    }


def _health_probe_request_validity(
    expires: Any,
    now: datetime,
) -> tuple[str | None, float | None]:
    if not isinstance(expires, str):
        return "health_probe_expiry_invalid", None
    try:
        expires_at = datetime.strptime(
            expires,
            "%Y%m%dT%H%M%SZ",
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        return "health_probe_expiry_invalid", None
    remaining = (expires_at - now.astimezone(timezone.utc)).total_seconds()
    if remaining <= 0:
        return "health_probe_expired", remaining
    if remaining > HEALTH_PROBE_REQUEST_EXPIRY_SECONDS:
        return "health_probe_expiry_exceeds_5_minutes", remaining
    return None, remaining


def _post_dispatch_reconciliation_reason(reconciliation: Any) -> str:
    return {
        "MULTIPLE_MATCHING_COMPLETIONS": "multiple_matching_results",
        "UNTRUSTED_AUTHOR": "untrusted_result_author",
        "MALFORMED_EVIDENCE": "malformed_result_evidence",
        "UNSUPPORTED_PROTOCOL": "unsupported_result_protocol",
        "UNSUPPORTED_TERMINAL_RESULT": "unsupported_terminal_result",
        "CONFLICTING_EVIDENCE": "conflicting_result_evidence",
        "REPOSITORY_MISMATCH": "target_result_identity_mismatch",
        "ISSUE_MISMATCH": "target_result_identity_mismatch",
        "SURFACE_MISMATCH": "target_result_identity_mismatch",
        "ACTION_MISMATCH": "target_result_identity_mismatch",
        "BRANCH_MISMATCH": "target_result_identity_mismatch",
        "HEAD_MISMATCH": "target_result_identity_mismatch",
    }.get(reconciliation.reason.value, "durable_reconciliation_blocked")


def _invoke_lifecycle_fault(
    injector: Callable[[str], None] | None,
    stage: str,
    summary: dict[str, Any],
) -> str | None:
    if injector is None:
        return None
    try:
        injector(stage)
    except Exception as error:
        summary["fault_injection_stage"] = stage
        summary["fault_injection_error_type"] = type(error).__name__
        reason = f"fault_injected_{stage}"
        _block(summary, reason)
        return reason
    return None


def _processed_record_matches_in_flight(
    record: dict[str, Any], in_flight: dict[str, Any]
) -> bool:
    return (
        (record.get("target_repository") or DEFAULT_REPOSITORY)
        == in_flight.get("target_repository")
        and record.get("target_issue") == in_flight.get("target_issue")
        and record.get("target_dispatch_request_id")
        == in_flight.get("dispatch_request_id")
        and record.get("requested_action") == in_flight.get("action")
        and record.get("expected_branch") == in_flight.get("branch")
        and record.get("expected_head") == in_flight.get("expected_head")
    )


def _b1_identity_from_in_flight(
    in_flight: dict[str, Any]
) -> dict[str, Any]:
    return {
        "request_id": in_flight["request_id"],
        "target_repository": in_flight["target_repository"],
        "target_issue": in_flight["target_issue"],
        "target_dispatch_request_id": in_flight["dispatch_request_id"],
        "requested_action": in_flight["action"],
        "expected_branch": in_flight["branch"],
        "expected_head": in_flight["expected_head"],
    }


def _recover_existing_in_flight(
    *,
    state_root: Path,
    control_repo_root: Path,
    target_repo_root: Path,
    in_flight: dict[str, Any],
    repository: str,
    client: Any,
    provider: Any | None,
    cycle: int,
    now: datetime,
    summary: dict[str, Any],
) -> dict[str, Any]:
    outcome = {"reason": None, "settled_non_success": False}
    summary["restart_reconciliation_performed"] = True
    summary["in_flight_stage"] = in_flight["stage"]
    summary["in_flight_operator_session_id"] = in_flight[
        "operator_session_id"
    ]
    summary["request_id"] = in_flight["request_id"]
    summary["target_repository"] = in_flight["target_repository"]
    summary["target_issue"] = in_flight["target_issue"]
    summary["target_dispatch_request_id"] = in_flight[
        "dispatch_request_id"
    ]
    summary["requested_action"] = in_flight["action"]
    summary["expected_branch"] = in_flight["branch"]
    summary["expected_head"] = in_flight["expected_head"]
    if in_flight["target_repository"] != repository:
        outcome["reason"] = "in_flight_target_repository_mismatch"
        return outcome

    processed_path = state_root / "processed_requests.jsonl"
    try:
        records = (
            _read_processed_request_records(
                processed_path,
                repository=repository,
            )
            if processed_path.exists()
            else {}
        )
    except (OSError, ValueError):
        outcome["reason"] = "corrupted_state"
        return outcome
    existing = records.get(str(in_flight["request_id"]))
    if existing is not None:
        if (
            in_flight["stage"] == PREPARED
            or not _processed_record_matches_in_flight(existing, in_flight)
        ):
            outcome["reason"] = "processed_in_flight_identity_conflict"
            return outcome
        try:
            remove_exact_json(state_root / "in_flight.json", in_flight)
        except (OSError, LifecycleEvidenceError):
            outcome["reason"] = "in_flight_release_failed"
            return outcome
        summary["processed_request_already_seen"] = True
        summary["in_flight_present"] = False
        summary["in_flight_stage"] = None
        summary["phase"] = "restart_processed"
        summary["current_delegation_outcome"] = "restart_local_processed_record"
        if existing.get("completion_source") == DISPATCHER_OUTCOME_COMPLETION_SOURCE:
            summary["dispatcher_invoked"] = True
            summary["dispatcher_execution_reach"] = (
                DISPATCHER_REJECTED_BEFORE_RUNNER
            )
            summary["runner_reached"] = False
            summary["codex_reached"] = False
            summary["terminal_result"] = existing.get("terminal_result")
            summary["terminal_settlement"] = existing.get(
                "terminal_settlement"
            )
            summary["terminal_observed_at_utc"] = existing.get(
                "terminal_observed_at_utc"
            )
        outcome["settled_non_success"] = (
            existing.get("terminal_settlement") == "settled_non_success"
        )
        return outcome

    if in_flight["stage"] == REJECTED_BEFORE_RUNNER:
        terminal = in_flight["terminal_evidence"]
        b1_identity = _b1_identity_from_in_flight(in_flight)
        try:
            _append_dispatcher_rejection_processed_request(
                state_root,
                b1_identity,
                terminal,
                cycle,
                now,
            )
            processed_in_flight = updated_in_flight_payload(
                in_flight,
                stage=PROCESSED,
                dispatcher_invoked=True,
                terminal_evidence=terminal,
                updated_at=now,
            )
            write_durable_json(
                state_root / "in_flight.json",
                processed_in_flight,
                operator_session_id=in_flight["operator_session_id"],
            )
            remove_exact_json(
                state_root / "in_flight.json",
                processed_in_flight,
            )
        except (OSError, LifecycleEvidenceError):
            outcome["reason"] = "restart_processed_transition_failed"
            return outcome
        summary["processed_request_written"] = True
        summary["dispatcher_invoked"] = True
        summary["dispatcher_execution_reach"] = DISPATCHER_REJECTED_BEFORE_RUNNER
        summary["runner_reached"] = False
        summary["codex_reached"] = False
        summary["terminal_result"] = terminal["result"]
        summary["terminal_settlement"] = terminal["settlement"]
        summary["terminal_observed_at_utc"] = terminal["observed_at_utc"]
        summary["in_flight_present"] = False
        summary["in_flight_stage"] = None
        summary["phase"] = "restart_processed"
        summary["current_delegation_outcome"] = (
            "restart_dispatcher_rejected_before_runner"
        )
        outcome["settled_non_success"] = True
        return outcome

    if in_flight["stage"] == PREPARED:
        outcome["reason"] = "prepared_in_flight_uncertain"
        return outcome
    if in_flight["stage"] == PROCESSED:
        outcome["reason"] = "processed_in_flight_record_missing"
        return outcome

    reconciliation = _resolve_reconciliation(
        _request_identity_from_in_flight(in_flight),
        _reconciliation_provider(provider, client, repository),
        summary,
    )
    _copy_reconciliation_result(summary, reconciliation)
    if reconciliation.decision not in {
        ReconciliationDecision.COMPLETED,
        ReconciliationDecision.SETTLED_NON_SUCCESS,
    }:
        outcome["reason"] = "dispatched_in_flight_uncertain"
        return outcome

    review_candidate_error = _persist_review_candidate_if_available(
        state_root=state_root,
        b1_summary=_b1_identity_from_in_flight(in_flight),
        reconciliation=reconciliation,
        now=now,
        operator_session_id=str(in_flight["operator_session_id"]),
        summary=summary,
        control_repo_root=control_repo_root,
        target_repo_root=target_repo_root,
    )
    if review_candidate_error is not None:
        outcome["reason"] = review_candidate_error
        return outcome
    try:
        _append_reconciled_processed_request(
            state_root,
            _b1_identity_from_in_flight(in_flight),
            reconciliation,
            cycle,
            now,
            dispatcher_invoked=True,
        )
    except (OSError, LifecycleEvidenceError):
        outcome["reason"] = "processed_request_write_failed"
        return outcome
    terminal = _terminal_evidence(reconciliation, now)
    summary["terminal_observed_at_utc"] = terminal["observed_at_utc"]
    processed_in_flight = updated_in_flight_payload(
        in_flight,
        stage=PROCESSED,
        dispatcher_invoked=True,
        terminal_evidence=terminal,
        updated_at=now,
    )
    try:
        write_durable_json(
            state_root / "in_flight.json",
            processed_in_flight,
            operator_session_id=in_flight["operator_session_id"],
        )
        remove_exact_json(
            state_root / "in_flight.json",
            processed_in_flight,
        )
    except (OSError, LifecycleEvidenceError):
        outcome["reason"] = "restart_processed_transition_failed"
        return outcome
    summary["processed_request_written"] = True
    summary["durable_completion_reconciled"] = True
    summary["dispatcher_result_writeback_reached"] = True
    summary["dispatcher_result_writeback_verified"] = True
    summary["target_result_verified"] = True
    summary["target_result_comment_id"] = terminal["evidence_id"]
    summary["target_result_author"] = terminal["author"]
    summary["in_flight_present"] = False
    summary["in_flight_stage"] = None
    summary["phase"] = "restart_reconciled"
    summary["current_delegation_outcome"] = "restart_terminal_reconciled"
    outcome["settled_non_success"] = (
        reconciliation.decision
        == ReconciliationDecision.SETTLED_NON_SUCCESS
    )
    return outcome


def _append_observation_if_new(
    state_dir: Path,
    b1_summary: dict[str, Any],
    cycle: int,
    now: datetime,
) -> bool:
    path = state_dir / "dry_run_observations.jsonl"
    request_id = str(b1_summary.get("request_id") or "")
    repository = str(b1_summary.get("target_repository") or b1_summary.get("repository") or DEFAULT_REPOSITORY)
    observed = _read_observed_request_identities(path) if path.exists() else set()
    if (repository, request_id) in observed:
        return False
    observation = {
        "protocol": OBSERVATION_PROTOCOL,
        "observed_at_utc": _format_time(now),
        "cycle": cycle,
        "request_id": request_id,
        "target_repository": repository,
        "target_issue": b1_summary.get("target_issue"),
        "target_dispatch_request_id": b1_summary.get("target_dispatch_request_id"),
        "requested_action": b1_summary.get("requested_action"),
        "expected_branch": b1_summary.get("expected_branch"),
        "expected_head": b1_summary.get("expected_head"),
        "dry_run_result": b1_summary.get("dry_run_result"),
    }
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        json.dump(observation, handle, sort_keys=True)
        handle.write("\n")
    return True


def _validate_same_node_launcher_binding(
    *, repository: str, b1_summary: dict[str, Any], continuation: dict[str, Any]
) -> tuple[dict[str, Any] | None, str | None]:
    """Require the launcher's exact dirty-candidate handoff; never grant admission."""
    raw = os.environ.get(SAME_NODE_LAUNCHER_BINDING_ENV)
    if not raw:
        return None, "same_node_continuation_launcher_binding_missing"
    try:
        binding = json.loads(raw)
    except (TypeError, ValueError):
        return None, "same_node_continuation_launcher_binding_invalid"
    expected_keys = {
        "protocol",
        "repository",
        "issue",
        "parent_comment_id",
        "branch",
        "head",
        "candidate_manifest_fingerprint",
        "remaining_budget_before",
        "is_human_approval",
    }
    if not isinstance(binding, dict) or set(binding) != expected_keys:
        return None, "same_node_continuation_launcher_binding_invalid"
    issue = binding.get("issue")
    budget = binding.get("remaining_budget_before")
    fingerprint = binding.get("candidate_manifest_fingerprint")
    if (
        binding.get("protocol") != SAME_NODE_LAUNCHER_BINDING_PROTOCOL
        or type(issue) is not int
        or issue <= 0
        or type(budget) is not int
        or budget != 1
        or binding.get("is_human_approval") is not False
        or not isinstance(fingerprint, str)
        or re.fullmatch(r"[0-9a-f]{64}", fingerprint) is None
    ):
        return None, "same_node_continuation_launcher_binding_invalid"
    expected = {
        "repository": repository,
        "issue": b1_summary.get("target_issue"),
        "parent_comment_id": continuation.get("parent_comment_id"),
        "branch": b1_summary.get("expected_branch"),
        "head": str(b1_summary.get("expected_head") or "").lower(),
    }
    if any(binding.get(key) != value for key, value in expected.items()):
        return None, "same_node_continuation_launcher_binding_mismatch"
    return binding, None


def _delegate_b3_request(
    *,
    state_root: Path,
    repo_root: str | Path,
    control_repo_root: str | Path,
    repository: str,
    client: Any,
    b1_summary: dict[str, Any],
    cycle: int,
    now: datetime,
    summary: dict[str, Any],
    dispatcher_invoker: Any | None,
    timeout_seconds: int | None,
    durable_evidence_provider: Any | None,
    operator_session_id: str,
    process_identity: dict[str, Any],
    lifecycle_fault_injector: Callable[[str], None] | None,
) -> str | None:
    summary["current_delegation_outcome"] = None
    action = b1_summary.get("requested_action")
    if summary.get("mode") == B3B_MODE and action != B3B_ALLOWED_ACTION:
        _block(summary, "run_reviewbundle_not_enabled_in_b3b")
        return "run_reviewbundle_not_enabled_in_b3b"
    if summary.get("mode") == B3C_MODE and action not in {
        B3B_ALLOWED_ACTION,
        B3C_ALLOWED_ACTION,
        B3C_FINAL_AUDIT_ACTION,
    }:
        _block(summary, "unsupported_action_in_b3c")
        return "unsupported_action_in_b3c"
    if action == B3B_ALLOWED_ACTION:
        expiry_error, remaining_seconds = _health_probe_request_validity(
            b1_summary.get("expires"),
            now,
        )
        summary["health_probe_request_remaining_seconds"] = remaining_seconds
        if expiry_error is not None:
            if expiry_error not in NONFATAL_REQUEST_REJECTION_REASONS:
                _block(summary, expiry_error)
            return expiry_error
    readiness = b1_summary.get("local_readiness") or {}
    continuation = b1_summary.get("same_node_candidate_continuation") or {}
    continuation_admitted = continuation.get("admitted") is True
    if readiness.get("clean") is not True and not continuation_admitted:
        _block(summary, "dirty_repository")
        return "dirty_repository"
    if readiness.get("staged_clean") is not True:
        _block(summary, "staged_files_present")
        return "staged_files_present"
    if readiness.get("clean") is not True and action == B3C_ALLOWED_ACTION:
        binding, binding_error = _validate_same_node_launcher_binding(
            repository=repository,
            b1_summary=b1_summary,
            continuation=continuation,
        )
        if binding_error is not None:
            _block(summary, binding_error)
            return binding_error
        summary["same_node_candidate_continuation"] = {
            **continuation,
            "launcher_binding": "matched",
            "candidate_manifest_fingerprint": binding[
                "candidate_manifest_fingerprint"
            ],
            "remaining_budget_before": binding["remaining_budget_before"],
            "is_human_approval": False,
        }

    processed_path = state_root / "processed_requests.jsonl"
    request_id = str(b1_summary.get("request_id") or "")
    try:
        processed = (
            _read_processed_request_records(processed_path, repository=repository)
            if processed_path.exists()
            else {}
        )
    except (OSError, ValueError):
        _block(summary, "corrupted_state")
        return "corrupted_state"
    if request_id in processed:
        if not _processed_record_matches_b1_identity(processed[request_id], b1_summary):
            _block(summary, "processed_request_identity_mismatch")
            return "processed_request_identity_mismatch"
        summary["processed_request_already_seen"] = True
        summary["phase"] = "already_processed"
        summary["current_delegation_outcome"] = "local_processed_request_already_seen"
        return None

    reconciliation_provider = _reconciliation_provider(
        durable_evidence_provider,
        client,
        repository,
    )
    request_identity = _request_identity_from_b1(b1_summary, repository)
    reconciliation = _resolve_reconciliation(
        request_identity,
        reconciliation_provider,
        summary,
    )
    _copy_reconciliation_result(summary, reconciliation)
    if reconciliation.decision in {
        ReconciliationDecision.COMPLETED,
        ReconciliationDecision.SETTLED_NON_SUCCESS,
    }:
        review_candidate_error = _persist_review_candidate_if_available(
            state_root=state_root,
            b1_summary=b1_summary,
            reconciliation=reconciliation,
            now=now,
            operator_session_id=operator_session_id,
            summary=summary,
            control_repo_root=Path(control_repo_root),
            target_repo_root=Path(repo_root),
        )
        if review_candidate_error is not None:
            return review_candidate_error
        _append_reconciled_processed_request(
            state_root,
            b1_summary,
            reconciliation,
            cycle,
            now,
            dispatcher_invoked=False,
        )
        summary["processed_request_written"] = True
        summary["durable_completion_reconciled"] = True
        summary["terminal_observed_at_utc"] = _format_time(now)
        if reconciliation.decision == ReconciliationDecision.SETTLED_NON_SUCCESS:
            summary["current_delegation_outcome"] = "durable_terminal_non_success_reconciled"
            _block(summary, "durable_terminal_non_success")
            return "durable_terminal_non_success"
        summary["phase"] = "reconciled_completed"
        summary["current_delegation_outcome"] = "durable_completion_reconciled"
        return None
    if reconciliation.decision == ReconciliationDecision.BLOCKED:
        _block(summary, "durable_reconciliation_blocked")
        return "durable_reconciliation_blocked"
    if reconciliation.decision == ReconciliationDecision.ERROR:
        _block(summary, "durable_reconciliation_error")
        return "durable_reconciliation_error"
    if reconciliation.decision != ReconciliationDecision.NOT_FOUND:
        _block(summary, "durable_reconciliation_unexpected_decision")
        return "durable_reconciliation_unexpected_decision"

    fault_reason = _invoke_lifecycle_fault(
        lifecycle_fault_injector,
        "before_durable_admit",
        summary,
    )
    if fault_reason is not None:
        return fault_reason

    in_flight_path = state_root / "in_flight.json"
    in_flight = new_in_flight_payload(
        request_id=request_id,
        target_repository=repository,
        target_issue=int(b1_summary["target_issue"]),
        dispatch_request_id=str(b1_summary["target_dispatch_request_id"]),
        action=str(action),
        branch=str(b1_summary["expected_branch"]),
        expected_head=str(b1_summary["expected_head"]).lower(),
        operator_session_id=operator_session_id,
        process_identity=process_identity,
        prepared_at=now,
    )
    try:
        write_durable_json(
            in_flight_path,
            in_flight,
            operator_session_id=operator_session_id,
        )
    except (OSError, LifecycleEvidenceError):
        _block(summary, "in_flight_write_failed")
        return "in_flight_write_failed"
    summary["in_flight_present"] = True
    summary["in_flight_stage"] = PREPARED
    summary["in_flight_operator_session_id"] = operator_session_id

    fault_reason = _invoke_lifecycle_fault(
        lifecycle_fault_injector,
        "after_prepared_before_dispatch",
        summary,
    )
    if fault_reason is not None:
        return fault_reason

    invoker = dispatcher_invoker or default_dispatcher_invoker
    configured_timeout = (
        timeout_seconds if timeout_seconds is not None else DEFAULT_TIMEOUT_SECONDS
    )
    timeout = (
        min(configured_timeout, HEALTH_PROBE_RESULT_TIMEOUT_SECONDS)
        if action == B3B_ALLOWED_ACTION
        else configured_timeout
    )
    summary["effective_dispatcher_timeout_seconds"] = timeout
    args = build_dispatcher_command(
        repo_root=control_repo_root,
        target_repo_root=repo_root,
        target_issue=int(b1_summary["target_issue"]),
        relay_request=build_relay_dispatch_contract(b1_summary),
        repository=repository,
    )
    summary["dispatcher_invocation_args"] = args
    summary["operator_direct_execution_performed"] = True
    summary["dispatcher_invoked"] = True
    summary["dispatcher_invocation_count"] += 1

    try:
        invocation = invoker(
            args=args,
            cwd=str(Path(control_repo_root).resolve()),
            timeout_seconds=timeout,
        )
    except TimeoutError as error:
        invocation = DispatcherInvocationResult(returncode=1, stderr=str(error), timed_out=True)
    except FileNotFoundError as error:
        invocation = DispatcherInvocationResult(returncode=1, stderr=str(error), timed_out=False)
        summary["dispatcher_missing"] = True
    except Exception as error:
        invocation = DispatcherInvocationResult(returncode=1, stderr=str(error), timed_out=False)

    summary["dispatcher_exit_code"] = invocation.returncode
    summary["dispatcher_timed_out"] = bool(invocation.timed_out)
    summary["dispatcher_stdout"] = invocation.stdout
    summary["dispatcher_stderr"] = invocation.stderr
    summary["dispatcher_execution_reach"] = invocation.execution_reach

    confirmed_pre_runner_rejection = (
        not summary.get("dispatcher_missing")
        and not invocation.timed_out
        and invocation.returncode == DISPATCHER_REJECTED_BEFORE_RUNNER_EXIT_CODE
        and invocation.execution_reach == DISPATCHER_REJECTED_BEFORE_RUNNER
    )
    if confirmed_pre_runner_rejection:
        summary["runner_reached"] = False
        summary["codex_reached"] = False
        terminal = _dispatcher_rejection_terminal(request_id, now)
        rejected_in_flight = updated_in_flight_payload(
            in_flight,
            stage=REJECTED_BEFORE_RUNNER,
            dispatcher_invoked=True,
            terminal_evidence=terminal,
            updated_at=now,
        )
        try:
            write_durable_json(
                in_flight_path,
                rejected_in_flight,
                operator_session_id=operator_session_id,
            )
        except (OSError, LifecycleEvidenceError):
            _block(summary, "in_flight_rejection_transition_failed")
            return "in_flight_rejection_transition_failed"
        summary["in_flight_stage"] = REJECTED_BEFORE_RUNNER
        fault_reason = _invoke_lifecycle_fault(
            lifecycle_fault_injector,
            "after_pre_runner_rejection_before_processed",
            summary,
        )
        if fault_reason is not None:
            return fault_reason
        try:
            _append_dispatcher_rejection_processed_request(
                state_root,
                b1_summary,
                terminal,
                cycle,
                now,
            )
        except (OSError, LifecycleEvidenceError):
            _block(summary, "processed_request_write_failed")
            return "processed_request_write_failed"
        summary["processed_request_written"] = True
        processed_in_flight = updated_in_flight_payload(
            rejected_in_flight,
            stage=PROCESSED,
            dispatcher_invoked=True,
            terminal_evidence=terminal,
            updated_at=now,
        )
        try:
            write_durable_json(
                in_flight_path,
                processed_in_flight,
                operator_session_id=operator_session_id,
            )
            remove_exact_json(in_flight_path, processed_in_flight)
        except (OSError, LifecycleEvidenceError):
            _block(summary, "in_flight_processed_transition_failed")
            return "in_flight_processed_transition_failed"
        summary["in_flight_present"] = False
        summary["in_flight_stage"] = None
        summary["terminal_result"] = terminal["result"]
        summary["terminal_settlement"] = terminal["settlement"]
        summary["terminal_observed_at_utc"] = terminal["observed_at_utc"]
        summary["current_delegation_outcome"] = DISPATCHER_REJECTED_BEFORE_RUNNER
        _block(summary, "dispatcher_rejected_before_runner")
        return "dispatcher_rejected_before_runner"

    confirmed_pre_runner_failure = (
        not invocation.timed_out
        and (
            summary.get("dispatcher_missing")
            or (
                invocation.returncode == DISPATCHER_FAILED_BEFORE_RUNNER_EXIT_CODE
                and invocation.execution_reach == DISPATCHER_FAILED_BEFORE_RUNNER
            )
        )
    )
    if confirmed_pre_runner_failure:
        summary["runner_reached"] = False
        summary["codex_reached"] = False
        try:
            remove_exact_json(in_flight_path, in_flight)
        except (OSError, LifecycleEvidenceError):
            _block(summary, "in_flight_pre_runner_failure_cleanup_failed")
            return "in_flight_pre_runner_failure_cleanup_failed"
        summary["in_flight_present"] = False
        summary["in_flight_stage"] = None
        if summary.get("dispatcher_missing"):
            _block(summary, "dispatcher_missing")
            return "dispatcher_missing"
        _block(summary, "dispatcher_pre_runner_transient_failure")
        return "dispatcher_pre_runner_transient_failure"

    if invocation.execution_reach == DISPATCHER_RUNNER_MAY_HAVE_STARTED:
        summary["runner_reached"] = None
        summary["codex_reached"] = None

    if not summary.get("dispatcher_missing"):
        in_flight = updated_in_flight_payload(
            in_flight,
            stage=DISPATCHED_NOT_LOCALLY_SETTLED,
            dispatcher_invoked=True,
            terminal_evidence=None,
            updated_at=now,
        )
        try:
            write_durable_json(
                in_flight_path,
                in_flight,
                operator_session_id=operator_session_id,
            )
        except (OSError, LifecycleEvidenceError):
            _block(summary, "in_flight_dispatch_transition_failed")
            return "in_flight_dispatch_transition_failed"
        summary["in_flight_stage"] = DISPATCHED_NOT_LOCALLY_SETTLED

    if summary.get("dispatcher_missing"):
        _block(summary, "dispatcher_missing")
        return "dispatcher_missing"
    if invocation.timed_out:
        _block(summary, "dispatcher_timeout")
        return "dispatcher_timeout"
    if invocation.returncode != 0:
        _block(summary, "dispatcher_nonzero_exit")
        return "dispatcher_nonzero_exit"

    fault_reason = _invoke_lifecycle_fault(
        lifecycle_fault_injector,
        "after_dispatch_before_processed",
        summary,
    )
    if fault_reason is not None:
        return fault_reason

    reconciliation = _resolve_reconciliation(
        request_identity,
        reconciliation_provider,
        summary,
    )
    _copy_reconciliation_result(summary, reconciliation)
    if reconciliation.decision == ReconciliationDecision.NOT_FOUND:
        _block(summary, "target_result_missing")
        return "target_result_missing"
    if reconciliation.decision == ReconciliationDecision.ERROR:
        _block(summary, "github_read_unavailable")
        return "github_read_unavailable"
    if reconciliation.decision == ReconciliationDecision.BLOCKED:
        reason = _post_dispatch_reconciliation_reason(reconciliation)
        if reconciliation.matched_evidence_ids:
            summary["dispatcher_result_writeback_reached"] = True
        _block(summary, reason)
        return reason
    if reconciliation.decision not in {
        ReconciliationDecision.COMPLETED,
        ReconciliationDecision.SETTLED_NON_SUCCESS,
    }:
        _block(summary, "durable_reconciliation_unexpected_decision")
        return "durable_reconciliation_unexpected_decision"

    terminal = _terminal_evidence(reconciliation, now)
    summary["terminal_observed_at_utc"] = terminal["observed_at_utc"]
    summary["dispatcher_result_writeback_reached"] = True
    summary["target_result_comment_id"] = reconciliation.matched_evidence_ids[0]
    summary["target_result_author"] = reconciliation.terminal_author
    summary["target_result_verified"] = True
    summary["dispatcher_result_writeback_verified"] = True
    review_candidate_error = _persist_review_candidate_if_available(
        state_root=state_root,
        b1_summary=b1_summary,
        reconciliation=reconciliation,
        now=now,
        operator_session_id=operator_session_id,
        summary=summary,
        control_repo_root=Path(control_repo_root),
        target_repo_root=Path(repo_root),
    )
    if review_candidate_error is not None:
        return review_candidate_error
    _append_processed_request(
        state_root,
        b1_summary,
        terminal,
        cycle,
        now,
    )
    summary["processed_request_written"] = True
    in_flight = updated_in_flight_payload(
        in_flight,
        stage=PROCESSED,
        dispatcher_invoked=True,
        terminal_evidence=terminal,
        updated_at=now,
    )
    try:
        write_durable_json(
            in_flight_path,
            in_flight,
            operator_session_id=operator_session_id,
        )
    except (OSError, LifecycleEvidenceError):
        _block(summary, "in_flight_processed_transition_failed")
        return "in_flight_processed_transition_failed"
    summary["in_flight_stage"] = PROCESSED

    fault_reason = _invoke_lifecycle_fault(
        lifecycle_fault_injector,
        "after_processed_durable",
        summary,
    )
    if fault_reason is not None:
        return fault_reason
    try:
        remove_exact_json(in_flight_path, in_flight)
    except (OSError, LifecycleEvidenceError):
        _block(summary, "in_flight_release_failed")
        return "in_flight_release_failed"
    summary["in_flight_present"] = False
    summary["in_flight_stage"] = None
    if reconciliation.decision == ReconciliationDecision.SETTLED_NON_SUCCESS:
        summary["current_delegation_outcome"] = "verified_terminal_non_success"
        _block(summary, "target_result_not_success")
        return "target_result_not_success"
    summary["current_delegation_outcome"] = "verified_dispatcher_result"
    return None


def _append_processed_request(
    state_dir: Path,
    b1_summary: dict[str, Any],
    terminal: dict[str, Any],
    cycle: int,
    now: datetime,
) -> None:
    path = state_dir / "processed_requests.jsonl"
    payload = {
        "protocol": PROCESSED_REQUEST_PROTOCOL,
        "processed_at_utc": _format_time(now),
        "cycle": cycle,
        "request_id": b1_summary.get("request_id"),
        "target_repository": b1_summary.get("target_repository", b1_summary.get("repository")),
        "target_issue": b1_summary.get("target_issue"),
        "target_dispatch_request_id": b1_summary.get("target_dispatch_request_id"),
        "requested_action": b1_summary.get("requested_action"),
        "expected_branch": b1_summary.get("expected_branch"),
        "expected_head": b1_summary.get("expected_head"),
        "target_result_comment_id": terminal.get("evidence_id"),
        "target_result_author": terminal.get("author"),
        "terminal_result": terminal.get("result"),
        "terminal_settlement": terminal.get("settlement"),
        "terminal_observed_at_utc": terminal.get("observed_at_utc"),
        "dispatcher_invoked": True,
        "result_verified": True,
        "lifecycle_state": CONSUMED,
    }
    append_jsonl_durable(path, payload)


def _append_dispatcher_rejection_processed_request(
    state_dir: Path,
    b1_summary: dict[str, Any],
    terminal: dict[str, Any],
    cycle: int,
    now: datetime,
) -> None:
    payload = {
        "protocol": PROCESSED_REQUEST_PROTOCOL,
        "processed_at_utc": _format_time(now),
        "cycle": cycle,
        "request_id": b1_summary.get("request_id"),
        "target_repository": b1_summary.get(
            "target_repository", b1_summary.get("repository")
        ),
        "target_issue": b1_summary.get("target_issue"),
        "target_dispatch_request_id": b1_summary.get(
            "target_dispatch_request_id"
        ),
        "requested_action": b1_summary.get("requested_action"),
        "expected_branch": b1_summary.get("expected_branch"),
        "expected_head": b1_summary.get("expected_head"),
        "lifecycle_state": CONSUMED,
        "completion_source": DISPATCHER_OUTCOME_COMPLETION_SOURCE,
        "dispatcher_invoked": True,
        "dispatcher_execution_reach": DISPATCHER_REJECTED_BEFORE_RUNNER,
        "result_verified": False,
        "terminal_result": terminal["result"],
        "terminal_settlement": terminal["settlement"],
        "terminal_observed_at_utc": terminal["observed_at_utc"],
    }
    append_jsonl_durable(state_dir / "processed_requests.jsonl", payload)


def _append_reconciled_processed_request(
    state_dir: Path,
    b1_summary: dict[str, Any],
    reconciliation: Any,
    cycle: int,
    now: datetime,
    *,
    dispatcher_invoked: bool,
) -> None:
    path = state_dir / "processed_requests.jsonl"
    payload = {
        "protocol": PROCESSED_REQUEST_PROTOCOL,
        "processed_at_utc": _format_time(now),
        "cycle": cycle,
        "request_id": b1_summary.get("request_id"),
        "target_repository": b1_summary.get("target_repository", b1_summary.get("repository")),
        "target_issue": b1_summary.get("target_issue"),
        "target_dispatch_request_id": b1_summary.get("target_dispatch_request_id"),
        "requested_action": b1_summary.get("requested_action"),
        "expected_branch": b1_summary.get("expected_branch"),
        "expected_head": b1_summary.get("expected_head"),
        "lifecycle_state": CONSUMED,
        "completion_source": "durable_evidence_reconciliation",
        "dispatcher_invoked": dispatcher_invoked,
        "result_verified": True,
        "reconciliation_decision": reconciliation.decision.value,
        "reconciliation_reason": reconciliation.reason.value,
        "reconciliation_matched_evidence_ids": list(reconciliation.matched_evidence_ids),
        "terminal_result": reconciliation.terminal_result,
        "terminal_settlement": (
            "settled_success"
            if reconciliation.terminal_result == "success"
            else "settled_non_success"
        ),
        "terminal_observed_at_utc": _format_time(now),
        "target_result_comment_id": reconciliation.matched_evidence_ids[0],
        "target_result_author": reconciliation.terminal_author,
    }
    append_jsonl_durable(path, payload)


def _read_observed_request_identities(path: Path) -> set[tuple[str, str]]:
    identities: set[tuple[str, str]] = set()
    if not path.exists():
        return identities
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict) or "request_id" not in payload:
            raise ValueError("invalid_observation")
        repository = str(payload.get("target_repository") or DEFAULT_REPOSITORY)
        identities.add((repository, str(payload["request_id"])))
    return identities


def _read_observed_request_ids(path: Path) -> set[str]:
    return {request_id for _, request_id in _read_observed_request_identities(path)}


def _read_all_processed_request_records(
    path: Path,
) -> dict[tuple[str, str], dict[str, Any]]:
    records: dict[tuple[str, str], dict[str, Any]] = {}
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = _parse_processed_request_record(line)
        repository = str(payload.get("target_repository") or DEFAULT_REPOSITORY)
        identity = (repository, payload["request_id"])
        if identity in records:
            raise ValueError("invalid_processed_request")
        records[identity] = payload
    return records


def _read_processed_request_records(
    path: Path,
    *,
    repository: str = DEFAULT_REPOSITORY,
) -> dict[str, dict[str, Any]]:
    return {
        request_id: payload
        for (record_repository, request_id), payload in _read_all_processed_request_records(path).items()
        if record_repository == repository
    }


def _parse_processed_request_record(line: str) -> dict[str, Any]:
    try:
        payload = json.loads(line, object_pairs_hook=_reject_duplicate_json_keys)
    except json.JSONDecodeError as error:
        raise ValueError("invalid_processed_request") from error
    _validate_processed_request_record(payload)
    return payload


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _validate_processed_request_record(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise ValueError("invalid_processed_request")
    if payload.get("protocol") != PROCESSED_REQUEST_PROTOCOL:
        raise ValueError("invalid_processed_request")
    request_id = payload.get("request_id")
    if not isinstance(request_id, str) or not REQUEST_ID_PATTERN.fullmatch(request_id):
        raise ValueError("invalid_processed_request")
    lifecycle_state = payload.get("lifecycle_state")
    if "lifecycle_state" in payload and lifecycle_state != CONSUMED:
        raise ValueError("invalid_processed_request")
    completion_source = payload.get("completion_source")
    if completion_source not in {
        None,
        "durable_evidence_reconciliation",
        DISPATCHER_OUTCOME_COMPLETION_SOURCE,
    }:
        raise ValueError("invalid_processed_request")
    if completion_source == "durable_evidence_reconciliation":
        _validate_reconciled_processed_record(payload)
    elif completion_source == DISPATCHER_OUTCOME_COMPLETION_SOURCE:
        _validate_dispatcher_outcome_processed_record(payload)
    elif "dispatcher_invoked" in payload and payload.get("dispatcher_invoked") is not True:
        raise ValueError("invalid_processed_request")
    if (
        completion_source != DISPATCHER_OUTCOME_COMPLETION_SOURCE
        and "result_verified" in payload
        and payload.get("result_verified") is not True
    ):
        raise ValueError("invalid_processed_request")
    terminal_result = payload.get("terminal_result")
    terminal_settlement = payload.get("terminal_settlement")
    if "terminal_result" in payload or "terminal_settlement" in payload:
        if terminal_result not in {"success", "failure", "blocked"}:
            raise ValueError("invalid_processed_request")
        expected_settlement = (
            "settled_success"
            if terminal_result == "success"
            else "settled_non_success"
        )
        if terminal_settlement != expected_settlement:
            raise ValueError("invalid_processed_request")
    terminal_observed_at = payload.get("terminal_observed_at_utc")
    if (
        "terminal_observed_at_utc" in payload
        and parse_utc(terminal_observed_at) is None
    ):
        raise ValueError("invalid_processed_request")
    target_repository = payload.get("target_repository")
    if target_repository is not None and target_repository not in SUPPORTED_TARGET_REPOSITORIES:
        raise ValueError("invalid_processed_request")
    identity_keys = (
        "target_issue",
        "target_dispatch_request_id",
        "requested_action",
        "expected_branch",
        "expected_head",
    )
    if not all(key in payload for key in identity_keys):
        raise ValueError("invalid_processed_request")
    if type(payload.get("target_issue")) is not int or payload["target_issue"] <= 0:
        raise ValueError("invalid_processed_request")
    for key in (
        "target_dispatch_request_id",
        "requested_action",
        "expected_branch",
        "expected_head",
    ):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise ValueError("invalid_processed_request")


def _validate_reconciled_processed_record(payload: dict[str, Any]) -> None:
    if type(payload.get("dispatcher_invoked")) is not bool:
        raise ValueError("invalid_processed_request")
    if payload.get("result_verified") is not True:
        raise ValueError("invalid_processed_request")
    if payload.get("lifecycle_state") != CONSUMED:
        raise ValueError("invalid_processed_request")
    decision_reason = (
        payload.get("reconciliation_decision"),
        payload.get("reconciliation_reason"),
    )
    if decision_reason not in {
        ("COMPLETED", "EXACTLY_ONE_TRUSTED_MATCH"),
        (
            "SETTLED_NON_SUCCESS",
            "EXACTLY_ONE_TRUSTED_NON_SUCCESS_MATCH",
        ),
    }:
        raise ValueError("invalid_processed_request")
    evidence_ids = payload.get("reconciliation_matched_evidence_ids")
    if (
        not isinstance(evidence_ids, list)
        or len(evidence_ids) != 1
        or not all(isinstance(evidence_id, str) and evidence_id.strip() for evidence_id in evidence_ids)
    ):
        raise ValueError("invalid_processed_request")


def _validate_dispatcher_outcome_processed_record(payload: dict[str, Any]) -> None:
    if (
        payload.get("lifecycle_state") != CONSUMED
        or payload.get("dispatcher_invoked") is not True
        or payload.get("dispatcher_execution_reach")
        != DISPATCHER_REJECTED_BEFORE_RUNNER
        or payload.get("result_verified") is not False
        or payload.get("terminal_result") != "blocked"
        or payload.get("terminal_settlement") != "settled_non_success"
    ):
        raise ValueError("invalid_processed_request")


def _processed_record_matches_b1_identity(
    record: dict[str, Any], b1_summary: dict[str, Any]
) -> bool:
    return (
        (record.get("target_repository") or DEFAULT_REPOSITORY)
        == b1_summary.get("target_repository", b1_summary.get("repository"))
        and record.get("target_issue") == b1_summary.get("target_issue")
        and record.get("target_dispatch_request_id")
        == b1_summary.get("target_dispatch_request_id")
        and record.get("requested_action") == b1_summary.get("requested_action")
        and record.get("expected_branch") == b1_summary.get("expected_branch")
        and record.get("expected_head") == b1_summary.get("expected_head")
    )


def read_processed_request_ids(path: str | Path) -> set[str]:
    """Read B3 processed request IDs without modifying operator state."""
    return set(_read_processed_request_records(Path(path)))


def read_processed_request_records(
    path: str | Path,
    *,
    repository: str = DEFAULT_REPOSITORY,
) -> dict[str, dict[str, Any]]:
    """Read validated B3 processed request identity records without modifying state."""
    return _read_processed_request_records(Path(path), repository=repository)


def _reset_request_execution_visibility(summary: dict[str, Any]) -> None:
    summary.update(
        {
            "health_probe_request_remaining_seconds": None,
            "processed_request_written": False,
            "processed_request_already_seen": False,
            "current_delegation_outcome": None,
            "status_progress_publication": "not_requested",
            "durable_reconciliation_performed": False,
            "durable_reconciliation_decision": None,
            "durable_reconciliation_reason": None,
            "durable_reconciliation_matched_evidence_ids": [],
            "durable_reconciliation_diagnostics": [],
            "durable_completion_reconciled": False,
            "terminal_result": None,
            "terminal_settlement": None,
            "terminal_observed_at_utc": None,
            "effective_dispatcher_timeout_seconds": None,
            "dispatcher_invocation_args": [],
            "dispatcher_exit_code": None,
            "dispatcher_timed_out": False,
            "dispatcher_missing": False,
            "dispatcher_stdout": "",
            "dispatcher_stderr": "",
            "dispatcher_execution_reach": None,
            "dispatcher_result_writeback_reached": False,
            "dispatcher_result_writeback_verified": False,
            "target_result_verified": False,
            "target_result_comment_id": None,
            "target_result_author": None,
            "runner_reached": None,
            "codex_reached": None,
            "operator_direct_execution_performed": False,
            "dispatcher_invoked": False,
            "current_failure_recorded": False,
            "current_failure_reason": None,
            "last_failure_json_applies_to_current_run": False,
            "current_run": {},
        }
    )


def _report_request_accepted_progress(
    summary: dict[str, Any], reporter: Callable[[dict[str, Any]], None] | None
) -> None:
    """Report only validated, request-bound non-terminal B3-C progress."""
    if reporter is None:
        return
    try:
        progress = _current_run_visibility(summary)
        progress.update(
            {
                "requested_action": summary.get("requested_action"),
                "expected_branch": summary.get("expected_branch"),
                "expected_head": summary.get("expected_head"),
            }
        )
        reporter(progress)
    except Exception:
        # A visibility write failure must not create a false terminal result or retry.
        summary["status_progress_publication"] = "unverified"
        return
    summary["status_progress_publication"] = "reported"


def _copy_b1_identity(summary: dict[str, Any], b1_summary: dict[str, Any]) -> None:
    # Latest lifecycle fields describe the most recent B1 evaluation cycle.
    # A consumed-only waiting cycle must clear current-selection visibility.
    for key in (
        "inbox_comment_id",
        "expires",
        "evaluated_at_utc",
        "current_request_count",
        "consumed_request_count",
        "expired_request_count",
        "selected_request_state",
    ):
        summary[key] = b1_summary.get(key)
    # Waiting cycles retain the most recent request for status visibility, but a
    # different CURRENT request must start with fresh execution/result fields.
    if b1_summary.get("selected_request_state") == "CURRENT":
        previous_identity = (
            summary.get("target_repository"),
            summary.get("request_id"),
        )
        next_identity = (
            b1_summary.get("target_repository", b1_summary.get("repository")),
            b1_summary.get("request_id"),
        )
        if previous_identity != next_identity:
            _reset_request_execution_visibility(summary)
        for key in (
            "request_id",
            "target_repository",
            "target_issue",
            "target_dispatch_request_id",
            "requested_action",
            "expected_branch",
            "expected_head",
        ):
            summary[key] = b1_summary.get(key)


def _request_lifecycle_visibility(summary: dict[str, Any]) -> dict[str, str]:
    """Derive only request-local stages that existing evidence can establish."""
    if summary.get("target_result_verified"):
        return {
            "stage": "TERMINAL_RESULT_READY",
            "certainty": "verified",
            "basis": "trusted_terminal_result",
        }
    if summary.get("current_failure_recorded"):
        return {
            "stage": "BLOCKED_OR_FAILED",
            "certainty": "verified",
            "basis": "current_failure_record",
        }
    reach = summary.get("dispatcher_execution_reach")
    if reach == DISPATCHER_REJECTED_BEFORE_RUNNER:
        return {
            "stage": "BLOCKED_OR_FAILED",
            "certainty": "verified",
            "basis": "dispatcher_rejected_before_runner",
        }
    if reach == DISPATCHER_FAILED_BEFORE_RUNNER:
        return {
            "stage": "BLOCKED_OR_FAILED",
            "certainty": "verified",
            "basis": "dispatcher_failed_before_runner",
        }
    if reach == DISPATCHER_RUNNER_MAY_HAVE_STARTED:
        return {
            "stage": "RUNNER_OR_CODEX_REACH_UNCERTAIN",
            "certainty": "unknown",
            "basis": "dispatcher_runner_reach_uncertain",
        }
    if summary.get("dispatcher_invoked"):
        return {
            "stage": "DISPATCHER_REACHED",
            "certainty": "verified",
            "basis": "operator_dispatcher_invocation",
        }
    if summary.get("selected_request_state") == "CURRENT" and summary.get("request_id"):
        return {
            "stage": "REQUEST_ACCEPTED",
            "certainty": "verified",
            "basis": "current_request_identity",
        }
    return {
        "stage": "UNKNOWN",
        "certainty": "unknown",
        "basis": "no_current_request_evidence",
    }


def _current_run_visibility(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": summary.get("request_id"),
        "issue_number": summary.get("target_issue"),
        "lifecycle": _request_lifecycle_visibility(summary),
        "mode": summary.get("mode"),
        "max_cycles": summary.get("configured_max_cycles"),
        "operator_dispatcher_invocation_performed": bool(
            summary.get("operator_direct_execution_performed")
        ),
        "dispatcher_invoked": bool(summary.get("dispatcher_invoked")),
        "dispatcher_execution_reach": summary.get("dispatcher_execution_reach"),
        "runner_reached": summary.get("runner_reached"),
        "codex_reached": summary.get("codex_reached"),
        "operator_direct_runner_invoked": bool(summary.get("runner_invoked")),
        "operator_direct_codex_invoked": bool(summary.get("codex_invoked")),
        "github_result_writeback_observed": bool(
            summary.get("dispatcher_result_writeback_reached")
            or summary.get("github_write_performed")
        ),
        "durable_reconciliation_performed": bool(
            summary.get("durable_reconciliation_performed")
        ),
        "durable_reconciliation_decision": summary.get("durable_reconciliation_decision"),
        "durable_reconciliation_reason": summary.get("durable_reconciliation_reason"),
        "durable_reconciliation_matched_evidence_ids": list(
            summary.get("durable_reconciliation_matched_evidence_ids", [])
        ),
        "durable_completion_reconciled": bool(summary.get("durable_completion_reconciled")),
        "current_failure_recorded": bool(summary.get("current_failure_recorded")),
        "current_failure_reason": summary.get("current_failure_reason"),
        "last_failure_json_applies_to_current_run": bool(
            summary.get("last_failure_json_applies_to_current_run")
        ),
        "last_failure_json_status": summary.get("last_failure_json_status"),
    }


def _finalize_summary(summary: dict[str, Any]) -> dict[str, Any]:
    if summary.get("current_failure_recorded"):
        status = "current_failure"
    elif summary.get("historical_last_failure_file_present"):
        status = "historical_not_current_run"
    else:
        status = "not_present"
    summary["last_failure_json_status"] = status
    summary["last_failure_json_applies_to_current_run"] = status == "current_failure"
    summary["current_run"] = _current_run_visibility(summary)
    return summary


def _flag_exists(state_dir: Path, name: str) -> bool:
    return (state_dir / name).exists()


def _write_state(state_dir: Path, status: str, summary: dict[str, Any], now: datetime) -> None:
    payload = {
        "protocol": STATE_PROTOCOL,
        "updated_at_utc": _format_time(now),
        "status": status,
        "mode": summary["mode"],
        "repo": summary["repository"],
        "inbox_issue": summary["configured_inbox_issue"],
        "cycles_completed": summary["cycles_completed"],
        "last_request_id": summary.get("request_id"),
        "operator_session_id": summary.get("operator_session_id"),
        "started_at_utc": summary.get("started_at_utc"),
        "valid_until_utc": summary.get("valid_until_utc"),
        "next_task_availability": summary.get("next_task_availability"),
        "next_task_availability_reason": summary.get("next_task_availability_reason"),
    }
    _write_json(state_dir / "state.json", payload)


def _write_heartbeat(
    state_dir: Path,
    status: str,
    cycle: int,
    summary: dict[str, Any],
    now: datetime,
) -> None:
    payload = {
        "protocol": HEARTBEAT_PROTOCOL,
        "updated_at_utc": _format_time(now),
        "pid": os.getpid(),
        "mode": summary["mode"],
        "status": status,
        "cycle": cycle,
        "repo": summary["repository"],
        "inbox_issue": summary["configured_inbox_issue"],
        "request_id": summary.get("request_id"),
        "target_issue": summary.get("target_issue"),
        "operator_session_id": summary.get("operator_session_id"),
        "process_identity": summary.get("process_identity"),
        "started_at_utc": summary.get("started_at_utc"),
        "valid_until_utc": summary.get("valid_until_utc"),
        "configured_max_cycles": summary.get("configured_max_cycles"),
        "configured_poll_interval_seconds": summary.get(
            "configured_poll_interval_seconds"
        ),
        "configured_timeout_seconds": summary.get(
            "configured_timeout_seconds"
        ),
        "next_task_availability": summary.get("next_task_availability"),
        "next_task_availability_reason": summary.get("next_task_availability_reason"),
    }
    _write_json(state_dir / "heartbeat.json", payload)


def _record_failure(state_dir: Path, summary: dict[str, Any], reason: str, now: datetime) -> None:
    summary["current_failure_recorded"] = True
    summary["current_failure_reason"] = reason
    _finalize_summary(summary)
    payload = {
        "protocol": FAILURE_PROTOCOL,
        "failed_at_utc": _format_time(now),
        "reason": reason,
        "mode": summary["mode"],
        "repo": summary["repository"],
        "inbox_issue": summary["configured_inbox_issue"],
        "request_id": summary.get("request_id"),
        "dispatcher_reached": bool(summary.get("dispatcher_invoked")),
        "dispatcher_execution_reach": summary.get("dispatcher_execution_reach"),
        "dispatcher_result_writeback_reached": bool(
            summary.get("dispatcher_result_writeback_reached")
        ),
        "dispatcher_result_writeback_verified": bool(
            summary.get("dispatcher_result_writeback_verified")
        ),
        "durable_reconciliation_performed": bool(
            summary.get("durable_reconciliation_performed")
        ),
        "durable_reconciliation_decision": summary.get("durable_reconciliation_decision"),
        "durable_reconciliation_reason": summary.get("durable_reconciliation_reason"),
        "durable_reconciliation_matched_evidence_ids": list(
            summary.get("durable_reconciliation_matched_evidence_ids", [])
        ),
        "durable_reconciliation_diagnostics": list(
            summary.get("durable_reconciliation_diagnostics", [])
        ),
        "durable_completion_reconciled": bool(summary.get("durable_completion_reconciled")),
        "runner_reached": summary.get("runner_reached"),
        "codex_reached": summary.get("codex_reached"),
        "github_write_reached": bool(summary.get("github_write_performed")),
        "current_run": summary["current_run"],
        "current_failure_recorded": True,
        "last_failure_json_applies_to_current_run": True,
        "last_failure_json_status": "current_failure",
    }
    _write_json(state_dir / "last_failure.json", payload)


def _write_log(state_dir: Path, event: str, reason: str, summary: dict[str, Any]) -> None:
    _finalize_summary(summary)
    payload = {
        "at_utc": _format_time(datetime.now(timezone.utc)),
        "event": event,
        "reason": reason,
        "mode": summary["mode"],
        "repo": summary["repository"],
        "inbox_issue": summary["configured_inbox_issue"],
        "request_id": summary.get("request_id"),
        "inbox_comment_id": summary.get("inbox_comment_id"),
        "expires": summary.get("expires"),
        "evaluated_at_utc": summary.get("evaluated_at_utc"),
        "current_request_count": summary.get("current_request_count"),
        "consumed_request_count": summary.get("consumed_request_count"),
        "expired_request_count": summary.get("expired_request_count"),
        "selected_request_state": summary.get("selected_request_state"),
        "dispatcher_invoked": bool(summary.get("dispatcher_invoked")),
        "dispatcher_execution_reach": summary.get("dispatcher_execution_reach"),
        "dispatcher_result_writeback_reached": bool(
            summary.get("dispatcher_result_writeback_reached")
        ),
        "dispatcher_result_writeback_verified": bool(
            summary.get("dispatcher_result_writeback_verified")
        ),
        "durable_reconciliation_performed": bool(
            summary.get("durable_reconciliation_performed")
        ),
        "durable_reconciliation_decision": summary.get("durable_reconciliation_decision"),
        "durable_reconciliation_reason": summary.get("durable_reconciliation_reason"),
        "durable_reconciliation_matched_evidence_ids": list(
            summary.get("durable_reconciliation_matched_evidence_ids", [])
        ),
        "durable_reconciliation_diagnostics": list(
            summary.get("durable_reconciliation_diagnostics", [])
        ),
        "durable_completion_reconciled": bool(summary.get("durable_completion_reconciled")),
        "current_delegation_outcome": summary.get("current_delegation_outcome"),
        "runner_invoked": False,
        "codex_invoked": False,
        "runner_reached": summary.get("runner_reached"),
        "codex_reached": summary.get("codex_reached"),
        "github_write_performed": False,
        "current_run": summary["current_run"],
        "current_failure_recorded": bool(summary.get("current_failure_recorded")),
        "last_failure_json_applies_to_current_run": bool(
            summary.get("last_failure_json_applies_to_current_run")
        ),
        "last_failure_json_status": summary.get("last_failure_json_status"),
    }
    with (state_dir / "operator.log").open("a", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.write("\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)
    if json.loads(path.read_text(encoding="utf-8")) != payload:
        raise OSError("json_readback_failed")


def _copy_reconciliation_result(summary: dict[str, Any], result: Any) -> None:
    summary["durable_reconciliation_decision"] = result.decision.value
    summary["durable_reconciliation_reason"] = result.reason.value
    summary["durable_reconciliation_matched_evidence_ids"] = list(
        result.matched_evidence_ids
    )
    summary["durable_reconciliation_diagnostics"] = list(result.diagnostics)
    terminal_result = getattr(result, "terminal_result", None)
    summary["terminal_result"] = terminal_result
    summary["terminal_settlement"] = (
        "settled_success"
        if terminal_result == "success"
        else (
            "settled_non_success"
            if terminal_result in {"failure", "blocked"}
            else None
        )
    )


def _block(summary: dict[str, Any], reason: str) -> None:
    if reason not in summary["blocked_reasons"]:
        summary["blocked_reasons"].append(reason)
    summary["result"] = "blocked"
    summary["phase"] = "blocked"


def _now(value: Callable[[], datetime] | datetime | None) -> datetime:
    if callable(value):
        current = value()
    elif value is None:
        current = datetime.now(timezone.utc)
    else:
        current = value
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

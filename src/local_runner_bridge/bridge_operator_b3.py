"""Bridge Operator B3 foreground bounded loop."""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
    DispatcherInvocationResult,
    build_dispatcher_command,
    default_dispatcher_invoker,
    _read_matching_results,
)
from local_runner_bridge.durable_evidence_provider import GitHubIssueCommentEvidenceProvider
from local_runner_bridge.durable_evidence_reconciliation import (
    RequestIdentity,
    ReconciliationDecision,
    resolve_durable_completion,
)

SUMMARY_PROTOCOL = "lawb.bridge_operator_b3_dry_run_loop_summary.v1"
HEARTBEAT_PROTOCOL = "lawb.bridge_operator_b3_heartbeat.v1"
LOCK_PROTOCOL = "lawb.bridge_operator_b3_lock.v1"
STATE_PROTOCOL = "lawb.bridge_operator_b3_state.v1"
OBSERVATION_PROTOCOL = "lawb.bridge_operator_b3_dry_run_observation.v1"
PROCESSED_REQUEST_PROTOCOL = "lawb.bridge_operator_b3_processed_request.v1"
FAILURE_PROTOCOL = "lawb.bridge_operator_b3_failure.v1"
B3A_MODE = "b3a-dry-run"
B3B_MODE = "b3b-maybe-status-check"
B3C_MODE = "b3c-run-reviewbundle"
B3B_ALLOWED_ACTION = "maybe-status-check"
B3C_ALLOWED_ACTION = "run-reviewbundle"

DEFAULT_MAX_CYCLES_LIMIT = 100
DEFAULT_MAX_POLL_INTERVAL_SECONDS = 3600.0
DEFAULT_READ_RETRY_COUNT = 2
SAFE_WAIT_B1_REASONS = frozenset({"missing_request", "no_current_request_after_consumption"})
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
) -> dict[str, Any]:
    """Run a visible bounded loop, dry-run by default."""
    control_root = Path(control_repo_root if control_repo_root is not None else repo_root).resolve()
    target_root = Path(repo_root).resolve()
    summary = _base_summary(repository, inbox_issue, control_root, target_root, mode)
    summary["configured_max_cycles"] = max_cycles
    summary["configured_poll_interval_seconds"] = poll_interval_seconds
    sleep = sleeper or time.sleep
    lock_acquired = False
    lock_path: Path | None = None

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

    lock_path = state_root / "operator.lock"
    try:
        _acquire_lock(lock_path, repository, inbox_issue, mode, _now(now_utc))
        lock_acquired = True
    except FileExistsError:
        _block(summary, "active_lock_present")
        _record_failure(state_root, summary, "active_lock_present", _now(now_utc))
        _write_log(state_root, "blocked", "active_lock_present", summary)
        return _finalize_summary(summary)
    except OSError as error:
        _block(summary, "lock_unavailable")
        summary["lock_error_type"] = type(error).__name__
        _record_failure(state_root, summary, "lock_unavailable", _now(now_utc))
        _write_log(state_root, "blocked", "lock_unavailable", summary)
        return _finalize_summary(summary)

    try:
        summary["lock_acquired"] = True
        summary["loop_started"] = True
        summary["result"] = "success"
        summary["phase"] = "running"
        _write_state(state_root, "running", summary, _now(now_utc))
        _write_log(state_root, "started", "dry_run_loop_started", summary)

        control_client = github_client or GitHubApiClient(DEFAULT_REPOSITORY)
        target_client = target_github_client
        if target_client is None:
            target_client = (
                control_client if repository == DEFAULT_REPOSITORY else GitHubApiClient(repository)
            )
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
                        )
                        if reason is not None:
                            _record_failure(state_root, summary, reason, _now(now_utc))
                            _write_log(state_root, "failed", reason, summary)
                            break
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
                            _write_log(state_root, "processed", "verified_dispatcher_result", summary)
                        else:
                            _write_log(state_root, "completed", "no_dispatcher_result_verified", summary)
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
        if lock_acquired and lock_path is not None:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass


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
        "lock_acquired": False,
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
        "durable_reconciliation_performed": False,
        "durable_reconciliation_read_attempts": 0,
        "durable_reconciliation_decision": None,
        "durable_reconciliation_reason": None,
        "durable_reconciliation_matched_evidence_ids": [],
        "durable_reconciliation_diagnostics": [],
        "durable_completion_reconciled": False,
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
        "dispatcher_timed_out": False,
        "dispatcher_missing": False,
        "dispatcher_stdout": "",
        "dispatcher_stderr": "",
        "dispatcher_result_writeback_reached": False,
        "dispatcher_result_writeback_verified": False,
        "target_result_verified": False,
        "target_result_comment_id": None,
        "target_result_author": None,
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


def _acquire_lock(
    lock_path: Path,
    repository: str,
    inbox_issue: int,
    mode: str,
    now: datetime,
) -> None:
    payload = {
        "protocol": LOCK_PROTOCOL,
        "pid": os.getpid(),
        "created_at_utc": _format_time(now),
        "repo": repository,
        "inbox_issue": inbox_issue,
        "mode": mode,
    }
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    fd = os.open(str(lock_path), flags)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.write("\n")


def _run_b1_with_bounded_retry(
    *,
    state_root: Path,
    repo_root: str | Path,
    repository: str,
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
                inbox_issue=DEFAULT_INBOX_ISSUE,
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
) -> str | None:
    summary["current_delegation_outcome"] = None
    action = b1_summary.get("requested_action")
    if summary.get("mode") == B3B_MODE and action != B3B_ALLOWED_ACTION:
        _block(summary, "run_reviewbundle_not_enabled_in_b3b")
        return "run_reviewbundle_not_enabled_in_b3b"
    if summary.get("mode") == B3C_MODE and action != B3C_ALLOWED_ACTION:
        _block(summary, "maybe_status_check_not_enabled_in_b3c")
        return "maybe_status_check_not_enabled_in_b3c"
    readiness = b1_summary.get("local_readiness") or {}
    if readiness.get("clean") is not True:
        _block(summary, "dirty_repository")
        return "dirty_repository"

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

    reconciliation_provider = durable_evidence_provider or GitHubIssueCommentEvidenceProvider(
        client,
        repository=repository,
    )
    request_identity = RequestIdentity(
        repository=repository,
        issue_number=int(b1_summary["target_issue"]),
        surface="issue_comment",
        request_id=str(b1_summary["target_dispatch_request_id"]),
        action=str(b1_summary["requested_action"]),
        branch=str(b1_summary["expected_branch"]),
        head=str(b1_summary["expected_head"]),
    )
    summary["durable_reconciliation_performed"] = True
    summary["durable_reconciliation_read_attempts"] += 1
    reconciliation = resolve_durable_completion(
        request_identity,
        reconciliation_provider,
        frozenset(TRUSTED_ACTORS),
    )
    _copy_reconciliation_result(summary, reconciliation)
    if reconciliation.decision == ReconciliationDecision.COMPLETED:
        _append_reconciled_processed_request(
            state_root,
            b1_summary,
            reconciliation,
            cycle,
            now,
        )
        summary["processed_request_written"] = True
        summary["durable_completion_reconciled"] = True
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

    invoker = dispatcher_invoker or default_dispatcher_invoker
    timeout = timeout_seconds if timeout_seconds is not None else DEFAULT_TIMEOUT_SECONDS
    args = build_dispatcher_command(
        repo_root=control_repo_root,
        target_repo_root=repo_root,
        target_issue=int(b1_summary["target_issue"]),
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

    if summary.get("dispatcher_missing"):
        _block(summary, "dispatcher_missing")
        return "dispatcher_missing"
    if invocation.timed_out:
        _block(summary, "dispatcher_timeout")
        return "dispatcher_timeout"
    if invocation.returncode != 0:
        _block(summary, "dispatcher_nonzero_exit")
        return "dispatcher_nonzero_exit"

    result_lookup_summary = {
        "target_issue": b1_summary["target_issue"],
        "requested_action": b1_summary["requested_action"],
        "repository": repository,
        "expected_branch": b1_summary["expected_branch"],
        "expected_head": b1_summary["expected_head"],
        "target_dispatch_request_id": b1_summary["target_dispatch_request_id"],
    }
    matches = _read_matching_results(client, result_lookup_summary)
    if matches["read_error"] is not None:
        _block(summary, "github_read_unavailable")
        summary["github_read_error_type"] = matches["read_error"]
        return "github_read_unavailable"
    if matches["matching_count"] == 0:
        _block(summary, "target_result_missing")
        return "target_result_missing"
    if matches["matching_count"] > 1:
        summary["dispatcher_result_writeback_reached"] = True
        _block(summary, "multiple_matching_results")
        return "multiple_matching_results"

    match = matches["matches"][0]
    summary["dispatcher_result_writeback_reached"] = True
    summary["target_result_comment_id"] = match["comment_id"]
    summary["target_result_author"] = match["author"]
    if match["author"] not in TRUSTED_ACTORS:
        _block(summary, "untrusted_result_author")
        return "untrusted_result_author"
    payload = match["payload"]
    if str(payload.get("result") or "") != "success":
        _block(summary, "target_result_not_success")
        return "target_result_not_success"

    summary["target_result_verified"] = True
    summary["dispatcher_result_writeback_verified"] = True
    _append_processed_request(state_root, b1_summary, match, cycle, now)
    summary["processed_request_written"] = True
    summary["current_delegation_outcome"] = "verified_dispatcher_result"
    return None


def _append_processed_request(
    state_dir: Path,
    b1_summary: dict[str, Any],
    match: dict[str, Any],
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
        "target_result_comment_id": match.get("comment_id"),
        "target_result_author": match.get("author"),
        "dispatcher_invoked": True,
        "result_verified": True,
        "lifecycle_state": CONSUMED,
    }
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.write("\n")


def _append_reconciled_processed_request(
    state_dir: Path,
    b1_summary: dict[str, Any],
    reconciliation: Any,
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
        "lifecycle_state": CONSUMED,
        "completion_source": "durable_evidence_reconciliation",
        "dispatcher_invoked": False,
        "result_verified": True,
        "reconciliation_decision": reconciliation.decision.value,
        "reconciliation_reason": reconciliation.reason.value,
        "reconciliation_matched_evidence_ids": list(reconciliation.matched_evidence_ids),
    }
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.write("\n")


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
    if completion_source is not None and completion_source != "durable_evidence_reconciliation":
        raise ValueError("invalid_processed_request")
    if completion_source == "durable_evidence_reconciliation":
        _validate_reconciled_processed_record(payload)
    elif "dispatcher_invoked" in payload and payload.get("dispatcher_invoked") is not True:
        raise ValueError("invalid_processed_request")
    if "result_verified" in payload and payload.get("result_verified") is not True:
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
    if payload.get("dispatcher_invoked") is not False:
        raise ValueError("invalid_processed_request")
    if payload.get("result_verified") is not True:
        raise ValueError("invalid_processed_request")
    if payload.get("lifecycle_state") != CONSUMED:
        raise ValueError("invalid_processed_request")
    if payload.get("reconciliation_decision") != "COMPLETED":
        raise ValueError("invalid_processed_request")
    if payload.get("reconciliation_reason") != "EXACTLY_ONE_TRUSTED_MATCH":
        raise ValueError("invalid_processed_request")
    evidence_ids = payload.get("reconciliation_matched_evidence_ids")
    if (
        not isinstance(evidence_ids, list)
        or len(evidence_ids) != 1
        or not all(isinstance(evidence_id, str) and evidence_id.strip() for evidence_id in evidence_ids)
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
    # Request identity fields describe the last CURRENT request selected during
    # this B3 run. Later waiting cycles must not erase already-processed evidence.
    if b1_summary.get("selected_request_state") == "CURRENT":
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


def _current_run_visibility(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": summary.get("request_id"),
        "issue_number": summary.get("target_issue"),
        "mode": summary.get("mode"),
        "max_cycles": summary.get("configured_max_cycles"),
        "operator_dispatcher_invocation_performed": bool(
            summary.get("operator_direct_execution_performed")
        ),
        "dispatcher_invoked": bool(summary.get("dispatcher_invoked")),
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
        "runner_reached": False,
        "codex_reached": False,
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
    temp.replace(path)


def _copy_reconciliation_result(summary: dict[str, Any], result: Any) -> None:
    summary["durable_reconciliation_decision"] = result.decision.value
    summary["durable_reconciliation_reason"] = result.reason.value
    summary["durable_reconciliation_matched_evidence_ids"] = list(
        result.matched_evidence_ids
    )
    summary["durable_reconciliation_diagnostics"] = list(result.diagnostics)


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

"""Bridge Operator B3-A foreground dry-run bounded loop."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from local_runner_bridge.bridge_operator_b1 import (
    DEFAULT_REPOSITORY,
    GitHubApiClient,
    run_bridge_operator_b1_dry_run,
)
from local_runner_bridge.bridge_operator_b2 import DEFAULT_INBOX_ISSUE

SUMMARY_PROTOCOL = "lawb.bridge_operator_b3_dry_run_loop_summary.v1"
HEARTBEAT_PROTOCOL = "lawb.bridge_operator_b3_heartbeat.v1"
LOCK_PROTOCOL = "lawb.bridge_operator_b3_lock.v1"
STATE_PROTOCOL = "lawb.bridge_operator_b3_state.v1"
OBSERVATION_PROTOCOL = "lawb.bridge_operator_b3_dry_run_observation.v1"
FAILURE_PROTOCOL = "lawb.bridge_operator_b3_failure.v1"

DEFAULT_MAX_CYCLES_LIMIT = 100
DEFAULT_MAX_POLL_INTERVAL_SECONDS = 3600.0
DEFAULT_READ_RETRY_COUNT = 2
SAFE_WAIT_B1_REASONS = frozenset({"missing_request"})


def run_bridge_operator_b3_dry_run_loop(
    *,
    repo_root: str | Path,
    repository: str = DEFAULT_REPOSITORY,
    inbox_issue: int = DEFAULT_INBOX_ISSUE,
    max_cycles: int = 1,
    poll_interval_seconds: float = 0.0,
    state_dir: str | Path | None = None,
    github_client: Any | None = None,
    local_checker: Any | None = None,
    now_utc: Callable[[], datetime] | datetime | None = None,
    sleeper: Callable[[float], None] | None = None,
    read_retry_count: int = DEFAULT_READ_RETRY_COUNT,
) -> dict[str, Any]:
    """Run a visible dry-run loop without delegating to Dispatcher."""
    summary = _base_summary(repository, inbox_issue, repo_root)
    sleep = sleeper or time.sleep
    lock_acquired = False
    lock_path: Path | None = None

    state_root = _resolve_state_dir(state_dir)
    if state_root is None:
        _block(summary, "localappdata_missing")
        return summary
    summary["state_dir"] = str(state_root)

    validation_error = _validate_loop_config(
        repository=repository,
        inbox_issue=inbox_issue,
        max_cycles=max_cycles,
        poll_interval_seconds=poll_interval_seconds,
        read_retry_count=read_retry_count,
    )
    if validation_error is not None:
        _block(summary, validation_error)
        return summary

    try:
        state_root.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        _block(summary, "state_dir_unavailable")
        summary["state_error_type"] = type(error).__name__
        return summary

    try:
        _validate_state_files(state_root)
    except ValueError as error:
        _block(summary, str(error))
        _record_failure(state_root, summary, str(error), _now(now_utc))
        _write_log(state_root, "failed", str(error), summary)
        return summary

    lock_path = state_root / "operator.lock"
    try:
        _acquire_lock(lock_path, repository, inbox_issue, _now(now_utc))
        lock_acquired = True
    except FileExistsError:
        _block(summary, "active_lock_present")
        _record_failure(state_root, summary, "active_lock_present", _now(now_utc))
        _write_log(state_root, "blocked", "active_lock_present", summary)
        return summary
    except OSError as error:
        _block(summary, "lock_unavailable")
        summary["lock_error_type"] = type(error).__name__
        _record_failure(state_root, summary, "lock_unavailable", _now(now_utc))
        _write_log(state_root, "blocked", "lock_unavailable", summary)
        return summary

    try:
        summary["lock_acquired"] = True
        summary["loop_started"] = True
        summary["result"] = "success"
        summary["phase"] = "running"
        _write_state(state_root, "running", summary, _now(now_utc))
        _write_log(state_root, "started", "dry_run_loop_started", summary)

        client = github_client or GitHubApiClient(repository)
        for cycle in range(1, max_cycles + 1):
            summary["cycles_started"] = cycle
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
                    repo_root=repo_root,
                    repository=repository,
                    client=client,
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
                    appended = _append_observation_if_new(
                        state_root,
                        b1_summary,
                        cycle,
                        _now(now_utc),
                    )
                    summary["dry_run_observation_written"] = appended
                    summary["dry_run_duplicate_observation"] = not appended
                    _write_log(state_root, "observed", "eligible_request_dry_run_observed", summary)
                elif _is_github_read_failure(b1_summary):
                    _block(summary, "github_read_unavailable")
                    _record_failure(state_root, summary, "github_read_unavailable", _now(now_utc))
                    _write_log(state_root, "failed", "github_read_unavailable", summary)
                    break
                elif _is_safe_wait_b1_result(b1_summary):
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
        _write_state(state_root, summary["phase"], summary, _now(now_utc))
        _write_heartbeat(state_root, summary["phase"], summary["cycles_completed"], summary, _now(now_utc))
        return summary
    finally:
        if lock_acquired and lock_path is not None:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass


def _base_summary(repository: str, inbox_issue: int, repo_root: str | Path) -> dict[str, Any]:
    return {
        "protocol": SUMMARY_PROTOCOL,
        "phase": "preflight",
        "result": "blocked",
        "repository": repository,
        "configured_inbox_issue": inbox_issue,
        "repo_root": str(repo_root),
        "state_dir": None,
        "mode": "b3a-dry-run",
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
        "request_id": None,
        "target_issue": None,
        "target_dispatch_request_id": None,
        "requested_action": None,
        "expected_branch": None,
        "expected_head": None,
        "last_b1_result": None,
        "last_b1_blocked_reasons": [],
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
) -> str | None:
    if repository != DEFAULT_REPOSITORY:
        return "unsupported_repository"
    if inbox_issue != DEFAULT_INBOX_ISSUE:
        return "unsupported_inbox_issue"
    if not isinstance(max_cycles, int) or max_cycles < 1 or max_cycles > DEFAULT_MAX_CYCLES_LIMIT:
        return "invalid_max_cycles"
    if poll_interval_seconds < 0 or poll_interval_seconds > DEFAULT_MAX_POLL_INTERVAL_SECONDS:
        return "invalid_poll_interval_seconds"
    if read_retry_count < 0 or read_retry_count > 5:
        return "invalid_read_retry_count"
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


def _acquire_lock(lock_path: Path, repository: str, inbox_issue: int, now: datetime) -> None:
    payload = {
        "protocol": LOCK_PROTOCOL,
        "pid": os.getpid(),
        "created_at_utc": _format_time(now),
        "repo": repository,
        "inbox_issue": inbox_issue,
        "mode": "b3a-dry-run",
    }
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    fd = os.open(str(lock_path), flags)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.write("\n")


def _run_b1_with_bounded_retry(
    *,
    repo_root: str | Path,
    repository: str,
    client: Any,
    local_checker: Any | None,
    now_utc: Callable[[], datetime] | datetime | None,
    retry_count: int,
    summary: dict[str, Any],
) -> dict[str, Any]:
    attempts = retry_count + 1
    last: dict[str, Any] | None = None
    for attempt in range(1, attempts + 1):
        summary["github_read_attempts"] += 1
        try:
            last = run_bridge_operator_b1_dry_run(
                inbox_issue=DEFAULT_INBOX_ISSUE,
                repo_root=repo_root,
                repository=repository,
                github_client=client,
                local_checker=local_checker,
                now_utc=_now(now_utc),
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
    observed = _read_observed_request_ids(path) if path.exists() else set()
    if request_id in observed:
        return False
    observation = {
        "protocol": OBSERVATION_PROTOCOL,
        "observed_at_utc": _format_time(now),
        "cycle": cycle,
        "request_id": request_id,
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


def _read_observed_request_ids(path: Path) -> set[str]:
    request_ids: set[str] = set()
    if not path.exists():
        return request_ids
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict) or "request_id" not in payload:
            raise ValueError("invalid_observation")
        request_ids.add(str(payload["request_id"]))
    return request_ids


def _copy_b1_identity(summary: dict[str, Any], b1_summary: dict[str, Any]) -> None:
    for key in (
        "request_id",
        "target_issue",
        "target_dispatch_request_id",
        "requested_action",
        "expected_branch",
        "expected_head",
    ):
        if b1_summary.get(key) is not None:
            summary[key] = b1_summary.get(key)


def _flag_exists(state_dir: Path, name: str) -> bool:
    return (state_dir / name).exists()


def _write_state(state_dir: Path, status: str, summary: dict[str, Any], now: datetime) -> None:
    payload = {
        "protocol": STATE_PROTOCOL,
        "updated_at_utc": _format_time(now),
        "status": status,
        "mode": "b3a-dry-run",
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
        "mode": "b3a-dry-run",
        "status": status,
        "cycle": cycle,
        "repo": summary["repository"],
        "inbox_issue": summary["configured_inbox_issue"],
        "request_id": summary.get("request_id"),
        "target_issue": summary.get("target_issue"),
    }
    _write_json(state_dir / "heartbeat.json", payload)


def _record_failure(state_dir: Path, summary: dict[str, Any], reason: str, now: datetime) -> None:
    payload = {
        "protocol": FAILURE_PROTOCOL,
        "failed_at_utc": _format_time(now),
        "reason": reason,
        "mode": "b3a-dry-run",
        "repo": summary["repository"],
        "inbox_issue": summary["configured_inbox_issue"],
        "request_id": summary.get("request_id"),
        "dispatcher_reached": False,
        "runner_reached": False,
        "codex_reached": False,
        "github_write_reached": False,
    }
    _write_json(state_dir / "last_failure.json", payload)


def _write_log(state_dir: Path, event: str, reason: str, summary: dict[str, Any]) -> None:
    payload = {
        "at_utc": _format_time(datetime.now(timezone.utc)),
        "event": event,
        "reason": reason,
        "mode": "b3a-dry-run",
        "repo": summary["repository"],
        "inbox_issue": summary["configured_inbox_issue"],
        "request_id": summary.get("request_id"),
        "dispatcher_invoked": False,
        "runner_invoked": False,
        "codex_invoked": False,
        "github_write_performed": False,
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

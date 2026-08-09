"""Read-only Bridge Operator diagnostics."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from local_runner_bridge.bridge_operator_lifecycle_state import (
    LifecycleEvidenceError,
    inspect_expected_process,
    inspect_lock_file,
    parse_utc,
    quarantined_lock_paths,
    validate_in_flight_payload,
)

DIAGNOSTIC_PROTOCOL = "lawb.bridge_operator_diagnostics.v1"
STATUS_READY = "READY"
STATUS_ATTENTION = "ATTENTION"
STATUS_BLOCKED = "BLOCKED"

STATE_FILENAMES = (
    "operator.lock",
    "pause.flag",
    "stop.flag",
    "state.json",
    "heartbeat.json",
    "last_failure.json",
    "in_flight.json",
    "processed_requests.jsonl",
    "dry_run_observations.jsonl",
    "operator.log",
)

CommandRunner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]
Which = Callable[[str], str | None]


def run_bridge_diagnostics(
    *,
    repo_root: str | Path,
    state_dir: str | Path | None = None,
    command_runner: CommandRunner | None = None,
    which: Which | None = None,
    now_utc: datetime | Callable[[], datetime] | None = None,
    process_probe: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Inspect local repo and Bridge Operator state without modifying either."""
    root = Path(repo_root).resolve()
    resolved_state_dir = _resolve_state_dir(state_dir)
    runner = command_runner or _run_command
    finder = which or shutil.which

    repository = _inspect_repository(root, runner)
    bridge_state = _inspect_bridge_state(
        resolved_state_dir,
        now=_now(now_utc),
        process_probe=process_probe or inspect_expected_process,
    )
    tools = _inspect_tools(root, runner, finder)
    status, reasons = _overall_status(repository, bridge_state, tools)

    return {
        "protocol": DIAGNOSTIC_PROTOCOL,
        "status": status,
        "status_reasons": reasons,
        "repository": repository,
        "bridge_operator_state": bridge_state,
        "failure_clarity": bridge_state["failure_clarity"],
        "activity": bridge_state["activity"],
        "tools": tools,
        "read_only": True,
        "dispatcher_invoked": False,
        "runner_invoked": False,
        "codex_invoked": False,
        "github_api_called": False,
        "github_write_performed": False,
        "lock_created": False,
        "lock_removed": False,
    }


def _inspect_repository(root: Path, runner: CommandRunner) -> dict[str, Any]:
    branch = _git_output(root, runner, "rev-parse", "--abbrev-ref", "HEAD")
    head = _git_output(root, runner, "rev-parse", "HEAD")
    status = _git_output(root, runner, "status", "--porcelain")
    origin_master = _git_output(root, runner, "rev-parse", "--verify", "origin/master")

    return {
        "repo_root": str(root),
        "current_branch": branch["stdout"],
        "head": head["stdout"],
        "working_tree_clean": status["stdout"] == "" if status["ok"] else None,
        "origin_master_known": origin_master["ok"],
        "origin_master_head": origin_master["stdout"],
        "head_equals_origin_master": (
            head["stdout"] == origin_master["stdout"]
            if head["ok"] and origin_master["ok"]
            else None
        ),
        "read_errors": [
            reason
            for reason, result in (
                ("branch_unavailable", branch),
                ("head_unavailable", head),
                ("status_unavailable", status),
            )
            if not result["ok"]
        ],
    }


def _git_output(
    root: Path,
    runner: CommandRunner,
    *args: str,
) -> dict[str, Any]:
    try:
        result = runner(["git", *args], root)
    except Exception as error:
        return {"ok": False, "stdout": None, "error_type": type(error).__name__}
    if result.returncode != 0:
        return {
            "ok": False,
            "stdout": None,
            "error_type": "CommandFailed",
        }
    return {"ok": True, "stdout": result.stdout.strip(), "error_type": None}


def _inspect_bridge_state(
    state_dir: Path | None,
    *,
    now: datetime,
    process_probe: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    if state_dir is None:
        present = {name: False for name in STATE_FILENAMES}
        return {
            "state_dir": None,
            "state_dir_resolved": False,
            **_presence_fields(present),
            "read_errors": ["state_dir_unavailable"],
            "failure_clarity": {
                "last_failure_json_status": "not_present",
                "last_failure_reason": None,
                "last_failure_request_id": None,
            },
            "activity": _empty_activity(),
            "lock": _empty_lock_inspection(),
            "in_flight": _empty_in_flight_inspection(),
            "quarantined_lock_evidence": {"count": 0, "filenames": []},
            "status_freshness": _empty_status_freshness(now),
            "exceptional_recovery_reason": "state_dir_unavailable",
        }

    present = {name: (state_dir / name).exists() for name in STATE_FILENAMES}
    read_errors: list[str] = []

    state_payload = _read_json_file(state_dir / "state.json")
    heartbeat_payload = _read_json_file(state_dir / "heartbeat.json")
    failure_payload = _read_json_file(state_dir / "last_failure.json")
    in_flight_payload = _read_json_file(state_dir / "in_flight.json")

    if state_payload["status"] in {"unreadable", "invalid_json"}:
        read_errors.append(f"state_json_{state_payload['status']}")
    if heartbeat_payload["status"] in {"unreadable", "invalid_json"}:
        read_errors.append(f"heartbeat_json_{heartbeat_payload['status']}")
    if failure_payload["status"] in {"unreadable", "invalid_json"}:
        read_errors.append(f"last_failure_json_{failure_payload['status']}")
    if in_flight_payload["status"] in {"unreadable", "invalid_json"}:
        read_errors.append(f"in_flight_json_{in_flight_payload['status']}")

    lock = inspect_lock_file(
        state_dir / "operator.lock",
        process_probe=process_probe,
    )
    in_flight = _inspect_in_flight(in_flight_payload)
    quarantine = quarantined_lock_paths(state_dir)
    freshness = _status_freshness(heartbeat_payload, now)
    exceptional_recovery_reason = lock.get("exceptional_recovery_reason")
    if in_flight["present"] and in_flight["validity"] != "valid":
        exceptional_recovery_reason = (
            "in_flight_invalid_manual_recovery_required"
        )
    elif in_flight["present"] and not lock["present"]:
        exceptional_recovery_reason = (
            "in_flight_without_lock_manual_recovery_required"
        )
    elif in_flight["present"] and exceptional_recovery_reason is None:
        exceptional_recovery_reason = {
            "PREPARED": "prepared_in_flight_uncertain",
            "DISPATCHED_NOT_LOCALLY_SETTLED": (
                "dispatched_in_flight_requires_reconciliation"
            ),
            "PROCESSED": "processed_in_flight_requires_local_reconciliation",
        }.get(
            in_flight["lifecycle_stage"],
            "unresolved_in_flight_manual_recovery_required",
        )

    processed_count = _count_jsonl(state_dir / "processed_requests.jsonl")
    observation_count = _count_jsonl(state_dir / "dry_run_observations.jsonl")
    latest_log = _latest_jsonl_payload(state_dir / "operator.log")
    for name, result in (
        ("processed_requests_jsonl", processed_count),
        ("dry_run_observations_jsonl", observation_count),
        ("operator_log", latest_log),
    ):
        if result["status"] in {"unreadable", "invalid_json"}:
            read_errors.append(f"{name}_{result['status']}")

    activity = {
        "latest_state_status": _payload_value(state_payload, "status"),
        "latest_heartbeat_status": _payload_value(heartbeat_payload, "status"),
        "latest_heartbeat_cycle": _payload_value(heartbeat_payload, "cycle"),
        "latest_heartbeat_request_id": _payload_value(heartbeat_payload, "request_id"),
        "latest_operator_session_id": _payload_value(
            heartbeat_payload, "operator_session_id"
        ),
        "processed_request_count": processed_count["count"],
        "observation_count": observation_count["count"],
        "latest_operator_log_event": _payload_value(latest_log, "event"),
        "latest_operator_log_reason": _payload_value(latest_log, "reason"),
        "latest_operator_log_request_id": _payload_value(latest_log, "request_id"),
    }
    failure_clarity = _failure_clarity(failure_payload, activity)

    return {
        "state_dir": str(state_dir),
        "state_dir_resolved": True,
        **_presence_fields(present),
        "read_errors": read_errors,
        "failure_clarity": failure_clarity,
        "activity": activity,
        "lock": lock,
        "in_flight": in_flight,
        "quarantined_lock_evidence": {
            "count": len(quarantine),
            "filenames": [path.name for path in quarantine],
        },
        "status_freshness": freshness,
        "exceptional_recovery_reason": exceptional_recovery_reason,
    }


def _presence_fields(present: dict[str, bool]) -> dict[str, bool]:
    return {
        "lock_file_present": present["operator.lock"],
        "pause_flag_present": present["pause.flag"],
        "stop_flag_present": present["stop.flag"],
        "state_json_present": present["state.json"],
        "heartbeat_json_present": present["heartbeat.json"],
        "last_failure_json_present": present["last_failure.json"],
        "in_flight_json_present": present["in_flight.json"],
        "processed_requests_jsonl_present": present["processed_requests.jsonl"],
        "dry_run_observations_jsonl_present": present["dry_run_observations.jsonl"],
        "operator_log_present": present["operator.log"],
    }


def _empty_activity() -> dict[str, Any]:
    return {
        "latest_state_status": None,
        "latest_heartbeat_status": None,
        "latest_heartbeat_cycle": None,
        "latest_heartbeat_request_id": None,
        "latest_operator_session_id": None,
        "processed_request_count": 0,
        "observation_count": 0,
        "latest_operator_log_event": None,
        "latest_operator_log_reason": None,
        "latest_operator_log_request_id": None,
    }


def _empty_lock_inspection() -> dict[str, Any]:
    return {
        "present": False,
        "metadata_status": "not_present",
        "operator_session_id": None,
        "repository": None,
        "inbox_issue": None,
        "mode": None,
        "process_identity": None,
        "process_status": "not_observed",
        "descendant_status": "not_observed",
        "descendant_pids": [],
        "quarantine_safe": False,
        "exceptional_recovery_reason": None,
        "evidence_sha256": None,
    }


def _empty_in_flight_inspection() -> dict[str, Any]:
    return {
        "present": False,
        "validity": "not_present",
        "lifecycle_stage": None,
        "operator_session_id": None,
        "request_id": None,
        "dispatcher_invoked": None,
        "terminal_result": None,
    }


def _inspect_in_flight(read_result: dict[str, Any]) -> dict[str, Any]:
    if read_result["status"] == "not_present":
        return _empty_in_flight_inspection()
    if read_result["status"] != "readable":
        return {
            **_empty_in_flight_inspection(),
            "present": True,
            "validity": "invalid",
        }
    try:
        payload = validate_in_flight_payload(read_result["payload"])
    except LifecycleEvidenceError:
        return {
            **_empty_in_flight_inspection(),
            "present": True,
            "validity": "invalid",
        }
    terminal = payload.get("terminal_evidence")
    return {
        "present": True,
        "validity": "valid",
        "lifecycle_stage": payload["stage"],
        "operator_session_id": payload["operator_session_id"],
        "request_id": payload["request_id"],
        "dispatcher_invoked": payload["dispatcher_invoked"],
        "terminal_result": terminal.get("result") if terminal else None,
    }


def _empty_status_freshness(now: datetime) -> dict[str, Any]:
    return {
        "assessment": "unknown",
        "observed_at_utc": now.isoformat(),
        "updated_at_utc": None,
        "valid_until_utc": None,
        "age_seconds": None,
    }


def _status_freshness(
    heartbeat: dict[str, Any], now: datetime
) -> dict[str, Any]:
    result = _empty_status_freshness(now)
    if heartbeat["status"] != "readable":
        return result
    updated_text = _payload_value(heartbeat, "updated_at_utc")
    valid_text = _payload_value(heartbeat, "valid_until_utc")
    updated = parse_utc(updated_text)
    valid_until = parse_utc(valid_text)
    result["updated_at_utc"] = updated_text
    result["valid_until_utc"] = valid_text
    if updated is not None:
        result["age_seconds"] = max(0.0, (now - updated).total_seconds())
    if valid_until is not None:
        result["assessment"] = "fresh" if now <= valid_until else "expired"
    return result


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "not_present", "payload": None}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return {"status": "unreadable", "payload": None}
    except json.JSONDecodeError:
        return {"status": "invalid_json", "payload": None}
    if not isinstance(payload, dict):
        return {"status": "invalid_json", "payload": None}
    return {"status": "readable", "payload": payload}


def _count_jsonl(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "not_present", "count": 0}
    count = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {"status": "unreadable", "count": 0}
    try:
        for line in lines:
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                return {"status": "invalid_json", "count": count}
            count += 1
    except json.JSONDecodeError:
        return {"status": "invalid_json", "count": count}
    return {"status": "readable", "count": count}


def _latest_jsonl_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "not_present", "payload": None}
    latest: dict[str, Any] | None = None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {"status": "unreadable", "payload": None}
    try:
        for line in lines:
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                return {"status": "invalid_json", "payload": latest}
            latest = payload
    except json.JSONDecodeError:
        return {"status": "invalid_json", "payload": latest}
    return {"status": "readable", "payload": latest}


def _failure_clarity(failure: dict[str, Any], activity: dict[str, Any]) -> dict[str, Any]:
    payload = failure["payload"]
    if failure["status"] == "not_present":
        status = "not_present"
    elif failure["status"] in {"unreadable", "invalid_json"}:
        status = failure["status"]
    elif payload and _has_current_failure_evidence(payload, activity):
        status = "current_failure"
    else:
        status = "historical_not_current_run"
    return {
        "last_failure_json_status": status,
        "last_failure_reason": payload.get("reason") if payload else None,
        "last_failure_request_id": payload.get("request_id") if payload else None,
    }


def _has_current_failure_evidence(
    failure_payload: dict[str, Any],
    activity: dict[str, Any],
) -> bool:
    log_event = activity.get("latest_operator_log_event")
    log_request_id = activity.get("latest_operator_log_request_id")
    failure_request_id = failure_payload.get("request_id")
    if log_event in {"failed", "blocked"}:
        if log_request_id is None or failure_request_id is None:
            return True
        return str(log_request_id) == str(failure_request_id)
    if log_event is not None:
        return False
    return activity.get("latest_state_status") in {"blocked", "failed"}


def _payload_value(read_result: dict[str, Any], key: str) -> Any:
    payload = read_result.get("payload")
    if isinstance(payload, dict):
        return payload.get(key)
    return None


def _inspect_tools(root: Path, runner: CommandRunner, finder: Which) -> dict[str, Any]:
    gh_path = finder("gh")
    codex_path = _resolve_safe_application("codex", finder)
    return {
        "python_executable": sys.executable,
        "gh_available": gh_path is not None,
        "gh_path": gh_path,
        "gh_version": _safe_version(root, runner, gh_path),
        "codex_available": codex_path is not None,
        "codex_path": codex_path,
        "codex_version": _safe_version(root, runner, codex_path),
    }


def _resolve_safe_application(
    name: str,
    finder: Which,
    *,
    platform: str | None = None,
) -> str | None:
    current_platform = platform or sys.platform
    if current_platform == "win32":
        candidates: list[str] = []
        for query in (
            name,
            f"{name}.exe",
            f"{name}.cmd",
            f"{name}.bat",
            f"{name}.com",
        ):
            candidate = finder(query)
            if candidate and candidate not in candidates:
                candidates.append(candidate)

        for suffix in (".exe", ".cmd", ".bat", ".com"):
            for candidate in candidates:
                if Path(candidate).suffix.lower() == suffix:
                    return candidate
        return None

    candidate = finder(name)
    if candidate is None:
        return None
    if Path(candidate).suffix.lower() in {".ps1", ".cmd", ".bat", ".sh"}:
        return None
    return candidate


def _safe_version(root: Path, runner: CommandRunner, command_path: str | None) -> str | None:
    if command_path is None:
        return None
    command = _version_command(command_path)
    try:
        result = runner(command, root)
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.splitlines()[0].strip() if result.stdout.splitlines() else ""


def _version_command(command_path: str) -> list[str]:
    suffix = Path(command_path).suffix.lower()
    if suffix in {".cmd", ".bat"}:
        comspec = os.environ.get("COMSPEC") or "cmd.exe"
        return [comspec, "/d", "/c", command_path, "--version"]
    return [command_path, "--version"]


def _overall_status(
    repository: dict[str, Any],
    bridge_state: dict[str, Any],
    tools: dict[str, Any],
) -> tuple[str, list[str]]:
    blocked: list[str] = []
    attention: list[str] = []

    if repository["working_tree_clean"] is False:
        blocked.append("working_tree_dirty")
    if repository["read_errors"]:
        blocked.extend(repository["read_errors"])
    lock = bridge_state["lock"]
    if bridge_state["lock_file_present"]:
        if lock["metadata_status"] != "complete":
            blocked.append(
                lock["exceptional_recovery_reason"]
                or "lock_metadata_invalid_manual_recovery_required"
            )
        elif lock["process_status"] == "live":
            blocked.append("active_lock_present")
        elif lock["quarantine_safe"]:
            attention.append("dead_lock_quarantine_candidate")
        else:
            blocked.append(
                lock["exceptional_recovery_reason"]
                or "dead_lock_recovery_uncertain"
            )
    in_flight = bridge_state["in_flight"]
    if in_flight["present"]:
        blocked.append(
            "unresolved_in_flight_present"
            if in_flight["validity"] == "valid"
            else "in_flight_invalid_manual_recovery_required"
        )
    if bridge_state["stop_flag_present"]:
        blocked.append("stop_flag_present")
    for error in bridge_state["read_errors"]:
        if error.startswith(("state_json_", "heartbeat_json_", "last_failure_json_")):
            blocked.append(error)
        else:
            attention.append(error)

    failure_status = bridge_state["failure_clarity"]["last_failure_json_status"]
    if failure_status == "current_failure":
        attention.append("current_last_failure_present")
    if failure_status == "historical_not_current_run":
        attention.append("historical_last_failure_present")
    if bridge_state["pause_flag_present"]:
        attention.append("pause_flag_present")
    if bridge_state["status_freshness"]["assessment"] == "expired":
        attention.append("status_stale")
    if repository["origin_master_known"] is False:
        attention.append("origin_master_unknown")
    if repository["head_equals_origin_master"] is False:
        attention.append("head_differs_from_origin_master")
    if not tools["gh_available"]:
        attention.append("gh_unavailable")
    if not tools["codex_available"]:
        attention.append("codex_unavailable")
    if not any(
        bridge_state[name]
        for name in (
            "state_json_present",
            "heartbeat_json_present",
            "last_failure_json_present",
            "in_flight_json_present",
            "processed_requests_jsonl_present",
            "dry_run_observations_jsonl_present",
            "operator_log_present",
        )
    ):
        attention.append("no_state_files_present")

    if blocked:
        return STATUS_BLOCKED, blocked
    if attention:
        return STATUS_ATTENTION, attention
    return STATUS_READY, ["ready"]


def _resolve_state_dir(state_dir: str | Path | None) -> Path | None:
    if state_dir is not None:
        return Path(state_dir)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    return Path(local_app_data) / "LocalAIWorkbench" / "BridgeOperator"


def _now(value: datetime | Callable[[], datetime] | None) -> datetime:
    current = value() if callable(value) else value
    if current is None:
        current = datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _run_command(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        timeout=10,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--state-dir")
    parser.add_argument("--json", action="store_true", help="Print JSON output, the default.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    summary = run_bridge_diagnostics(
        repo_root=args.repo_root,
        state_dir=args.state_dir,
    )
    indent = 2 if args.pretty else None
    print(json.dumps(summary, indent=indent, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

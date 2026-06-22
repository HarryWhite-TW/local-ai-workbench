"""Read-only Bridge Operator diagnostics."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

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
) -> dict[str, Any]:
    """Inspect local repo and Bridge Operator state without modifying either."""
    root = Path(repo_root).resolve()
    resolved_state_dir = _resolve_state_dir(state_dir)
    runner = command_runner or _run_command
    finder = which or shutil.which

    repository = _inspect_repository(root, runner)
    bridge_state = _inspect_bridge_state(resolved_state_dir)
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


def _inspect_bridge_state(state_dir: Path | None) -> dict[str, Any]:
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
        }

    present = {name: (state_dir / name).exists() for name in STATE_FILENAMES}
    read_errors: list[str] = []

    state_payload = _read_json_file(state_dir / "state.json")
    heartbeat_payload = _read_json_file(state_dir / "heartbeat.json")
    failure_payload = _read_json_file(state_dir / "last_failure.json")

    if state_payload["status"] in {"unreadable", "invalid_json"}:
        read_errors.append(f"state_json_{state_payload['status']}")
    if heartbeat_payload["status"] in {"unreadable", "invalid_json"}:
        read_errors.append(f"heartbeat_json_{heartbeat_payload['status']}")
    if failure_payload["status"] in {"unreadable", "invalid_json"}:
        read_errors.append(f"last_failure_json_{failure_payload['status']}")

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
    }


def _presence_fields(present: dict[str, bool]) -> dict[str, bool]:
    return {
        "lock_file_present": present["operator.lock"],
        "pause_flag_present": present["pause.flag"],
        "stop_flag_present": present["stop.flag"],
        "state_json_present": present["state.json"],
        "heartbeat_json_present": present["heartbeat.json"],
        "last_failure_json_present": present["last_failure.json"],
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
        "processed_request_count": 0,
        "observation_count": 0,
        "latest_operator_log_event": None,
        "latest_operator_log_reason": None,
        "latest_operator_log_request_id": None,
    }


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
    codex_path = finder("codex")
    return {
        "python_executable": sys.executable,
        "gh_available": gh_path is not None,
        "gh_path": gh_path,
        "gh_version": _safe_version(root, runner, gh_path),
        "codex_available": codex_path is not None,
        "codex_path": codex_path,
        "codex_version": _safe_version(root, runner, codex_path),
    }


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
    if bridge_state["lock_file_present"]:
        blocked.append("active_lock_present")
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

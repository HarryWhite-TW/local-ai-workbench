"""Bounded local evidence primitives for the Bridge Operator B3 lifecycle.

This module owns serialization, validation, and read-only process observation.
It does not poll GitHub, choose lifecycle transitions, or invoke Dispatcher.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

LOCK_PROTOCOL = "lawb.bridge_operator_b3_lock.v2"
LOCK_SCHEMA_VERSION = 2
IN_FLIGHT_PROTOCOL = "lawb.bridge_operator_b3_in_flight.v1"
IN_FLIGHT_SCHEMA_VERSION = 1
REVIEW_CANDIDATE_PROTOCOL = "lawb.bridge_operator_review_candidate.v1"
REVIEW_CANDIDATE_SCHEMA_VERSION = 2
LEGACY_REVIEW_CANDIDATE_SCHEMA_VERSION = 1
PREPARED = "PREPARED"
DISPATCHED_NOT_LOCALLY_SETTLED = "DISPATCHED_NOT_LOCALLY_SETTLED"
REJECTED_BEFORE_RUNNER = "REJECTED_BEFORE_RUNNER"
PROCESSED = "PROCESSED"
IN_FLIGHT_STAGES = frozenset(
    {PREPARED, DISPATCHED_NOT_LOCALLY_SETTLED, REJECTED_BEFORE_RUNNER, PROCESSED}
)
PRE_RUNNER_REJECTION_EVIDENCE_PREFIX = "local-dispatcher:"
PRE_RUNNER_REJECTION_AUTHOR = "local-dispatcher-v1"
PRE_RUNNER_REJECTION_DECISION = "DISPATCHER_REJECTED_BEFORE_RUNNER"
PRE_RUNNER_REJECTION_REASON = "STRUCTURED_PRE_RUNNER_REJECTION"
TERMINAL_RESULTS = frozenset({"success", "failure", "blocked"})
SETTLEMENTS = frozenset({"settled_success", "settled_non_success"})
QUARANTINE_PREFIX = "operator.lock.quarantine."
QUARANTINE_SUFFIX = ".json"

_SESSION_ID = re.compile(r"^[0-9a-f]{32}$")
_START_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{7,255}$")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{2,127}$")
_HEAD = re.compile(r"^[0-9a-f]{40}$")
_COMMENT_ID = re.compile(r"^[1-9][0-9]{0,18}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class LifecycleEvidenceError(ValueError):
    """One exact lifecycle evidence contract failure."""


def format_utc(value: datetime) -> str:
    current = value
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return (
        current.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def validate_session_id(value: Any) -> str:
    if not isinstance(value, str) or _SESSION_ID.fullmatch(value) is None:
        raise LifecycleEvidenceError("operator_session_id_invalid")
    return value


def capture_current_process_identity() -> dict[str, Any]:
    status, identity = _query_process_identity(os.getpid())
    if status != "live" or identity is None:
        raise LifecycleEvidenceError("process_identity_unavailable")
    return identity


def validate_process_identity(value: Any) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or set(value) != {"platform", "pid", "start_token", "started_at_utc"}
        or value.get("platform") not in {"windows", "linux"}
        or type(value.get("pid")) is not int
        or value["pid"] <= 0
        or not isinstance(value.get("start_token"), str)
        or _START_TOKEN.fullmatch(value["start_token"]) is None
        or parse_utc(value.get("started_at_utc")) is None
    ):
        raise LifecycleEvidenceError("process_identity_invalid")
    return dict(value)


def inspect_expected_process(expected: dict[str, Any]) -> dict[str, Any]:
    """Observe one exact PID/start identity and its current descendant tree."""
    expected = validate_process_identity(expected)
    current_platform = _platform_name()
    if current_platform != expected["platform"]:
        return _process_observation(
            "uncertain",
            "uncertain",
            observed=None,
            descendants=(),
            reason="process_platform_mismatch",
        )

    status, observed = _query_process_identity(expected["pid"])
    if status == "live" and observed is not None:
        process_status = (
            "live"
            if observed["start_token"] == expected["start_token"]
            else "pid_reused"
        )
    else:
        process_status = status

    try:
        descendants = _descendant_pids(expected["pid"])
        descendant_status = "present" if descendants else "none"
        descendant_reason = "none"
    except OSError:
        descendants = ()
        descendant_status = "uncertain"
        descendant_reason = "descendant_snapshot_unavailable"

    reason = (
        descendant_reason
        if process_status in {"dead", "pid_reused"}
        and descendant_status == "uncertain"
        else "none"
    )
    return _process_observation(
        process_status,
        descendant_status,
        observed=observed,
        descendants=descendants,
        reason=reason,
    )


def _process_observation(
    process_status: str,
    descendant_status: str,
    *,
    observed: dict[str, Any] | None,
    descendants: tuple[int, ...],
    reason: str,
) -> dict[str, Any]:
    return {
        "process_status": process_status,
        "descendant_status": descendant_status,
        "observed_process_identity": observed,
        "descendant_pids": list(descendants),
        "reason": reason,
    }


def _platform_name() -> str | None:
    if sys.platform == "win32":
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    return None


def _query_process_identity(pid: int) -> tuple[str, dict[str, Any] | None]:
    if sys.platform == "win32":
        return _query_windows_process_identity(pid)
    if sys.platform.startswith("linux"):
        return _query_linux_process_identity(pid)
    return "uncertain", None


def _query_windows_process_identity(
    pid: int,
) -> tuple[str, dict[str, Any] | None]:
    from ctypes import wintypes

    class FileTime(ctypes.Structure):
        _fields_ = [
            ("low", wintypes.DWORD),
            ("high", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_process.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    wait = kernel32.WaitForSingleObject
    wait.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    wait.restype = wintypes.DWORD
    get_times = kernel32.GetProcessTimes
    get_times.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(FileTime),
        ctypes.POINTER(FileTime),
        ctypes.POINTER(FileTime),
        ctypes.POINTER(FileTime),
    ]
    get_times.restype = wintypes.BOOL

    process_query_limited_information = 0x1000
    synchronize = 0x00100000
    handle = open_process(
        process_query_limited_information | synchronize,
        False,
        pid,
    )
    if not handle:
        error = ctypes.get_last_error()
        return ("dead", None) if error == 87 else ("uncertain", None)
    try:
        wait_result = wait(handle, 0)
        if wait_result == 0:
            return "dead", None
        if wait_result != 0x102:
            return "uncertain", None
        creation = FileTime()
        exit_time = FileTime()
        kernel_time = FileTime()
        user_time = FileTime()
        if not get_times(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        ):
            return "uncertain", None
        filetime = (int(creation.high) << 32) | int(creation.low)
        started = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(
            microseconds=filetime // 10
        )
        return "live", {
            "platform": "windows",
            "pid": pid,
            "start_token": f"windows-filetime:{filetime}",
            "started_at_utc": format_utc(started),
        }
    finally:
        close_handle(handle)


def _linux_stat(pid: int) -> tuple[int, int]:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    except FileNotFoundError as error:
        raise ProcessLookupError(pid) from error
    end = raw.rfind(")")
    if end < 0:
        raise OSError("linux_process_stat_invalid")
    fields = raw[end + 2 :].split()
    if len(fields) <= 19:
        raise OSError("linux_process_stat_invalid")
    return int(fields[1]), int(fields[19])


def _query_linux_process_identity(
    pid: int,
) -> tuple[str, dict[str, Any] | None]:
    try:
        _, start_ticks = _linux_stat(pid)
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(
            encoding="ascii"
        ).strip()
        btime_line = next(
            line
            for line in Path("/proc/stat").read_text(encoding="ascii").splitlines()
            if line.startswith("btime ")
        )
        boot_seconds = int(btime_line.split()[1])
        ticks_per_second = int(os.sysconf("SC_CLK_TCK"))
    except ProcessLookupError:
        return "dead", None
    except (OSError, StopIteration, ValueError):
        return "uncertain", None
    started = datetime.fromtimestamp(
        boot_seconds + (start_ticks / ticks_per_second),
        tz=timezone.utc,
    )
    return "live", {
        "platform": "linux",
        "pid": pid,
        "start_token": f"linux:{boot_id}:{start_ticks}",
        "started_at_utc": format_utc(started),
    }


def _descendant_pids(root_pid: int) -> tuple[int, ...]:
    if sys.platform == "win32":
        parent_by_pid = _windows_parent_snapshot()
    elif sys.platform.startswith("linux"):
        parent_by_pid = {}
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                parent, _ = _linux_stat(int(entry.name))
            except (OSError, ProcessLookupError, ValueError):
                continue
            parent_by_pid[int(entry.name)] = parent
    else:
        raise OSError("descendant_snapshot_unsupported")

    children_by_parent: dict[int, list[int]] = {}
    for child, parent in parent_by_pid.items():
        children_by_parent.setdefault(parent, []).append(child)
    result: set[int] = set()
    pending = list(children_by_parent.get(root_pid, ()))
    while pending:
        child = pending.pop()
        if child == root_pid or child in result:
            continue
        result.add(child)
        pending.extend(children_by_parent.get(child, ()))
    return tuple(sorted(result))


def _windows_parent_snapshot() -> dict[int, int]:
    from ctypes import wintypes

    class ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("size", wintypes.DWORD),
            ("usage_count", wintypes.DWORD),
            ("process_id", wintypes.DWORD),
            ("default_heap_id", ctypes.c_size_t),
            ("module_id", wintypes.DWORD),
            ("thread_count", wintypes.DWORD),
            ("parent_process_id", wintypes.DWORD),
            ("base_priority", ctypes.c_long),
            ("flags", wintypes.DWORD),
            ("executable_name", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_snapshot = kernel32.CreateToolhelp32Snapshot
    create_snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    create_snapshot.restype = wintypes.HANDLE
    first = kernel32.Process32FirstW
    first.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W)]
    first.restype = wintypes.BOOL
    next_entry = kernel32.Process32NextW
    next_entry.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W)]
    next_entry.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    snapshot = create_snapshot(0x00000002, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise OSError("process_snapshot_failed")
    result: dict[int, int] = {}
    try:
        entry = ProcessEntry32W()
        entry.size = ctypes.sizeof(ProcessEntry32W)
        if not first(snapshot, ctypes.byref(entry)):
            raise OSError("process_snapshot_read_failed")
        while True:
            result[int(entry.process_id)] = int(entry.parent_process_id)
            entry.size = ctypes.sizeof(ProcessEntry32W)
            if not next_entry(snapshot, ctypes.byref(entry)):
                break
    finally:
        close_handle(snapshot)
    return result


def create_lock_payload(
    *,
    operator_session_id: str,
    process_identity: dict[str, Any],
    created_at: datetime,
    repository: str,
    inbox_issue: int,
    mode: str,
) -> dict[str, Any]:
    payload = {
        "protocol": LOCK_PROTOCOL,
        "schema_version": LOCK_SCHEMA_VERSION,
        "operator_session_id": validate_session_id(operator_session_id),
        "process_identity": validate_process_identity(process_identity),
        "created_at_utc": format_utc(created_at),
        "repo": repository,
        "inbox_issue": inbox_issue,
        "mode": mode,
        "descendant_recovery_policy": "require_no_live_descendants",
    }
    validate_lock_payload(payload)
    return payload


def validate_lock_payload(value: Any) -> dict[str, Any]:
    expected_keys = {
        "protocol",
        "schema_version",
        "operator_session_id",
        "process_identity",
        "created_at_utc",
        "repo",
        "inbox_issue",
        "mode",
        "descendant_recovery_policy",
    }
    if (
        not isinstance(value, dict)
        or set(value) != expected_keys
        or value.get("protocol") != LOCK_PROTOCOL
        or value.get("schema_version") != LOCK_SCHEMA_VERSION
        or parse_utc(value.get("created_at_utc")) is None
        or not isinstance(value.get("repo"), str)
        or not value["repo"]
        or type(value.get("inbox_issue")) is not int
        or value["inbox_issue"] <= 0
        or not isinstance(value.get("mode"), str)
        or not value["mode"]
        or value.get("descendant_recovery_policy")
        != "require_no_live_descendants"
    ):
        raise LifecycleEvidenceError("lock_metadata_invalid")
    validate_session_id(value.get("operator_session_id"))
    validate_process_identity(value.get("process_identity"))
    return dict(value)


def inspect_lock_file(
    path: Path,
    *,
    process_probe: Callable[[dict[str, Any]], dict[str, Any]] = (
        inspect_expected_process
    ),
) -> dict[str, Any]:
    base = {
        "present": path.exists(),
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
    if not path.exists():
        return base
    try:
        raw = path.read_bytes()
        value = _load_json_bytes(raw)
    except (OSError, LifecycleEvidenceError):
        return {
            **base,
            "present": True,
            "metadata_status": "invalid",
            "exceptional_recovery_reason": (
                "lock_metadata_invalid_manual_recovery_required"
            ),
        }
    try:
        payload = validate_lock_payload(value)
    except LifecycleEvidenceError:
        return {
            **base,
            "present": True,
            "metadata_status": "legacy",
            "evidence_sha256": hashlib.sha256(raw).hexdigest(),
            "exceptional_recovery_reason": (
                "legacy_lock_manual_recovery_required"
            ),
        }
    try:
        observation = process_probe(payload["process_identity"])
    except Exception:
        observation = _process_observation(
            "uncertain",
            "uncertain",
            observed=None,
            descendants=(),
            reason="process_probe_failed",
        )
    process_status = observation.get("process_status")
    descendant_status = observation.get("descendant_status")
    allowed_statuses = {"live", "dead", "pid_reused", "uncertain"}
    if process_status not in allowed_statuses:
        process_status = "uncertain"
    if descendant_status not in {"none", "present", "uncertain"}:
        descendant_status = "uncertain"
    quarantine_safe = (
        process_status in {"dead", "pid_reused"}
        and descendant_status == "none"
    )
    if process_status == "live":
        recovery_reason = "live_operator_or_hung"
    elif descendant_status == "present":
        recovery_reason = "live_descendant_present"
    elif not quarantine_safe:
        recovery_reason = "process_liveness_uncertain"
    else:
        recovery_reason = None
    return {
        **base,
        "present": True,
        "metadata_status": "complete",
        "operator_session_id": payload["operator_session_id"],
        "repository": payload["repo"],
        "inbox_issue": payload["inbox_issue"],
        "mode": payload["mode"],
        "process_identity": payload["process_identity"],
        "process_status": process_status,
        "descendant_status": descendant_status,
        "descendant_pids": list(observation.get("descendant_pids") or []),
        "quarantine_safe": quarantine_safe,
        "exceptional_recovery_reason": recovery_reason,
        "evidence_sha256": hashlib.sha256(raw).hexdigest(),
    }


def write_exclusive_json(path: Path, payload: dict[str, Any]) -> None:
    raw = _json_bytes(payload)
    descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if descriptor != -1:
            os.close(descriptor)
    if path.read_bytes() != raw:
        raise LifecycleEvidenceError("exclusive_json_readback_failed")


def write_durable_json(
    path: Path,
    payload: dict[str, Any],
    *,
    operator_session_id: str,
) -> None:
    session_id = validate_session_id(operator_session_id)
    raw = _json_bytes(payload)
    temporary = path.with_name(f".{path.name}.{session_id}.tmp")
    created = False
    try:
        descriptor = os.open(
            str(temporary),
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        )
        created = True
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        created = False
        observed = path.read_bytes()
        if observed != raw or _load_json_bytes(observed) != payload:
            raise LifecycleEvidenceError("durable_json_readback_failed")
    finally:
        if created:
            temporary.unlink(missing_ok=True)


def append_jsonl_durable(path: Path, payload: dict[str, Any]) -> None:
    raw = _json_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        offset = handle.tell()
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    with path.open("rb") as handle:
        handle.seek(offset)
        if handle.read() != raw:
            raise LifecycleEvidenceError("durable_jsonl_readback_failed")


def new_in_flight_payload(
    *,
    request_id: str,
    target_repository: str,
    target_issue: int,
    dispatch_request_id: str,
    action: str,
    branch: str,
    expected_head: str,
    operator_session_id: str,
    process_identity: dict[str, Any],
    prepared_at: datetime,
) -> dict[str, Any]:
    timestamp = format_utc(prepared_at)
    payload = {
        "protocol": IN_FLIGHT_PROTOCOL,
        "schema_version": IN_FLIGHT_SCHEMA_VERSION,
        "request_id": request_id,
        "target_repository": target_repository,
        "target_issue": target_issue,
        "dispatch_request_id": dispatch_request_id,
        "action": action,
        "branch": branch,
        "expected_head": expected_head,
        "operator_session_id": operator_session_id,
        "process_identity": process_identity,
        "prepared_at_utc": timestamp,
        "updated_at_utc": timestamp,
        "stage": PREPARED,
        "dispatcher_invoked": False,
        "terminal_evidence": None,
    }
    validate_in_flight_payload(payload)
    return payload


def updated_in_flight_payload(
    payload: dict[str, Any],
    *,
    stage: str,
    dispatcher_invoked: bool,
    terminal_evidence: dict[str, Any] | None,
    updated_at: datetime,
) -> dict[str, Any]:
    updated = dict(payload)
    updated.update(
        {
            "stage": stage,
            "dispatcher_invoked": dispatcher_invoked,
            "terminal_evidence": terminal_evidence,
            "updated_at_utc": format_utc(updated_at),
        }
    )
    validate_in_flight_payload(updated)
    return updated


def validate_in_flight_payload(value: Any) -> dict[str, Any]:
    expected_keys = {
        "protocol",
        "schema_version",
        "request_id",
        "target_repository",
        "target_issue",
        "dispatch_request_id",
        "action",
        "branch",
        "expected_head",
        "operator_session_id",
        "process_identity",
        "prepared_at_utc",
        "updated_at_utc",
        "stage",
        "dispatcher_invoked",
        "terminal_evidence",
    }
    invalid = (
        not isinstance(value, dict)
        or set(value) != expected_keys
        or value.get("protocol") != IN_FLIGHT_PROTOCOL
        or value.get("schema_version") != IN_FLIGHT_SCHEMA_VERSION
        or not isinstance(value.get("request_id"), str)
        or _REQUEST_ID.fullmatch(value.get("request_id", "")) is None
        or not isinstance(value.get("target_repository"), str)
        or not value["target_repository"]
        or type(value.get("target_issue")) is not int
        or value["target_issue"] <= 0
        or not isinstance(value.get("dispatch_request_id"), str)
        or _REQUEST_ID.fullmatch(value.get("dispatch_request_id", "")) is None
        or not isinstance(value.get("action"), str)
        or not value["action"]
        or not isinstance(value.get("branch"), str)
        or not value["branch"]
        or not isinstance(value.get("expected_head"), str)
        or _HEAD.fullmatch(value.get("expected_head", "")) is None
        or parse_utc(value.get("prepared_at_utc")) is None
        or parse_utc(value.get("updated_at_utc")) is None
        or value.get("stage") not in IN_FLIGHT_STAGES
        or type(value.get("dispatcher_invoked")) is not bool
    )
    if invalid:
        raise LifecycleEvidenceError("in_flight_invalid")
    validate_session_id(value.get("operator_session_id"))
    validate_process_identity(value.get("process_identity"))
    prepared = parse_utc(value["prepared_at_utc"])
    updated = parse_utc(value["updated_at_utc"])
    if prepared is None or updated is None or updated < prepared:
        raise LifecycleEvidenceError("in_flight_invalid")
    stage = value["stage"]
    terminal = value["terminal_evidence"]
    if stage == PREPARED and (value["dispatcher_invoked"] or terminal is not None):
        raise LifecycleEvidenceError("in_flight_invalid")
    if stage == DISPATCHED_NOT_LOCALLY_SETTLED and (
        not value["dispatcher_invoked"] or terminal is not None
    ):
        raise LifecycleEvidenceError("in_flight_invalid")
    if stage in {REJECTED_BEFORE_RUNNER, PROCESSED} and (
        not value["dispatcher_invoked"] or terminal is None
    ):
        raise LifecycleEvidenceError("in_flight_invalid")
    if terminal is not None:
        validate_terminal_evidence(terminal)
    if stage == REJECTED_BEFORE_RUNNER and (
        terminal["evidence_id"]
        != f"{PRE_RUNNER_REJECTION_EVIDENCE_PREFIX}{value['request_id']}"
        or terminal["author"] != PRE_RUNNER_REJECTION_AUTHOR
        or terminal["result"] != "blocked"
        or terminal["settlement"] != "settled_non_success"
        or terminal["reconciliation_decision"] != PRE_RUNNER_REJECTION_DECISION
        or terminal["reconciliation_reason"] != PRE_RUNNER_REJECTION_REASON
    ):
        raise LifecycleEvidenceError("in_flight_invalid")
    return dict(value)


def validate_terminal_evidence(value: Any) -> dict[str, Any]:
    expected_keys = {
        "evidence_id",
        "author",
        "result",
        "settlement",
        "reconciliation_decision",
        "reconciliation_reason",
        "observed_at_utc",
    }
    if (
        not isinstance(value, dict)
        or set(value) != expected_keys
        or not isinstance(value.get("evidence_id"), str)
        or not value["evidence_id"].strip()
        or not isinstance(value.get("author"), str)
        or not value["author"].strip()
        or value.get("result") not in TERMINAL_RESULTS
        or value.get("settlement") not in SETTLEMENTS
        or not isinstance(value.get("reconciliation_decision"), str)
        or not value["reconciliation_decision"]
        or not isinstance(value.get("reconciliation_reason"), str)
        or not value["reconciliation_reason"]
        or parse_utc(value.get("observed_at_utc")) is None
        or (
            value["result"] == "success"
            and value["settlement"] != "settled_success"
        )
        or (
            value["result"] in {"failure", "blocked"}
            and value["settlement"] != "settled_non_success"
        )
    ):
        raise LifecycleEvidenceError("terminal_evidence_invalid")
    return dict(value)


def new_review_candidate_payload(
    *,
    target_repository: str,
    target_issue: int,
    dispatch_request_id: str,
    action: str,
    branch: str,
    expected_head: str,
    terminal_result_comment_id: str,
    review_bundle_comment_id: str,
    candidate_manifest_fingerprint: str,
    target_repo_root: str,
    recorded_at: datetime,
) -> dict[str, Any]:
    payload = {
        "protocol": REVIEW_CANDIDATE_PROTOCOL,
        "schema_version": REVIEW_CANDIDATE_SCHEMA_VERSION,
        "target_repository": target_repository,
        "target_issue": target_issue,
        "dispatch_request_id": dispatch_request_id,
        "action": action,
        "branch": branch,
        "expected_head": expected_head,
        "terminal_result_comment_id": terminal_result_comment_id,
        "review_bundle_comment_id": review_bundle_comment_id,
        "candidate_manifest_fingerprint": candidate_manifest_fingerprint,
        "target_repo_root": target_repo_root,
        "recorded_at_utc": format_utc(recorded_at),
    }
    validate_review_candidate_payload(payload)
    return payload


def validate_review_candidate_payload(value: Any) -> dict[str, Any]:
    common_keys = {
        "protocol",
        "schema_version",
        "target_repository",
        "target_issue",
        "dispatch_request_id",
        "action",
        "branch",
        "expected_head",
        "terminal_result_comment_id",
        "review_bundle_comment_id",
        "candidate_manifest_fingerprint",
        "recorded_at_utc",
    }
    if not isinstance(value, dict):
        raise LifecycleEvidenceError("review_candidate_invalid")
    schema_version = value.get("schema_version")
    expected_keys = (
        common_keys | {"target_repo_root"}
        if schema_version == REVIEW_CANDIDATE_SCHEMA_VERSION
        else common_keys
    )
    if (
        set(value) != expected_keys
        or value.get("protocol") != REVIEW_CANDIDATE_PROTOCOL
        or schema_version
        not in {
            LEGACY_REVIEW_CANDIDATE_SCHEMA_VERSION,
            REVIEW_CANDIDATE_SCHEMA_VERSION,
        }
        or not isinstance(value.get("target_repository"), str)
        or not value["target_repository"]
        or type(value.get("target_issue")) is not int
        or value["target_issue"] <= 0
        or not isinstance(value.get("dispatch_request_id"), str)
        or _REQUEST_ID.fullmatch(value["dispatch_request_id"]) is None
        or value.get("action") != "run-reviewbundle"
        or not isinstance(value.get("branch"), str)
        or not value["branch"]
        or not isinstance(value.get("expected_head"), str)
        or _HEAD.fullmatch(value["expected_head"]) is None
        or not isinstance(value.get("terminal_result_comment_id"), str)
        or _COMMENT_ID.fullmatch(value["terminal_result_comment_id"]) is None
        or not isinstance(value.get("review_bundle_comment_id"), str)
        or _COMMENT_ID.fullmatch(value["review_bundle_comment_id"]) is None
        or not isinstance(value.get("candidate_manifest_fingerprint"), str)
        or _SHA256.fullmatch(value["candidate_manifest_fingerprint"]) is None
        or parse_utc(value.get("recorded_at_utc")) is None
    ):
        raise LifecycleEvidenceError("review_candidate_invalid")
    if schema_version == REVIEW_CANDIDATE_SCHEMA_VERSION:
        target_repo_root = value.get("target_repo_root")
        if (
            not isinstance(target_repo_root, str)
            or not target_repo_root
            or "\x00" in target_repo_root
            or not Path(target_repo_root).is_absolute()
        ):
            raise LifecycleEvidenceError("review_candidate_invalid")
    return dict(value)


def load_review_candidate(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return validate_review_candidate_payload(_load_json_bytes(path.read_bytes()))
    except (OSError, LifecycleEvidenceError) as error:
        raise LifecycleEvidenceError("review_candidate_invalid") from error


def write_or_replace_review_candidate(
    path: Path,
    payload: dict[str, Any],
    *,
    operator_session_id: str,
) -> str:
    """Persist one verified candidate pointer without treating it as authority."""
    expected = validate_review_candidate_payload(payload)
    existing = load_review_candidate(path)
    if existing is not None:
        if existing["dispatch_request_id"] == expected["dispatch_request_id"]:
            comparable_keys = set(expected) - {"recorded_at_utc"}
            if any(existing.get(key) != expected[key] for key in comparable_keys):
                raise LifecycleEvidenceError("review_candidate_conflict")
            return "already_present"
        # A separately reconciled later successful review-bundle may replace it.
        write_durable_json(path, expected, operator_session_id=operator_session_id)
        return "replaced"
    write_durable_json(path, expected, operator_session_id=operator_session_id)
    return "written"


def load_in_flight(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = path.read_bytes()
        return validate_in_flight_payload(_load_json_bytes(raw))
    except (OSError, LifecycleEvidenceError) as error:
        raise LifecycleEvidenceError("in_flight_invalid") from error


def remove_exact_json(path: Path, expected: dict[str, Any]) -> None:
    try:
        observed = _load_json_bytes(path.read_bytes())
    except (OSError, LifecycleEvidenceError) as error:
        raise LifecycleEvidenceError("lifecycle_evidence_changed") from error
    if observed != expected:
        raise LifecycleEvidenceError("lifecycle_evidence_changed")
    path.unlink()
    if path.exists():
        raise LifecycleEvidenceError("lifecycle_evidence_release_failed")


def quarantine_lock(
    path: Path,
    *,
    expected_sha256: str,
    operator_session_id: str,
) -> Path:
    session_id = validate_session_id(operator_session_id)
    try:
        before_stat = path.stat()
        raw = path.read_bytes()
        payload = validate_lock_payload(_load_json_bytes(raw))
        after_stat = path.stat()
    except (OSError, LifecycleEvidenceError) as error:
        raise LifecycleEvidenceError("lock_evidence_changed") from error
    if (
        hashlib.sha256(raw).hexdigest() != expected_sha256
        or payload["operator_session_id"] != session_id
        or _stat_identity(before_stat) != _stat_identity(after_stat)
    ):
        raise LifecycleEvidenceError("lock_evidence_changed")
    destination = path.with_name(
        f"{QUARANTINE_PREFIX}{session_id}.{expected_sha256[:12]}{QUARANTINE_SUFFIX}"
    )
    if destination.exists():
        raise LifecycleEvidenceError("lock_quarantine_conflict")
    os.rename(path, destination)
    if path.exists() or destination.read_bytes() != raw:
        raise LifecycleEvidenceError("lock_quarantine_readback_failed")
    return destination


def quarantined_lock_paths(state_dir: Path) -> tuple[Path, ...]:
    return tuple(
        sorted(
            (
                path
                for path in state_dir.glob(
                    f"{QUARANTINE_PREFIX}*{QUARANTINE_SUFFIX}"
                )
                if path.is_file()
            ),
            key=lambda path: path.name,
        )
    )


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")


def _load_json_bytes(raw: bytes) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
        value = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, LifecycleEvidenceError) as error:
        raise LifecycleEvidenceError("lifecycle_json_invalid") from error
    if not isinstance(value, dict):
        raise LifecycleEvidenceError("lifecycle_json_invalid")
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LifecycleEvidenceError("lifecycle_json_duplicate_key")
        result[key] = value
    return result

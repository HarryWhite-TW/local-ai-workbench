"""Bounded, foreground-only Display Pilot operator candidate."""

from __future__ import annotations

import json
import hashlib
import math
import os
import re
import shlex
import stat
import subprocess
import time
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable

from .display_pilot_transport import parse_selector, validate_target
from .runtime_contract_binding import normalize_repo_path


SUMMARY_PROTOCOL = "hgw.display_pilot.operator.v1"
EVIDENCE_PROTOCOL = "hgw.display_pilot.canonical_evidence.v1"
RECOVERY_SUMMARY_PROTOCOL = "lawb.display_pilot.recovery.v1"
RECOVERY_INCIDENT_PROTOCOL = "lawb.display_pilot.recovery_incident.v1"
REPLAY_TOMBSTONE_PROTOCOL = "lawb.display_pilot.replay_tombstone.v1"
RUNNER_PROCESS_EVIDENCE_PROTOCOL = (
    "lawb.display_pilot.runner_process_evidence.v1"
)
RECOVERY_SCHEMA_VERSION = 1
RUNNER_PROCESS_EVIDENCE_SCHEMA_VERSION = 1
DEFAULT_MAX_CYCLES = 100
DEFAULT_POLL_INTERVAL_SECONDS = 5.0
MAX_CAPTURE_CHARS = 12_000
RUNNER_STREAM_PREVIEW_BYTES = 4_096
RUNNER_STREAM_TRUNCATION_MARKER = (
    "\n...[runner stream truncated]...\n"
)
RUNNER_LAUNCH_EXCEPTION_MESSAGE_CHARS = 1_000
RUNNER_DURATION_CLOCK_TOLERANCE_MS = 1_000
VERIFICATION_TIMEOUT_SECONDS = 600

_SHELL_SYNTAX = re.compile(r"[|;&><`$()\r\n]")
_ENV_EXPANSION = re.compile(r"%[^%]+%")
_RECOVERY_REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{2,127}\Z")
_SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")
_LOWER_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MACHINE_EVIDENCE_UNOBSERVED = object()
_RECOVERY_REQUEST_ARTIFACTS = {
    "original_in_flight.json",
    "original_in_flight.json.pending",
    "recovery_incident.json",
    "recovery_incident.json.pending",
    "runner_machine_evidence.json",
    "runner_process_evidence.json",
}
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
_FORBIDDEN_SIDE_EFFECT_FLAGS = (
    "github_write_performed",
    "commit_performed",
    "push_performed",
    "pr_created",
    "merge_performed",
    "issue_closed",
    "label_changed",
)
_REQUIRED_SAFETY_FLAGS = (
    "github_write_performed",
    "result_packet_written",
    "codex_side_action_executed",
    "runner_invoked",
    "dispatcher_invoked",
    "watcher_invoked",
    "broad_scan_performed",
    "commit_performed",
    "push_performed",
    "pr_created",
    "merge_performed",
    "issue_closed",
    "label_changed",
)
_SUCCESS_SAFETY_FLAGS = {
    "github_write_performed": False,
    "result_packet_written": True,
    "codex_side_action_executed": True,
    "runner_invoked": True,
    "dispatcher_invoked": False,
    "watcher_invoked": False,
    "broad_scan_performed": False,
    "commit_performed": False,
    "push_performed": False,
    "pr_created": False,
    "merge_performed": False,
    "issue_closed": False,
    "label_changed": False,
}
_EVIDENCE_FIELDS = {
    "protocol",
    "schema_version",
    "request_id",
    "repository",
    "issue",
    "repo_path",
    "branch",
    "head_before",
    "head_after",
    "codex_exit_code",
    "codex_status",
    "codex_timed_out",
    "runtime_contract_binding",
    "changed_files",
    "final_git_status",
    "staged_area_clean",
    "execution_assurance",
    "result_status",
    "blocked_reasons",
    "safety_flags",
    "review_bundle_comment_suppressed",
    "github_comment_posted",
}
_RUNTIME_CONTRACT_IDENTITY_FIELDS = (
    "protocol",
    "packet_id",
    "logical_issue",
    "repository",
    "branch",
    "expected_head",
    "task_mode",
    "allowed_files",
    "max_allowed_files",
    "verification_command_policy",
    "verification_commands",
    "scope_expansion_allowed",
)
_ALLOWED_PYTEST_FLAGS = {
    "-q",
    "--quiet",
    "-x",
    "--exitfirst",
    "--disable-warnings",
    "--strict-config",
    "--strict-markers",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class RunnerInvocationResult:
    """Parent-observed process facts returned by the Runner boundary."""

    process_started: bool
    exit_code: int | None
    timed_out: bool
    launch_exception: dict[str, str] | None
    started_at: str
    finished_at: str
    duration_ms: float
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True)
class _EvidenceSnapshot:
    raw: bytes
    identity: tuple[Any, ...]


@dataclass(frozen=True)
class _WindowsHandleInfo:
    attributes: int
    file_type: int
    volume_serial: int
    file_index: int
    size: int
    last_write: int


@dataclass(frozen=True)
class _ProcessedAppend:
    path: Path
    offset: int
    payload: bytes
    remove_if_empty: bool


_WINDOWS_GENERIC_READ = 0x80000000
_WINDOWS_FILE_SHARE_READ = 0x00000001
_WINDOWS_OPEN_EXISTING = 3
_WINDOWS_FILE_ATTRIBUTE_DIRECTORY = 0x00000010
_WINDOWS_FILE_ATTRIBUTE_NORMAL = 0x00000080
_WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
_WINDOWS_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_WINDOWS_FILE_TYPE_DISK = 0x0001


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    _atomic_text(
        path,
        json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n",
    )


def _atomic_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _summary() -> dict[str, Any]:
    return {
        "protocol": SUMMARY_PROTOCOL,
        "result": "success",
        "blocked_reasons": [],
        "cycles": 0,
        "request_processed": False,
        "runner_invoked": False,
        "runner_process_evidence_written": False,
        "runner_process_started": False,
        "runner_exit_code": None,
        "runner_timed_out": False,
        "machine_evidence_observed": False,
        "verification_invoked": False,
        "result_comment_candidate_count": 0,
        "github_write_performed": False,
        "commit_performed": False,
        "push_performed": False,
        "issue_closed": False,
        "label_changed": False,
        "pr_created": False,
        "merge_performed": False,
        "broad_issue_scan_performed": False,
        "latest_next_inference_performed": False,
        "safety_flags": {
            name: False for name in _REQUIRED_SAFETY_FLAGS
        },
    }


def _block(summary: dict[str, Any], *reasons: str) -> dict[str, Any]:
    summary["result"] = "blocked"
    summary["blocked_reasons"] = list(dict.fromkeys(reasons))
    return summary


def _bounded_exception(exc: BaseException) -> dict[str, str]:
    return {
        "type": f"{type(exc).__module__}.{type(exc).__qualname__}",
        "message": str(exc)[:RUNNER_LAUNCH_EXCEPTION_MESSAGE_CHARS],
    }


def _runner_stream_evidence(raw: bytes) -> dict[str, Any]:
    try:
        raw.decode("utf-8", errors="strict")
        replacement_used = False
    except UnicodeDecodeError:
        replacement_used = True
    if len(raw) <= RUNNER_STREAM_PREVIEW_BYTES:
        preview_truncated = False
        preview = raw.decode("utf-8", errors="replace")
    else:
        half = RUNNER_STREAM_PREVIEW_BYTES // 2
        if replacement_used:
            head = raw[:half]
            tail = raw[-half:]
        else:
            head_end = half
            while True:
                try:
                    head = raw[:head_end]
                    head.decode("utf-8", errors="strict")
                    break
                except UnicodeDecodeError:
                    head_end -= 1
            tail_start = len(raw) - half
            while True:
                try:
                    tail = raw[tail_start:]
                    tail.decode("utf-8", errors="strict")
                    break
                except UnicodeDecodeError:
                    tail_start += 1
        preview_truncated = True
        preview = (
            head.decode("utf-8", errors="replace")
            + RUNNER_STREAM_TRUNCATION_MARKER
            + tail.decode("utf-8", errors="replace")
        )
    return {
        "byte_count": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "preview": preview,
        "preview_truncated": preview_truncated,
        "decode_replacement_used": replacement_used,
    }


def _process_outcome_is_valid(
    *,
    process_started: Any,
    exit_code: Any,
    timed_out: Any,
    launch_exception: Any,
) -> bool:
    launch_failure = (
        process_started is False
        and exit_code is None
        and timed_out is False
        and launch_exception is not None
    )
    timeout = (
        process_started is True
        and exit_code is None
        and timed_out is True
        and launch_exception is None
    )
    completed = (
        process_started is True
        and type(exit_code) is int
        and timed_out is False
        and launch_exception is None
    )
    return sum((launch_failure, timeout, completed)) == 1


def _ordered_process_timestamps(
    *,
    started_at: Any,
    finished_at: Any,
    prepared_at: Any | None = None,
) -> bool:
    if not _supported_timestamp(started_at) or not _supported_timestamp(
        finished_at
    ):
        return False
    if prepared_at is not None and not _supported_timestamp(prepared_at):
        return False
    started = datetime.fromisoformat(started_at)
    finished = datetime.fromisoformat(finished_at)
    prepared = (
        datetime.fromisoformat(prepared_at)
        if prepared_at is not None
        else None
    )
    return started <= finished and (
        prepared is None or finished <= prepared
    )


def _process_duration_matches_timestamps(
    *,
    started_at: str,
    finished_at: str,
    duration_ms: int | float,
) -> bool:
    elapsed_ms = (
        datetime.fromisoformat(finished_at)
        - datetime.fromisoformat(started_at)
    ).total_seconds() * 1_000
    return (
        abs(duration_ms - elapsed_ms)
        <= RUNNER_DURATION_CLOCK_TOLERANCE_MS
    )


def _canonical_absolute_path_string(value: Any) -> bool:
    if type(value) is not str or not value:
        return False
    try:
        path = Path(value)
        return (
            path.is_absolute()
            and os.path.normcase(str(path.resolve()))
            == os.path.normcase(value)
        )
    except (OSError, RuntimeError):
        return False


def _nonnegative_finite_number(value: Any) -> bool:
    if type(value) not in {int, float} or isinstance(value, bool):
        return False
    try:
        return value >= 0 and math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def _replacement_preview_is_feasible(
    preview: str,
    *,
    byte_count: int,
    require_invalid_source: bool,
) -> bool:
    replacement_count = preview.count("\ufffd")
    if require_invalid_source and replacement_count == 0:
        return False
    try:
        fixed_byte_count = sum(
            len(character.encode("utf-8"))
            for character in preview
            if character != "\ufffd"
        )
    except UnicodeEncodeError:
        return False
    minimum = fixed_byte_count + replacement_count
    maximum = fixed_byte_count + (3 * replacement_count)
    return minimum <= byte_count <= maximum


def _strict_truncated_preview_is_feasible(
    head: str,
    tail: str,
    *,
    byte_count: int,
) -> bool:
    try:
        head_size = len(head.encode("utf-8"))
        tail_size = len(tail.encode("utf-8"))
    except UnicodeEncodeError:
        return False
    half = RUNNER_STREAM_PREVIEW_BYTES // 2
    head_adjustment = half - head_size
    tail_adjustment = half - tail_size
    if (
        head_adjustment not in range(4)
        or tail_adjustment not in range(4)
    ):
        return False
    gap = byte_count - head_size - tail_size
    if gap < 0:
        return False
    head_crossing_minimum = (
        head_adjustment + 1 if head_adjustment else 0
    )
    tail_crossing_minimum = (
        tail_adjustment + 1 if tail_adjustment else 0
    )
    if not head_adjustment and not tail_adjustment:
        return True
    if not head_adjustment:
        return gap >= tail_crossing_minimum
    if not tail_adjustment:
        return gap >= head_crossing_minimum
    same_character_crosses_both_boundaries = (
        2 <= gap <= 4
        and gap > head_adjustment
        and gap > tail_adjustment
    )
    separate_crossing_characters_fit = (
        gap >= head_crossing_minimum + tail_crossing_minimum
    )
    return (
        same_character_crosses_both_boundaries
        or separate_crossing_characters_fit
    )


def _stream_evidence_is_valid(stream: Any) -> bool:
    expected_keys = {
        "byte_count",
        "sha256",
        "preview",
        "preview_truncated",
        "decode_replacement_used",
    }
    if (
        type(stream) is not dict
        or set(stream) != expected_keys
        or type(stream.get("byte_count")) is not int
        or isinstance(stream.get("byte_count"), bool)
        or stream["byte_count"] < 0
        or type(stream.get("sha256")) is not str
        or _LOWER_SHA256.fullmatch(stream["sha256"]) is None
        or type(stream.get("preview")) is not str
        or type(stream.get("preview_truncated")) is not bool
        or type(stream.get("decode_replacement_used")) is not bool
        or stream["preview_truncated"]
        is not (stream["byte_count"] > RUNNER_STREAM_PREVIEW_BYTES)
    ):
        return False
    if stream["byte_count"] == 0:
        return stream == _runner_stream_evidence(b"")
    if not stream["preview"]:
        return False
    if stream["preview_truncated"]:
        marker = RUNNER_STREAM_TRUNCATION_MARKER
        marker_start = stream["preview"].find(marker)
        while marker_start >= 0:
            head = stream["preview"][:marker_start]
            tail = stream["preview"][marker_start + len(marker):]
            if head and tail:
                if stream["decode_replacement_used"]:
                    half = RUNNER_STREAM_PREVIEW_BYTES // 2
                    feasible = (
                        _replacement_preview_is_feasible(
                            head,
                            byte_count=half,
                            require_invalid_source=False,
                        )
                        and _replacement_preview_is_feasible(
                            tail,
                            byte_count=half,
                            require_invalid_source=False,
                        )
                    )
                else:
                    feasible = _strict_truncated_preview_is_feasible(
                        head,
                        tail,
                        byte_count=stream["byte_count"],
                    )
                if feasible:
                    return True
            marker_start = stream["preview"].find(
                marker,
                marker_start + 1,
            )
        return False
    elif not stream["decode_replacement_used"]:
        try:
            raw = stream["preview"].encode("utf-8")
        except UnicodeEncodeError:
            return False
        if (
            len(raw) != stream["byte_count"]
            or hashlib.sha256(raw).hexdigest() != stream["sha256"]
        ):
            return False
    elif not _replacement_preview_is_feasible(
        stream["preview"],
        byte_count=stream["byte_count"],
        require_invalid_source=True,
    ):
        return False
    return True


def _normalize_runner_result(
    value: RunnerInvocationResult | int,
    *,
    started_at: datetime,
    finished_at: datetime,
) -> RunnerInvocationResult:
    if isinstance(value, RunnerInvocationResult):
        result = value
    elif type(value) is int:
        result = RunnerInvocationResult(
            process_started=True,
            exit_code=value,
            timed_out=False,
            launch_exception=None,
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            duration_ms=max(
                0.0,
                (finished_at - started_at).total_seconds() * 1_000,
            ),
            stdout=b"",
            stderr=b"",
        )
    else:
        raise ValueError("runner_invocation_result_invalid")
    if (
        type(result.process_started) is not bool
        or (
            result.exit_code is not None
            and type(result.exit_code) is not int
        )
        or type(result.timed_out) is not bool
        or not _nonnegative_finite_number(result.duration_ms)
        or type(result.stdout) is not bytes
        or type(result.stderr) is not bytes
        or not _ordered_process_timestamps(
            started_at=result.started_at,
            finished_at=result.finished_at,
        )
        or not _process_duration_matches_timestamps(
            started_at=result.started_at,
            finished_at=result.finished_at,
            duration_ms=result.duration_ms,
        )
        or (
            result.launch_exception is not None
            and (
                type(result.launch_exception) is not dict
                or set(result.launch_exception) != {"type", "message"}
                or any(
                    type(item) is not str
                    for item in result.launch_exception.values()
                )
                or not result.launch_exception["type"]
                or len(result.launch_exception["message"])
                > RUNNER_LAUNCH_EXCEPTION_MESSAGE_CHARS
            )
        )
        or not _process_outcome_is_valid(
            process_started=result.process_started,
            exit_code=result.exit_code,
            timed_out=result.timed_out,
            launch_exception=result.launch_exception,
        )
        or (
            result.process_started is False
            and (result.stdout != b"" or result.stderr != b"")
        )
    ):
        raise ValueError("runner_invocation_result_invalid")
    return result


def _process_evidence_value(
    *,
    request_id: str,
    target_issue: int,
    target_repo_root: str | Path,
    runner_path: str | Path,
    powershell_path: str | Path,
    machine_evidence_path: Path,
    machine_evidence_bytes: bytes | None,
    result: RunnerInvocationResult,
    prepared_at: str,
) -> dict[str, Any]:
    return {
        "protocol": RUNNER_PROCESS_EVIDENCE_PROTOCOL,
        "schema_version": RUNNER_PROCESS_EVIDENCE_SCHEMA_VERSION,
        "request_id": request_id,
        "target_issue": target_issue,
        "target_repository": (
            "HarryWhite-TW/human-approval-automation-gateway"
        ),
        "target_repo_root": str(Path(target_repo_root).resolve()),
        "runner_path": str(Path(runner_path).resolve()),
        "powershell_path": str(Path(powershell_path).resolve()),
        "prepared_at": prepared_at,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "duration_ms": result.duration_ms,
        "process_started": result.process_started,
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "launch_exception": result.launch_exception,
        "stdout": _runner_stream_evidence(result.stdout),
        "stderr": _runner_stream_evidence(result.stderr),
        "machine_evidence_path": str(machine_evidence_path.absolute()),
        "machine_evidence_observed": machine_evidence_bytes is not None,
        "machine_evidence_size": (
            len(machine_evidence_bytes)
            if machine_evidence_bytes is not None
            else None
        ),
        "machine_evidence_sha256": (
            hashlib.sha256(machine_evidence_bytes).hexdigest()
            if machine_evidence_bytes is not None
            else None
        ),
    }


def _validate_runner_process_evidence(
    value: Any,
    *,
    request_id: str,
    target_issue: int,
    target_repo_root: str | Path | None = None,
    runner_path: str | Path | None = None,
    powershell_path: str | Path | None = None,
    machine_evidence_path: str | Path | None = None,
    stdout: bytes | None = None,
    stderr: bytes | None = None,
    machine_evidence_bytes: bytes | None | object = (
        _MACHINE_EVIDENCE_UNOBSERVED
    ),
) -> dict[str, Any]:
    expected_keys = {
        "protocol",
        "schema_version",
        "request_id",
        "target_issue",
        "target_repository",
        "target_repo_root",
        "runner_path",
        "powershell_path",
        "prepared_at",
        "started_at",
        "finished_at",
        "duration_ms",
        "process_started",
        "exit_code",
        "timed_out",
        "launch_exception",
        "stdout",
        "stderr",
        "machine_evidence_path",
        "machine_evidence_observed",
        "machine_evidence_size",
        "machine_evidence_sha256",
    }
    invalid = (
        type(value) is not dict
        or set(value) != expected_keys
        or value.get("protocol") != RUNNER_PROCESS_EVIDENCE_PROTOCOL
        or type(value.get("schema_version")) is not int
        or value.get("schema_version")
        != RUNNER_PROCESS_EVIDENCE_SCHEMA_VERSION
        or value.get("request_id") != request_id
        or value.get("target_issue") != target_issue
        or type(value.get("target_issue")) is not int
        or value.get("target_repository")
        != "HarryWhite-TW/human-approval-automation-gateway"
        or any(
            not _canonical_absolute_path_string(value.get(name))
            for name in (
                "target_repo_root",
                "runner_path",
                "powershell_path",
                "machine_evidence_path",
            )
        )
        or not _ordered_process_timestamps(
            started_at=value.get("started_at"),
            finished_at=value.get("finished_at"),
            prepared_at=value.get("prepared_at"),
        )
        or not _nonnegative_finite_number(value.get("duration_ms"))
        or not _process_duration_matches_timestamps(
            started_at=value.get("started_at"),
            finished_at=value.get("finished_at"),
            duration_ms=value.get("duration_ms"),
        )
        or type(value.get("process_started")) is not bool
        or (
            value.get("exit_code") is not None
            and type(value.get("exit_code")) is not int
        )
        or type(value.get("timed_out")) is not bool
        or (
            value.get("launch_exception") is not None
            and (
                type(value.get("launch_exception")) is not dict
                or set(value["launch_exception"]) != {"type", "message"}
                or any(
                    type(item) is not str
                    for item in value["launch_exception"].values()
                )
                or not value["launch_exception"]["type"]
                or len(value["launch_exception"]["message"])
                > RUNNER_LAUNCH_EXCEPTION_MESSAGE_CHARS
            )
        )
        or type(value.get("machine_evidence_observed")) is not bool
        or (
            value.get("machine_evidence_observed") is False
            and (
                value.get("machine_evidence_size") is not None
                or value.get("machine_evidence_sha256") is not None
            )
        )
        or (
            value.get("machine_evidence_observed") is True
            and (
                type(value.get("machine_evidence_size")) is not int
                or isinstance(value.get("machine_evidence_size"), bool)
                or value.get("machine_evidence_size", -1) < 0
                or type(value.get("machine_evidence_sha256")) is not str
                or _LOWER_SHA256.fullmatch(
                    value.get("machine_evidence_sha256", "")
                )
                is None
            )
        )
    )
    if invalid:
        raise ValueError("runner_process_evidence_invalid")
    if (
        target_repo_root is not None
        and os.path.normcase(value["target_repo_root"])
        != os.path.normcase(str(Path(target_repo_root).resolve()))
    ):
        raise ValueError("runner_process_evidence_identity_mismatch")
    for name, expected in (
        ("runner_path", runner_path),
        ("powershell_path", powershell_path),
        ("machine_evidence_path", machine_evidence_path),
    ):
        if expected is None:
            continue
        expected_path = (
            Path(expected).absolute()
            if name == "machine_evidence_path"
            else Path(expected).resolve()
        )
        if os.path.normcase(value[name]) != os.path.normcase(
            str(expected_path)
        ):
            raise ValueError("runner_process_evidence_identity_mismatch")
    for name, raw in (("stdout", stdout), ("stderr", stderr)):
        stream = value.get(name)
        if raw is not None:
            stream_is_valid = stream == _runner_stream_evidence(raw)
        else:
            stream_is_valid = _stream_evidence_is_valid(stream)
        if not stream_is_valid:
            raise ValueError("runner_process_evidence_invalid")
    if not _process_outcome_is_valid(
        process_started=value["process_started"],
        exit_code=value["exit_code"],
        timed_out=value["timed_out"],
        launch_exception=value["launch_exception"],
    ) or (
        value["process_started"] is False
        and (
            value["stdout"]["byte_count"] != 0
            or value["stderr"]["byte_count"] != 0
        )
    ):
        raise ValueError("runner_process_evidence_invalid")
    if machine_evidence_bytes is not _MACHINE_EVIDENCE_UNOBSERVED:
        expected_observed = machine_evidence_bytes is not None
        if value["machine_evidence_observed"] is not expected_observed:
            raise ValueError("runner_process_evidence_invalid")
        if machine_evidence_bytes is not None and (
            value["machine_evidence_size"] != len(machine_evidence_bytes)
            or value["machine_evidence_sha256"]
            != hashlib.sha256(machine_evidence_bytes).hexdigest()
        ):
            raise ValueError("runner_process_evidence_invalid")
    return value


def _write_runner_process_evidence(
    path: Path,
    value: dict[str, Any],
    *,
    validation: dict[str, Any],
) -> None:
    if os.path.lexists(path):
        raise ValueError("runner_process_evidence_conflict")
    raw = (
        json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary_created = False
    try:
        with temporary.open("xb") as handle:
            temporary_created = True
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if os.path.lexists(path):
            raise ValueError("runner_process_evidence_conflict")
        os.link(temporary, path, follow_symlinks=False)
        observed_raw = path.read_bytes()
        if observed_raw != raw:
            raise ValueError("runner_process_evidence_invalid")
        observed = _load_json_bytes(
            observed_raw,
            reason="runner_process_evidence_invalid",
        )
        if observed != value:
            raise ValueError("runner_process_evidence_invalid")
        _validate_runner_process_evidence(observed, **validation)
    finally:
        if temporary_created:
            temporary.unlink(missing_ok=True)


def _acquire_lock(path: Path) -> int | None:
    try:
        return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return None


def _processed_request_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    result: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            request_id = record.get("request_id") if type(record) is dict else None
            if not isinstance(request_id, str) or not request_id:
                raise ValueError("processed_record_invalid")
            result.add(request_id)
    return result


def _append_processed(
    path: Path,
    record: dict[str, Any],
    *,
    evidence_guard: _CanonicalEvidenceGuard | None = None,
) -> _ProcessedAppend:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")
    remove_if_empty = not path.exists()
    try:
        with path.open("ab") as handle:
            offset = handle.tell()
            append = _ProcessedAppend(
                path=path,
                offset=offset,
                payload=payload,
                remove_if_empty=remove_if_empty,
            )
            try:
                if evidence_guard is not None:
                    evidence_guard.require_unchanged()
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
                if evidence_guard is not None:
                    evidence_guard.require_unchanged()
            except Exception:
                handle.seek(0, os.SEEK_END)
                if handle.tell() == offset + len(payload):
                    handle.truncate(offset)
                    handle.flush()
                    os.fsync(handle.fileno())
                raise
    except Exception:
        if remove_if_empty and path.exists() and path.stat().st_size == 0:
            path.unlink()
        raise
    return append


def _rollback_processed_append(append: _ProcessedAppend) -> None:
    with append.path.open("r+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() != append.offset + len(append.payload):
            raise OSError("processed record changed during rollback")
        handle.seek(append.offset)
        if handle.read() != append.payload:
            raise OSError("processed record changed during rollback")
        handle.truncate(append.offset)
        handle.flush()
        os.fsync(handle.fileno())
    if append.remove_if_empty and append.offset == 0:
        append.path.unlink()


def _release_in_flight(
    path: Path,
    *,
    evidence_guard: _CanonicalEvidenceGuard,
) -> None:
    evidence_guard.require_unchanged()
    path.unlink()
    evidence_guard.require_unchanged()


def _recovery_summary(
    *,
    request_id: Any,
    target_issue: Any,
    in_flight_sha256: Any,
) -> dict[str, Any]:
    return {
        "protocol": RECOVERY_SUMMARY_PROTOCOL,
        "result": "blocked",
        "recovery_status": "blocked",
        "blocked_reasons": [],
        "request_id": request_id,
        "target_issue": target_issue,
        "original_in_flight_sha256": (
            in_flight_sha256.lower()
            if isinstance(in_flight_sha256, str)
            else in_flight_sha256
        ),
        "original_evidence_preserved": False,
        "incident_record": "not_written",
        "replay_tombstone": "not_written",
        "active_in_flight_released": False,
        "runner_invoked": False,
        "codex_invoked": False,
        "github_write_performed": False,
        "repository_mutation_performed": False,
    }


def _recovery_block(summary: dict[str, Any], reason: str) -> dict[str, Any]:
    summary["result"] = "blocked"
    summary["recovery_status"] = "blocked"
    summary["blocked_reasons"] = [reason]
    return summary


def _request_id_is_safe(value: Any) -> bool:
    return (
        type(value) is str
        and _RECOVERY_REQUEST_ID.fullmatch(value) is not None
        and not value.endswith((".", " "))
        and value.split(".", 1)[0].upper() not in _WINDOWS_RESERVED_NAMES
    )


def _supported_timestamp(value: Any) -> bool:
    if type(value) is not str or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value)
        value.encode("utf-8")
    except (ValueError, UnicodeError):
        return False
    return parsed.tzinfo is not None


def _load_json_bytes(raw: bytes, *, reason: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(reason) from exc
    if type(value) is not dict:
        raise ValueError(reason)
    return value


def _evidence_entry_identity(metadata: os.stat_result) -> tuple[Any, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        stat.S_IFMT(metadata.st_mode),
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        getattr(metadata, "st_file_attributes", 0),
        getattr(metadata, "st_reparse_tag", 0),
    )


def _entry_is_regular_non_reparse(metadata: os.stat_result) -> bool:
    reparse_attribute = getattr(
        stat,
        "FILE_ATTRIBUTE_REPARSE_POINT",
        0x400,
    )
    return (
        stat.S_ISREG(metadata.st_mode)
        and not stat.S_ISLNK(metadata.st_mode)
        and not (
            getattr(metadata, "st_file_attributes", 0)
            & reparse_attribute
        )
        and getattr(metadata, "st_reparse_tag", 0) == 0
    )


def _entry_and_handle_identify_same_file(
    entry: os.stat_result,
    opened: os.stat_result,
) -> bool:
    return (
        entry.st_dev == opened.st_dev
        and entry.st_ino == opened.st_ino
        and stat.S_IFMT(entry.st_mode) == stat.S_IFMT(opened.st_mode)
        and entry.st_size == opened.st_size
        and entry.st_mtime_ns == opened.st_mtime_ns
        and getattr(entry, "st_file_attributes", 0)
        == getattr(opened, "st_file_attributes", 0)
        and getattr(entry, "st_reparse_tag", 0)
        == getattr(opened, "st_reparse_tag", 0)
    )


def _win32_create_file(
    path: Path,
    desired_access: int,
    share_mode: int,
    creation_disposition: int,
    flags_and_attributes: int,
) -> int:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        str(path),
        desired_access,
        share_mode,
        None,
        creation_disposition,
        flags_and_attributes,
        None,
    )
    handle_value = (
        handle
        if isinstance(handle, int)
        else getattr(handle, "value", None)
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle_value in {None, invalid_handle}:
        raise ctypes.WinError(ctypes.get_last_error())
    return int(handle_value)


def _win32_create_evidence_handle(path: Path) -> int:
    return _win32_create_file(
        path,
        _WINDOWS_GENERIC_READ,
        _WINDOWS_FILE_SHARE_READ,
        _WINDOWS_OPEN_EXISTING,
        (
            _WINDOWS_FILE_ATTRIBUTE_NORMAL
            | _WINDOWS_FILE_FLAG_OPEN_REPARSE_POINT
        ),
    )


def _win32_evidence_handle_info(handle: int) -> _WindowsHandleInfo:
    import ctypes
    from ctypes import wintypes

    class _ByHandleFileInformation(ctypes.Structure):
        _fields_ = (
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", wintypes.FILETIME),
            ("ftLastAccessTime", wintypes.FILETIME),
            ("ftLastWriteTime", wintypes.FILETIME),
            ("dwVolumeSerialNumber", wintypes.DWORD),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("nNumberOfLinks", wintypes.DWORD),
            ("nFileIndexHigh", wintypes.DWORD),
            ("nFileIndexLow", wintypes.DWORD),
        )

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_information = kernel32.GetFileInformationByHandle
    get_information.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(_ByHandleFileInformation),
    )
    get_information.restype = wintypes.BOOL
    get_file_type = kernel32.GetFileType
    get_file_type.argtypes = (wintypes.HANDLE,)
    get_file_type.restype = wintypes.DWORD
    information = _ByHandleFileInformation()
    if not get_information(
        wintypes.HANDLE(handle),
        ctypes.byref(information),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    file_type = int(get_file_type(wintypes.HANDLE(handle)))
    if file_type == 0:
        error = ctypes.get_last_error()
        if error:
            raise ctypes.WinError(error)
    return _WindowsHandleInfo(
        attributes=int(information.dwFileAttributes),
        file_type=file_type,
        volume_serial=int(information.dwVolumeSerialNumber),
        file_index=(
            int(information.nFileIndexHigh) << 32
        ) | int(information.nFileIndexLow),
        size=(
            int(information.nFileSizeHigh) << 32
        ) | int(information.nFileSizeLow),
        last_write=(
            int(information.ftLastWriteTime.dwHighDateTime) << 32
        ) | int(information.ftLastWriteTime.dwLowDateTime),
    )


def _win32_read_evidence_handle(handle: int, expected_size: int) -> bytes:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    set_pointer = kernel32.SetFilePointerEx
    set_pointer.argtypes = (
        wintypes.HANDLE,
        ctypes.c_longlong,
        ctypes.POINTER(ctypes.c_longlong),
        wintypes.DWORD,
    )
    set_pointer.restype = wintypes.BOOL
    read_file = kernel32.ReadFile
    read_file.argtypes = (
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    )
    read_file.restype = wintypes.BOOL
    if not set_pointer(
        wintypes.HANDLE(handle),
        0,
        None,
        0,
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    chunks: list[bytes] = []
    remaining = expected_size
    while remaining:
        chunk_size = min(remaining, 1024 * 1024)
        buffer = ctypes.create_string_buffer(chunk_size)
        read_count = wintypes.DWORD()
        if not read_file(
            wintypes.HANDLE(handle),
            buffer,
            chunk_size,
            ctypes.byref(read_count),
            None,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if read_count.value == 0:
            raise OSError("unexpected end of canonical evidence")
        chunks.append(buffer.raw[:read_count.value])
        remaining -= read_count.value
    return b"".join(chunks)


def _win32_close_evidence_handle(handle: int) -> None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    if not close_handle(wintypes.HANDLE(handle)):
        raise ctypes.WinError(ctypes.get_last_error())


def _windows_handle_is_regular_non_reparse(
    information: _WindowsHandleInfo,
) -> bool:
    return (
        information.file_type == _WINDOWS_FILE_TYPE_DISK
        and not (
            information.attributes
            & (
                _WINDOWS_FILE_ATTRIBUTE_DIRECTORY
                | _WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT
            )
        )
    )


def _read_posix_evidence_descriptor(descriptor: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


class _CanonicalEvidenceGuard:
    def __init__(
        self,
        path: Path,
        *,
        reason: str,
        raw: bytes,
        identity: tuple[Any, ...],
        descriptor: int | None = None,
        windows_handle: int | None = None,
        windows_info: _WindowsHandleInfo | None = None,
    ) -> None:
        self.path = path
        self.reason = reason
        self.raw = raw
        self.identity = identity
        self._descriptor = descriptor
        self._windows_handle = windows_handle
        self._windows_info = windows_info

    def require_unchanged(self) -> None:
        try:
            if self._windows_handle is not None:
                before = _win32_evidence_handle_info(
                    self._windows_handle
                )
                if (
                    before != self._windows_info
                    or not _windows_handle_is_regular_non_reparse(before)
                ):
                    raise ValueError(self.reason)
                raw = _win32_read_evidence_handle(
                    self._windows_handle,
                    before.size,
                )
                after = _win32_evidence_handle_info(
                    self._windows_handle
                )
                if after != before:
                    raise ValueError(self.reason)
            elif self._descriptor is not None:
                before_stat = os.fstat(self._descriptor)
                raw = _read_posix_evidence_descriptor(self._descriptor)
                after_stat = os.fstat(self._descriptor)
                if (
                    not _entry_is_regular_non_reparse(after_stat)
                    or _evidence_entry_identity(before_stat)
                    != _evidence_entry_identity(after_stat)
                    or len(raw) != after_stat.st_size
                ):
                    raise ValueError(self.reason)
            else:
                raise ValueError(self.reason)
            path_stat = os.lstat(self.path)
            if (
                raw != self.raw
                or not _entry_is_regular_non_reparse(path_stat)
                or _evidence_entry_identity(path_stat) != self.identity
            ):
                raise ValueError(self.reason)
        except (OSError, ValueError) as exc:
            if isinstance(exc, ValueError) and str(exc) == self.reason:
                raise
            raise ValueError(self.reason) from exc

    def close(self) -> None:
        descriptor, self._descriptor = self._descriptor, None
        windows_handle, self._windows_handle = self._windows_handle, None
        if descriptor is not None:
            os.close(descriptor)
        if windows_handle is not None:
            try:
                _win32_close_evidence_handle(windows_handle)
            except OSError:
                pass


def _open_canonical_evidence_guard(
    path: Path,
    *,
    reason: str,
) -> _CanonicalEvidenceGuard:
    before: os.stat_result
    try:
        before = os.lstat(path)
        if not _entry_is_regular_non_reparse(before):
            raise ValueError(reason)
        identity = _evidence_entry_identity(before)
        if os.name == "nt":
            handle: int | None = None
            try:
                handle = _win32_create_evidence_handle(path)
                information = _win32_evidence_handle_info(handle)
                if (
                    not _windows_handle_is_regular_non_reparse(information)
                    or (
                        before.st_ino
                        and information.file_index != before.st_ino
                    )
                ):
                    raise ValueError(reason)
                raw = _win32_read_evidence_handle(
                    handle,
                    information.size,
                )
                after_read = _win32_evidence_handle_info(handle)
                after = os.lstat(path)
                if (
                    after_read != information
                    or len(raw) != information.size
                    or not _entry_is_regular_non_reparse(after)
                    or _evidence_entry_identity(after) != identity
                ):
                    raise ValueError(reason)
                return _CanonicalEvidenceGuard(
                    path,
                    reason=reason,
                    raw=raw,
                    identity=identity,
                    windows_handle=handle,
                    windows_info=information,
                )
            except Exception:
                if handle is not None:
                    try:
                        _win32_close_evidence_handle(handle)
                    except OSError:
                        pass
                raise
        no_follow = getattr(os, "O_NOFOLLOW", None)
        if no_follow is None:
            raise ValueError(reason)
        descriptor: int | None = None
        try:
            descriptor = os.open(
                path,
                os.O_RDONLY | getattr(os, "O_BINARY", 0) | no_follow,
            )
            opened = os.fstat(descriptor)
            if (
                not _entry_is_regular_non_reparse(opened)
                or not _entry_and_handle_identify_same_file(before, opened)
            ):
                raise ValueError(reason)
            raw = _read_posix_evidence_descriptor(descriptor)
            after_read = os.fstat(descriptor)
            after = os.lstat(path)
            if (
                _evidence_entry_identity(after_read)
                != _evidence_entry_identity(opened)
                or len(raw) != after_read.st_size
                or not _entry_is_regular_non_reparse(after)
                or _evidence_entry_identity(after) != identity
            ):
                raise ValueError(reason)
            return _CanonicalEvidenceGuard(
                path,
                reason=reason,
                raw=raw,
                identity=identity,
                descriptor=descriptor,
            )
        except Exception:
            if descriptor is not None:
                os.close(descriptor)
            raise
    except (OSError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc) == reason:
            raise
        raise ValueError(reason) from exc


def _read_canonical_evidence_snapshot(
    path: Path,
    *,
    reason: str,
) -> _EvidenceSnapshot:
    guard: _CanonicalEvidenceGuard | None = None
    try:
        guard = _open_canonical_evidence_guard(path, reason=reason)
        return _EvidenceSnapshot(
            raw=guard.raw,
            identity=guard.identity,
        )
    finally:
        if guard is not None:
            guard.close()


def _require_canonical_evidence_unchanged(
    path: Path,
    snapshot: _EvidenceSnapshot,
    *,
    reason: str,
) -> None:
    observed = _read_canonical_evidence_snapshot(path, reason=reason)
    if observed.identity != snapshot.identity or observed.raw != snapshot.raw:
        raise ValueError(reason)


def _validated_in_flight(
    raw: bytes,
    *,
    request_id: str,
    target_issue: int,
) -> dict[str, Any]:
    value = _load_json_bytes(raw, reason="in_flight_invalid")
    if (
        set(value) != {"request_id", "target_issue", "state", "at"}
        or value.get("request_id") != request_id
        or value.get("target_issue") != target_issue
        or type(value.get("target_issue")) is not int
        or value.get("state") != "delegating_runner"
        or not _supported_timestamp(value.get("at"))
    ):
        if value.get("request_id") != request_id:
            raise ValueError("in_flight_request_id_mismatch")
        if value.get("target_issue") != target_issue:
            raise ValueError("in_flight_target_issue_mismatch")
        if value.get("state") != "delegating_runner":
            raise ValueError("in_flight_state_unsupported")
        raise ValueError("in_flight_invalid")
    return value


def _incident_expected(
    *,
    request_id: str,
    target_issue: int,
    in_flight_sha256: str,
    in_flight_size: int,
    observed_request_directory_inventory: list[str],
    recorded_at: str,
) -> dict[str, Any]:
    return {
        "protocol": RECOVERY_INCIDENT_PROTOCOL,
        "schema_version": RECOVERY_SCHEMA_VERSION,
        "request_id": request_id,
        "target_issue": target_issue,
        "original_state": "delegating_runner",
        "original_in_flight_sha256": in_flight_sha256,
        "original_in_flight_size": in_flight_size,
        "original_in_flight_relative_path": (
            f"requests/{request_id}/original_in_flight.json"
        ),
        "observed_request_directory_inventory_before_recovery": list(
            observed_request_directory_inventory
        ),
        "outcome": "uncertain",
        "replay_policy": "prohibited",
        "recovery_reason_code": "uncertain_delegation_interrupted",
        "recorded_at": recorded_at,
    }


def _tombstone_expected(
    *,
    request_id: str,
    target_issue: int,
    in_flight_sha256: str,
    recorded_at: str,
) -> dict[str, Any]:
    return {
        "protocol": REPLAY_TOMBSTONE_PROTOCOL,
        "schema_version": RECOVERY_SCHEMA_VERSION,
        "request_id": request_id,
        "target_issue": target_issue,
        "outcome": "uncertain",
        "replay_policy": "prohibited",
        "original_in_flight_sha256": in_flight_sha256,
        "incident_record": f"requests/{request_id}/recovery_incident.json",
        "recorded_at": recorded_at,
    }


def _load_exact_record(
    path: Path,
    *,
    expected_without_timestamp: dict[str, Any],
    invalid_reason: str,
) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(invalid_reason) from exc
    value = _load_json_bytes(raw, reason=invalid_reason)
    if (
        set(value) != set(expected_without_timestamp) | {"recorded_at"}
        or not _supported_timestamp(value.get("recorded_at"))
        or any(value.get(key) != expected for key, expected in expected_without_timestamp.items())
    ):
        raise ValueError(invalid_reason)
    return value


def _verify_original_snapshot(
    path: Path,
    *,
    expected_bytes: bytes,
    expected_sha256: str,
) -> None:
    try:
        observed = path.read_bytes()
    except OSError as exc:
        raise ValueError("original_snapshot_invalid") from exc
    if (
        observed != expected_bytes
        or len(observed) != len(expected_bytes)
        or hashlib.sha256(observed).hexdigest() != expected_sha256
    ):
        raise ValueError("original_snapshot_conflict")


def _recovery_json_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")


def _recovery_pending_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.pending")


def _write_recovery_pending(path: Path, value: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())


def _promote_recovery_pending(
    path: Path,
    *,
    expected_bytes: bytes,
    conflict_reason: str,
    pending_phase: str,
    hook: Callable[[str], None],
) -> bool:
    pending = _recovery_pending_path(path)
    canonical_preexisting = path.exists()
    if canonical_preexisting:
        if not path.is_file() or path.read_bytes() != expected_bytes:
            raise ValueError(conflict_reason)
        if pending.exists():
            if not pending.is_file() or pending.read_bytes() != expected_bytes:
                raise ValueError(conflict_reason)
            pending.unlink()
        return True

    if pending.exists():
        if not pending.is_file() or pending.read_bytes() != expected_bytes:
            raise ValueError(conflict_reason)
    else:
        _write_recovery_pending(pending, expected_bytes)
    hook(pending_phase)
    os.replace(pending, path)
    if not path.is_file() or path.read_bytes() != expected_bytes:
        raise ValueError(conflict_reason)
    return False


def _recovery_paths_are_safe(
    *,
    root: Path,
    paths: tuple[Path, ...],
    forbidden_roots: tuple[str | Path, ...],
) -> bool:
    try:
        resolved_forbidden = tuple(
            Path(forbidden).resolve() for forbidden in forbidden_roots
        )
        for path in paths:
            resolved = path.resolve()
            if not _path_is_within(resolved, root) or any(
                _path_is_within(resolved, forbidden)
                for forbidden in resolved_forbidden
            ):
                return False
    except OSError:
        return False
    return True


def _create_recovery_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _prepare_replay_tombstone_store(
    store: Path,
    *,
    root: Path,
    tombstone_path: Path,
    forbidden_roots: tuple[str | Path, ...],
    create_directory: Callable[[Path], None],
) -> None:
    checked_paths = (
        store.parent,
        store,
        tombstone_path,
        _recovery_pending_path(tombstone_path),
    )
    if not _recovery_paths_are_safe(
        root=root,
        paths=checked_paths,
        forbidden_roots=forbidden_roots,
    ):
        raise ValueError("recovery_path_escape")
    if not store.exists():
        try:
            create_directory(store)
        except OSError as exc:
            raise ValueError("replay_tombstone_store_invalid") from exc
    if not store.is_dir():
        raise ValueError("replay_tombstone_store_invalid")
    if not _recovery_paths_are_safe(
        root=root,
        paths=checked_paths,
        forbidden_roots=forbidden_roots,
    ):
        raise ValueError("recovery_path_escape")
    if not store.is_dir():
        raise ValueError("replay_tombstone_store_invalid")


def _load_replay_tombstone(
    root: Path,
    *,
    request_id: str,
    target_issue: int,
) -> dict[str, Any] | None:
    store = root / "replay_tombstones"
    if store.exists() and not store.is_dir():
        raise ValueError("replay_tombstone_store_invalid")
    path = store / f"{request_id}.json"
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError("replay_tombstone_invalid")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError("replay_tombstone_invalid") from exc
    value = _load_json_bytes(raw, reason="replay_tombstone_invalid")
    expected_keys = {
        "protocol",
        "schema_version",
        "request_id",
        "target_issue",
        "outcome",
        "replay_policy",
        "original_in_flight_sha256",
        "incident_record",
        "recorded_at",
    }
    if (
        set(value) != expected_keys
        or value.get("protocol") != REPLAY_TOMBSTONE_PROTOCOL
        or value.get("schema_version") != RECOVERY_SCHEMA_VERSION
        or value.get("request_id") != request_id
        or value.get("target_issue") != target_issue
        or type(value.get("target_issue")) is not int
        or value.get("outcome") != "uncertain"
        or value.get("replay_policy") != "prohibited"
        or type(value.get("original_in_flight_sha256")) is not str
        or _SHA256.fullmatch(value["original_in_flight_sha256"]) is None
        or value.get("incident_record")
        != f"requests/{request_id}/recovery_incident.json"
        or not _supported_timestamp(value.get("recorded_at"))
    ):
        raise ValueError("replay_tombstone_invalid")
    return value


def recover_incident(
    *,
    state_root: str | Path,
    request_id: str,
    target_issue: int,
    in_flight_sha256: str,
    forbidden_state_roots: tuple[str | Path, ...] = (),
    now: Callable[[], datetime] = _utc_now,
    phase_hook: Callable[[str], None] | None = None,
    remove_in_flight: Callable[[Path], None] | None = None,
    create_tombstone_store: Callable[[Path], None] = _create_recovery_directory,
) -> dict[str, Any]:
    """Close one exact uncertain delegation without retrying or inferring state."""
    summary = _recovery_summary(
        request_id=request_id,
        target_issue=target_issue,
        in_flight_sha256=in_flight_sha256,
    )
    if not _request_id_is_safe(request_id):
        return _recovery_block(summary, "request_id_invalid")
    if type(target_issue) is not int or target_issue <= 0:
        return _recovery_block(summary, "target_issue_invalid")
    if type(in_flight_sha256) is not str or _SHA256.fullmatch(
        in_flight_sha256
    ) is None:
        return _recovery_block(summary, "in_flight_sha256_invalid")

    expected_sha256 = in_flight_sha256.lower()
    root = Path(state_root).resolve()
    if any(
        _path_is_within(root, Path(forbidden).resolve())
        for forbidden in forbidden_state_roots
    ):
        return _recovery_block(summary, "state_root_inside_git_worktree")
    if not root.is_dir():
        return _recovery_block(summary, "state_root_missing")

    lock_path = root / "operator.lock"
    in_flight_path = root / "in_flight.json"
    processed_path = root / "processed_requests.jsonl"
    requests_root = root / "requests"
    request_root = root / "requests" / request_id
    process_evidence_path = request_root / "runner_process_evidence.json"
    machine_evidence_path = request_root / "runner_machine_evidence.json"
    original_path = request_root / "original_in_flight.json"
    incident_path = request_root / "recovery_incident.json"
    tombstone_store = root / "replay_tombstones"
    tombstone_path = tombstone_store / f"{request_id}.json"
    recovery_paths = (
        lock_path,
        in_flight_path,
        processed_path,
        requests_root,
        request_root,
        process_evidence_path,
        machine_evidence_path,
        original_path,
        _recovery_pending_path(original_path),
        incident_path,
        _recovery_pending_path(incident_path),
        tombstone_store,
        tombstone_path,
        _recovery_pending_path(tombstone_path),
    )
    if not _recovery_paths_are_safe(
        root=root,
        paths=recovery_paths,
        forbidden_roots=forbidden_state_roots,
    ):
        return _recovery_block(summary, "recovery_path_escape")

    lock_handle = _acquire_lock(lock_path)
    if lock_handle is None:
        return _recovery_block(summary, "active_lock_present")
    hook = phase_hook or (lambda _: None)
    unlink = remove_in_flight or (lambda path: path.unlink())

    try:
        os.write(lock_handle, f"pid={os.getpid()}\n".encode("ascii"))
        os.close(lock_handle)
        lock_handle = -1

        if not request_root.is_dir():
            return _recovery_block(summary, "request_directory_missing")
        try:
            entries = {entry.name for entry in request_root.iterdir()}
        except OSError:
            return _recovery_block(summary, "request_directory_invalid")
        if entries - _RECOVERY_REQUEST_ARTIFACTS:
            return _recovery_block(summary, "request_directory_not_empty")
        observed_incident_inventory = sorted(
            entries
            - {
                "original_in_flight.json",
                "original_in_flight.json.pending",
                "recovery_incident.json",
                "recovery_incident.json.pending",
            }
        )
        process_evidence_entry = os.path.lexists(process_evidence_path)
        machine_evidence_entry = os.path.lexists(machine_evidence_path)
        if machine_evidence_entry and not process_evidence_entry:
            return _recovery_block(
                summary,
                "request_directory_not_empty",
            )
        process_evidence_snapshot: _EvidenceSnapshot | None = None
        machine_evidence_snapshot: _EvidenceSnapshot | None = None
        if process_evidence_entry:
            try:
                process_evidence_snapshot = (
                    _read_canonical_evidence_snapshot(
                        process_evidence_path,
                        reason="runner_process_evidence_invalid",
                    )
                )
                if machine_evidence_entry:
                    machine_evidence_snapshot = (
                        _read_canonical_evidence_snapshot(
                            machine_evidence_path,
                            reason="runner_process_evidence_invalid",
                        )
                    )
                    machine_evidence_bytes = machine_evidence_snapshot.raw
                else:
                    machine_evidence_bytes = None
                process_evidence = _load_json_bytes(
                    process_evidence_snapshot.raw,
                    reason="runner_process_evidence_invalid",
                )
                _validate_runner_process_evidence(
                    process_evidence,
                    request_id=request_id,
                    target_issue=target_issue,
                    machine_evidence_path=machine_evidence_path,
                    machine_evidence_bytes=machine_evidence_bytes,
                )
                _require_canonical_evidence_unchanged(
                    process_evidence_path,
                    process_evidence_snapshot,
                    reason="runner_process_evidence_invalid",
                )
                if machine_evidence_snapshot is not None:
                    _require_canonical_evidence_unchanged(
                        machine_evidence_path,
                        machine_evidence_snapshot,
                        reason="runner_process_evidence_invalid",
                    )
            except ValueError:
                return _recovery_block(
                    summary,
                    "runner_process_evidence_invalid",
                )
        if tombstone_store.exists() and not tombstone_store.is_dir():
            return _recovery_block(summary, "replay_tombstone_store_invalid")
        if tombstone_store.is_dir():
            allowed_tombstones = {
                tombstone_path.name,
                _recovery_pending_path(tombstone_path).name,
            }
            try:
                current_request_entries = {
                    entry.name
                    for entry in tombstone_store.iterdir()
                    if entry.name.startswith(tombstone_path.name)
                }
            except OSError:
                return _recovery_block(
                    summary,
                    "replay_tombstone_store_invalid",
                )
            if current_request_entries - allowed_tombstones:
                return _recovery_block(
                    summary,
                    "replay_tombstone_store_invalid",
                )

        try:
            processed = _processed_request_ids(processed_path)
        except (OSError, ValueError, json.JSONDecodeError):
            return _recovery_block(summary, "processed_records_invalid")
        if request_id in processed:
            return _recovery_block(summary, "processed_request_conflict")

        in_flight_exists = in_flight_path.is_file()
        if in_flight_path.exists() and not in_flight_exists:
            return _recovery_block(summary, "in_flight_invalid")
        if not in_flight_exists and not all(
            path.is_file() for path in (original_path, incident_path, tombstone_path)
        ):
            return _recovery_block(
                summary,
                "in_flight_missing_or_recovery_incomplete",
            )
        if in_flight_exists:
            try:
                original_bytes = in_flight_path.read_bytes()
            except OSError:
                return _recovery_block(summary, "in_flight_read_failed")
            observed_sha256 = hashlib.sha256(original_bytes).hexdigest()
            if observed_sha256 != expected_sha256:
                return _recovery_block(summary, "in_flight_sha256_mismatch")
            try:
                _validated_in_flight(
                    original_bytes,
                    request_id=request_id,
                    target_issue=target_issue,
                )
            except ValueError as exc:
                return _recovery_block(summary, str(exc))
        elif original_path.is_file():
            try:
                original_bytes = original_path.read_bytes()
            except OSError:
                return _recovery_block(summary, "original_snapshot_invalid")
            if hashlib.sha256(original_bytes).hexdigest() != expected_sha256:
                return _recovery_block(summary, "original_snapshot_conflict")
            try:
                _validated_in_flight(
                    original_bytes,
                    request_id=request_id,
                    target_issue=target_issue,
                )
            except ValueError:
                return _recovery_block(summary, "original_snapshot_conflict")
        else:
            return _recovery_block(
                summary,
                "in_flight_missing_or_recovery_incomplete",
            )

        if incident_path.exists() and not original_path.exists():
            return _recovery_block(summary, "recovery_partial_state_conflict")
        if tombstone_path.exists() and not incident_path.exists():
            return _recovery_block(summary, "recovery_partial_state_conflict")

        hook("before_original_snapshot")
        try:
            original_preexisting = _promote_recovery_pending(
                original_path,
                expected_bytes=original_bytes,
                conflict_reason="original_snapshot_conflict",
                pending_phase="after_original_pending",
                hook=hook,
            )
            _verify_original_snapshot(
                original_path,
                expected_bytes=original_bytes,
                expected_sha256=expected_sha256,
            )
        except (OSError, ValueError) as exc:
            return _recovery_block(
                summary,
                str(exc)
                if isinstance(exc, ValueError)
                else "original_snapshot_invalid",
            )
        summary["original_evidence_preserved"] = True
        hook("after_original_snapshot")

        incident_preexisting = incident_path.exists()
        if incident_preexisting:
            try:
                incident = _load_exact_record(
                    incident_path,
                    expected_without_timestamp={
                        key: value
                        for key, value in _incident_expected(
                            request_id=request_id,
                            target_issue=target_issue,
                            in_flight_sha256=expected_sha256,
                            in_flight_size=len(original_bytes),
                            observed_request_directory_inventory=(
                                observed_incident_inventory
                            ),
                            recorded_at="unused",
                        ).items()
                        if key != "recorded_at"
                    },
                    invalid_reason="recovery_incident_conflict",
                )
            except ValueError as exc:
                return _recovery_block(summary, str(exc))
            recorded_at = incident["recorded_at"]
        elif _recovery_pending_path(incident_path).exists():
            try:
                incident = _load_exact_record(
                    _recovery_pending_path(incident_path),
                    expected_without_timestamp={
                        key: value
                        for key, value in _incident_expected(
                            request_id=request_id,
                            target_issue=target_issue,
                            in_flight_sha256=expected_sha256,
                            in_flight_size=len(original_bytes),
                            observed_request_directory_inventory=(
                                observed_incident_inventory
                            ),
                            recorded_at="unused",
                        ).items()
                        if key != "recorded_at"
                    },
                    invalid_reason="recovery_incident_conflict",
                )
            except ValueError as exc:
                return _recovery_block(summary, str(exc))
            recorded_at = incident["recorded_at"]
        else:
            recorded_at = now().isoformat()
            if not _supported_timestamp(recorded_at):
                return _recovery_block(summary, "recovery_timestamp_invalid")
            incident = _incident_expected(
                request_id=request_id,
                target_issue=target_issue,
                in_flight_sha256=expected_sha256,
                in_flight_size=len(original_bytes),
                observed_request_directory_inventory=(
                    observed_incident_inventory
                ),
                recorded_at=recorded_at,
            )
        try:
            incident_preexisting = _promote_recovery_pending(
                incident_path,
                expected_bytes=_recovery_json_bytes(incident),
                conflict_reason="recovery_incident_conflict",
                pending_phase="after_incident_pending",
                hook=hook,
            )
        except (OSError, ValueError) as exc:
            return _recovery_block(
                summary,
                str(exc)
                if isinstance(exc, ValueError)
                else "recovery_incident_conflict",
            )
        summary["incident_record"] = (
            "already_present" if incident_preexisting else "written"
        )
        hook("after_incident_record")

        try:
            _prepare_replay_tombstone_store(
                tombstone_store,
                root=root,
                tombstone_path=tombstone_path,
                forbidden_roots=forbidden_state_roots,
                create_directory=create_tombstone_store,
            )
        except ValueError as exc:
            return _recovery_block(summary, str(exc))

        tombstone_preexisting = tombstone_path.exists()
        if tombstone_preexisting:
            try:
                tombstone = _load_exact_record(
                    tombstone_path,
                    expected_without_timestamp={
                        key: value
                        for key, value in _tombstone_expected(
                            request_id=request_id,
                            target_issue=target_issue,
                            in_flight_sha256=expected_sha256,
                            recorded_at="unused",
                        ).items()
                        if key != "recorded_at"
                    },
                    invalid_reason="replay_tombstone_conflict",
                )
            except ValueError as exc:
                return _recovery_block(summary, str(exc))
            if tombstone["recorded_at"] != recorded_at:
                return _recovery_block(summary, "replay_tombstone_conflict")
        else:
            tombstone = _tombstone_expected(
                request_id=request_id,
                target_issue=target_issue,
                in_flight_sha256=expected_sha256,
                recorded_at=recorded_at,
            )
        try:
            if not _recovery_paths_are_safe(
                root=root,
                paths=(
                    tombstone_store,
                    tombstone_path,
                    _recovery_pending_path(tombstone_path),
                ),
                forbidden_roots=forbidden_state_roots,
            ):
                return _recovery_block(summary, "recovery_path_escape")
            tombstone_preexisting = _promote_recovery_pending(
                tombstone_path,
                expected_bytes=_recovery_json_bytes(tombstone),
                conflict_reason="replay_tombstone_conflict",
                pending_phase="after_tombstone_pending",
                hook=hook,
            )
        except (OSError, ValueError) as exc:
            return _recovery_block(
                summary,
                str(exc)
                if isinstance(exc, ValueError)
                else "replay_tombstone_conflict",
            )
        summary["replay_tombstone"] = (
            "already_present" if tombstone_preexisting else "written"
        )
        hook("after_replay_tombstone")

        try:
            _verify_original_snapshot(
                original_path,
                expected_bytes=original_bytes,
                expected_sha256=expected_sha256,
            )
            verified_incident = _load_exact_record(
                incident_path,
                expected_without_timestamp={
                    key: value for key, value in incident.items() if key != "recorded_at"
                },
                invalid_reason="recovery_incident_conflict",
            )
            verified_tombstone = _load_exact_record(
                tombstone_path,
                expected_without_timestamp={
                    key: value
                    for key, value in tombstone.items()
                    if key != "recorded_at"
                },
                invalid_reason="replay_tombstone_conflict",
            )
        except ValueError as exc:
            return _recovery_block(summary, str(exc))
        if (
            verified_incident["recorded_at"] != recorded_at
            or verified_tombstone["recorded_at"] != recorded_at
        ):
            return _recovery_block(summary, "recovery_record_verification_failed")

        if process_evidence_snapshot is not None:
            try:
                _require_canonical_evidence_unchanged(
                    process_evidence_path,
                    process_evidence_snapshot,
                    reason="runner_process_evidence_invalid",
                )
                if machine_evidence_snapshot is not None:
                    _require_canonical_evidence_unchanged(
                        machine_evidence_path,
                        machine_evidence_snapshot,
                        reason="runner_process_evidence_invalid",
                    )
            except ValueError:
                return _recovery_block(
                    summary,
                    "runner_process_evidence_invalid",
                )

        if in_flight_exists:
            try:
                if in_flight_path.read_bytes() != original_bytes:
                    return _recovery_block(summary, "in_flight_changed_during_recovery")
                hook("before_in_flight_release")
                unlink(in_flight_path)
            except OSError:
                return _recovery_block(summary, "in_flight_release_failed")
            if in_flight_path.exists():
                return _recovery_block(summary, "in_flight_release_failed")
            summary["active_in_flight_released"] = True
            hook("after_in_flight_release")
            summary["recovery_status"] = "recovered"
        else:
            summary["active_in_flight_released"] = True
            summary["recovery_status"] = "already_recovered"
        summary["result"] = "success"
        summary["blocked_reasons"] = []
        return summary
    except Exception as exc:
        return _recovery_block(
            summary,
            f"recovery_interrupted:{type(exc).__name__}",
        )
    finally:
        if lock_handle not in {None, -1}:
            os.close(lock_handle)
        lock_path.unlink(missing_ok=True)


def build_verification_argv(
    command: str,
    *,
    python_path: str | Path,
    repo_root: str | Path,
) -> list[str]:
    """Validate one explicit pytest command and bind it to reviewed Python."""
    if (
        not isinstance(command, str)
        or not command.strip()
        or _SHELL_SYNTAX.search(command)
        or _ENV_EXPANSION.search(command)
    ):
        raise ValueError("verification_command_shell_syntax_rejected")
    try:
        parts = shlex.split(command, posix=True)
    except ValueError as exc:
        raise ValueError("verification_command_parse_failed") from exc
    if parts[:3] != ["python", "-m", "pytest"] or len(parts) < 4:
        raise ValueError("verification_command_not_pytest")

    reviewed_python = Path(python_path).resolve()
    target_root = Path(repo_root).resolve()
    if not reviewed_python.is_file():
        raise ValueError("reviewed_python_missing")
    if not target_root.is_dir():
        raise ValueError("target_repository_root_missing")

    selectors: list[str] = []
    index = 3
    while index < len(parts):
        argument = parts[index]
        if argument in _ALLOWED_PYTEST_FLAGS:
            index += 1
            continue
        if argument == "-p":
            if index + 1 >= len(parts) or parts[index + 1] != "no:cacheprovider":
                raise ValueError("verification_command_option_rejected")
            index += 2
            continue
        if argument == "-p=no:cacheprovider":
            index += 1
            continue
        if argument.startswith("-"):
            raise ValueError("verification_command_option_rejected")
        if any(character in argument for character in ("*", "?")):
            raise ValueError("verification_command_wildcard_rejected")
        candidate = argument.split("::", 1)[0]
        if not candidate:
            raise ValueError("verification_command_selector_rejected")
        normalized = candidate.replace("\\", "/")
        posix = PurePosixPath(normalized)
        windows = PureWindowsPath(candidate)
        if (
            posix.is_absolute()
            or windows.is_absolute()
            or ".." in posix.parts
            or (windows.drive and windows.root)
        ):
            raise ValueError("verification_command_path_rejected")
        if not posix.parts or posix.parts[0] != "tests":
            raise ValueError("verification_command_selector_rejected")
        if not (
            normalized == "tests"
            or normalized.endswith(".py")
            or (target_root / Path(*posix.parts)).is_dir()
        ):
            raise ValueError("verification_command_selector_rejected")
        resolved = (target_root / Path(*posix.parts)).resolve()
        try:
            resolved.relative_to(target_root)
        except ValueError as exc:
            raise ValueError("verification_command_path_rejected") from exc
        selectors.append(argument)
        index += 1
    if not selectors:
        raise ValueError("verification_command_selector_required")

    return [str(reviewed_python), "-m", "pytest", *parts[3:]]


def execute_verification_command(
    command: str,
    *,
    python_path: str | Path,
    repo_root: str | Path,
    timeout_seconds: int = VERIFICATION_TIMEOUT_SECONDS,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, str]:
    """Run one parent-controlled pytest command without a shell."""
    argv = build_verification_argv(
        command,
        python_path=python_path,
        repo_root=repo_root,
    )
    try:
        completed = run(
            argv,
            cwd=str(Path(repo_root).resolve()),
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        output = ((completed.stdout or "") + (completed.stderr or ""))[
            -MAX_CAPTURE_CHARS:
        ]
        return {
            "command": command,
            "result": "success" if completed.returncode == 0 else "failed",
            "reason": (
                "exit_code_0"
                if completed.returncode == 0
                else f"exit_code_{completed.returncode}: {output}"
            ),
        }
    except subprocess.TimeoutExpired:
        return {
            "command": command,
            "result": "failed",
            "reason": f"timeout_after_{timeout_seconds}_seconds",
        }


def _read_machine_evidence(
    path: Path,
    *,
    request_id: str,
    target_issue: int,
    target_repo_root: str | Path,
    runtime_contract: dict[str, Any],
) -> dict[str, Any]:
    snapshot = _read_canonical_evidence_snapshot(
        path,
        reason="runner_machine_evidence_unavailable",
    )
    return _validate_machine_evidence_bytes(
        snapshot.raw,
        request_id=request_id,
        target_issue=target_issue,
        target_repo_root=target_repo_root,
        runtime_contract=runtime_contract,
    )


def _validate_machine_evidence_bytes(
    raw: bytes,
    *,
    request_id: str,
    target_issue: int,
    target_repo_root: str | Path,
    runtime_contract: dict[str, Any],
) -> dict[str, Any]:
    try:
        evidence = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("runner_machine_evidence_unavailable") from exc
    if type(evidence) is not dict or set(evidence) != _EVIDENCE_FIELDS:
        raise ValueError("runner_machine_evidence_invalid")
    safety = evidence["safety_flags"]
    binding = evidence["runtime_contract_binding"]
    assurance = evidence["execution_assurance"]
    blocked_reasons = evidence["blocked_reasons"]
    expected_root = os.path.normcase(str(Path(target_repo_root).resolve()))
    observed_root = (
        os.path.normcase(str(Path(evidence["repo_path"]).resolve()))
        if type(evidence["repo_path"]) is str
        else ""
    )
    if (
        evidence["protocol"] != "lawb.display_pilot.runner_machine_evidence.v1"
        or type(evidence["schema_version"]) is not int
        or evidence["schema_version"] != 1
        or type(evidence["request_id"]) is not str
        or evidence["request_id"] != request_id
        or evidence["repository"]
        != "HarryWhite-TW/human-approval-automation-gateway"
        or type(evidence["issue"]) is not int
        or evidence["issue"] != target_issue
        or observed_root != expected_root
        or type(evidence["branch"]) is not str
        or evidence["branch"] != runtime_contract["branch"]
        or type(evidence["head_before"]) is not str
        or re.fullmatch(r"[0-9a-fA-F]{40}", evidence["head_before"]) is None
        or evidence["head_before"].lower() != runtime_contract["expected_head"].lower()
        or type(evidence["head_after"]) is not str
        or re.fullmatch(r"[0-9a-fA-F]{40}", evidence["head_after"]) is None
        or type(evidence["codex_exit_code"]) is not str
        or type(evidence["codex_status"]) is not str
        or evidence["codex_status"] not in {"passed", "failed", "not_run"}
        or type(evidence["codex_timed_out"]) is not bool
        or type(binding) is not dict
        or type(evidence["changed_files"]) is not list
        or type(evidence["final_git_status"]) is not str
        or type(evidence["staged_area_clean"]) is not bool
        or type(assurance) is not dict
        or type(evidence["result_status"]) is not str
        or evidence["result_status"] not in {"success", "blocked"}
        or type(blocked_reasons) is not list
        or any(
            type(value) is not str or not value.strip()
            for value in blocked_reasons
        )
        or type(safety) is not dict
        or set(safety) != set(_REQUIRED_SAFETY_FLAGS)
        or any(type(safety[name]) is not bool for name in _REQUIRED_SAFETY_FLAGS)
        or type(evidence["review_bundle_comment_suppressed"]) is not bool
        or type(evidence["github_comment_posted"]) is not bool
    ):
        raise ValueError("runner_machine_evidence_invalid")
    selected_allowed_files = _canonical_repo_paths(
        runtime_contract.get("allowed_files")
    )
    binding_allowed_files = _canonical_repo_paths(binding.get("allowed_files"))
    actual_changed_files = _canonical_repo_paths(
        binding.get("actual_changed_files"),
        allow_empty=True,
    )
    changed_files = _canonical_repo_paths(
        evidence["changed_files"],
        allow_empty=True,
    )
    required_binding = {
        "status",
        "contract_present",
        "pre_execution",
        "post_execution",
        "allowed_files",
        "actual_changed_files",
        "reasons",
    }
    required_assurance = {
        "governance_scope",
        "observable_evidence",
        "evidence_profile",
        "candidate_manifest_fingerprint",
        "isolation_guarantee",
        "isolation_provider",
        "isolation_evidence_source",
    }
    if (
        set(binding)
        != required_binding
        | ({"runtime_contract"} if binding.get("contract_present") is True else set())
        or type(binding["status"]) is not str
        or type(binding["contract_present"]) is not bool
        or type(binding["pre_execution"]) is not dict
        or type(binding["post_execution"]) is not dict
        or type(binding["allowed_files"]) is not list
        or type(binding["actual_changed_files"]) is not list
        or type(binding["reasons"]) is not list
        or any(type(value) is not str for value in binding["allowed_files"])
        or any(type(value) is not str for value in binding["actual_changed_files"])
        or any(type(value) is not str for value in binding["reasons"])
        or selected_allowed_files is None
        or binding_allowed_files is None
        or actual_changed_files is None
        or changed_files is None
        or binding_allowed_files != selected_allowed_files
        or actual_changed_files != changed_files
        or not _binding_stage_is_valid(binding["pre_execution"])
        or not _binding_stage_is_valid(binding["post_execution"])
        or (
            binding["contract_present"]
            and not _runtime_contract_identity_matches(
                binding["runtime_contract"],
                runtime_contract,
            )
        )
        or (
            binding["status"] == "passed"
            and (
                binding["pre_execution"]["status"] != "passed"
                or binding["post_execution"]["status"] != "passed"
                or binding["pre_execution"]["reasons"]
                or binding["post_execution"]["reasons"]
                or binding["reasons"]
            )
        )
        or not required_assurance <= set(assurance)
        or any(
            assurance[name] is not None and type(assurance[name]) is not str
            for name in required_assurance
        )
        or not _codex_fields_are_consistent(evidence)
    ):
        raise ValueError("runner_machine_evidence_invalid")
    if evidence["result_status"] == "blocked" and not blocked_reasons:
        raise ValueError("runner_machine_evidence_invalid")
    if evidence["result_status"] == "success" and (
        blocked_reasons
        or evidence["codex_timed_out"]
        or evidence["codex_exit_code"] != "0"
        or evidence["codex_status"] != "passed"
        or not evidence["staged_area_clean"]
        or evidence["head_after"].lower() != evidence["head_before"].lower()
        or binding["status"] != "passed"
        or binding["contract_present"] is not True
        or binding["pre_execution"]["status"] != "passed"
        or binding["post_execution"]["status"] != "passed"
        or binding["reasons"]
        or assurance["governance_scope"] != "passed"
        or assurance["observable_evidence"] != "verified"
        or any(path not in selected_allowed_files for path in changed_files)
        or type(runtime_contract.get("max_allowed_files")) is not int
        or type(runtime_contract.get("max_allowed_files")) is bool
        or runtime_contract["max_allowed_files"] <= 0
        or len(changed_files) > runtime_contract["max_allowed_files"]
    ):
        raise ValueError("runner_machine_evidence_invalid")
    evidence["changed_files"] = list(changed_files)
    binding["allowed_files"] = list(binding_allowed_files)
    binding["actual_changed_files"] = list(actual_changed_files)
    if binding.get("contract_present") is True:
        binding["runtime_contract"]["allowed_files"] = list(
            _canonical_repo_paths(
                binding["runtime_contract"]["allowed_files"]
            )
            or ()
        )
    return evidence


def _canonical_repo_paths(
    value: Any,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...] | None:
    if type(value) is not list or (not value and not allow_empty):
        return None
    normalized: list[str] = []
    for path in value:
        try:
            normalized.append(normalize_repo_path(path))
        except ValueError:
            return None
    if len(set(normalized)) != len(normalized):
        return None
    return tuple(sorted(normalized))


def _binding_stage_is_valid(value: dict[str, Any]) -> bool:
    return (
        set(value) == {"status", "reasons"}
        and type(value["status"]) is str
        and value["status"] in {"passed", "contract_violation", "not_run", "not_present"}
        and type(value["reasons"]) is list
        and all(type(reason) is str and reason for reason in value["reasons"])
    )


def _runtime_contract_identity_matches(
    observed: Any,
    expected: dict[str, Any],
) -> bool:
    if type(observed) is not dict:
        return False
    for field in _RUNTIME_CONTRACT_IDENTITY_FIELDS:
        if field == "allowed_files":
            observed_allowed_files = _canonical_repo_paths(observed.get(field))
            expected_allowed_files = _canonical_repo_paths(expected.get(field))
            if (
                observed_allowed_files is None
                or expected_allowed_files is None
                or observed_allowed_files != expected_allowed_files
            ):
                return False
            continue
        if (
            field not in observed
            or field not in expected
            or type(observed[field]) is not type(expected[field])
            or observed[field] != expected[field]
        ):
            return False
    return True


def _codex_fields_are_consistent(evidence: dict[str, Any]) -> bool:
    status = evidence["codex_status"]
    exit_code = evidence["codex_exit_code"]
    numeric_exit = re.fullmatch(r"-?\d+", exit_code)
    if status == "passed":
        return exit_code == "0" and evidence["codex_timed_out"] is False
    if status == "failed":
        return (
            numeric_exit is not None
            and int(exit_code) != 0
        )
    return numeric_exit is None and evidence["codex_timed_out"] is False


def _reconcile_safety_truth(
    evidence: dict[str, Any],
    *,
    runner_invoked: bool,
) -> tuple[dict[str, bool], list[str]]:
    """Merge raw flags with stronger structured or parent-observed true facts."""
    safety = dict(evidence["safety_flags"])
    reasons: list[str] = []
    if runner_invoked:
        if safety["runner_invoked"] is False:
            reasons.append("runner_invocation_fact_mismatch")
        safety["runner_invoked"] = True

    codex_execution_proven = (
        evidence["codex_status"] in {"passed", "failed"}
        or evidence["codex_timed_out"] is True
        or re.fullmatch(r"-?\d+", evidence["codex_exit_code"]) is not None
    )
    if codex_execution_proven:
        if safety["codex_side_action_executed"] is False:
            reasons.append("codex_execution_fact_mismatch")
        safety["codex_side_action_executed"] = True

    if evidence["github_comment_posted"] is True:
        if safety["github_write_performed"] is False:
            reasons.append("github_write_fact_mismatch")
        safety["github_write_performed"] = True

    return safety, list(dict.fromkeys(reasons))


def _execution_consistency_reasons(
    evidence: dict[str, Any],
    safety: dict[str, bool],
    *,
    reconciliation_reasons: list[str],
) -> list[str]:
    reasons: list[str] = []
    reconciled = set(reconciliation_reasons)
    if evidence["result_status"] == "success":
        reasons.extend(
            f"runner_success_safety_contradiction:{name}"
            for name, expected in _SUCCESS_SAFETY_FLAGS.items()
            if safety[name] is not expected
            and not (
                name == "github_write_performed"
                and "github_write_fact_mismatch" in reconciled
            )
        )
        if (
            evidence["review_bundle_comment_suppressed"] is not True
            or evidence["github_comment_posted"] is not False
        ) and "github_write_fact_mismatch" not in reconciled:
            reasons.append("runner_success_comment_contract_contradiction")
    elif (
        evidence["review_bundle_comment_suppressed"] is True
        and evidence["github_comment_posted"] is True
        and "github_write_fact_mismatch" not in reconciled
    ):
        reasons.append("runner_comment_contract_contradiction")
    return list(dict.fromkeys(reasons))


def _canonical_git_observation(value: Any) -> dict[str, Any]:
    required = {
        "head",
        "staged_paths",
        "staged_clean",
        "status_short",
        "effective_changed_paths",
        "fingerprint",
    }
    if (
        type(value) is not dict
        or not required <= set(value)
        or type(value["head"]) is not str
        or type(value["staged_clean"]) is not bool
        or type(value["status_short"]) is not str
        or type(value["fingerprint"]) is not str
    ):
        raise ValueError("parent_verification_git_observation_invalid")
    staged = _canonical_repo_paths(value["staged_paths"], allow_empty=True)
    changed = _canonical_repo_paths(
        value["effective_changed_paths"],
        allow_empty=True,
    )
    if (
        staged is None
        or changed is None
        or value["staged_clean"] is not (not staged)
        or any(path not in changed for path in staged)
    ):
        raise ValueError("parent_verification_git_paths_invalid")
    result = dict(value)
    result["staged_paths"] = list(staged)
    result["effective_changed_paths"] = list(changed)
    return result


def _git(
    root: Path,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={root.as_posix()}",
            "-C",
            str(root),
            *arguments,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        raise ValueError("parent_verification_git_observation_failed")
    return completed


def capture_git_observation(repo_root: str | Path) -> dict[str, Any]:
    """Capture bounded identity and mutation evidence around parent pytest."""
    root = Path(repo_root).resolve()
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    status = _git(root, "status", "--short", "--untracked-files=all").stdout.rstrip()
    staged = _canonical_repo_paths(
        [
            line
            for line in _git(
                root,
                "diff",
                "--cached",
                "--name-only",
            ).stdout.splitlines()
            if line
        ],
        allow_empty=True,
    )
    unstaged = [
        line
        for line in _git(root, "diff", "--name-only").stdout.splitlines()
        if line
    ]
    untracked = [
        line
        for line in _git(
            root,
            "ls-files",
            "--others",
            "--exclude-standard",
        ).stdout.splitlines()
        if line
    ]
    changed = _canonical_repo_paths(
        [*(staged or ()), *unstaged, *untracked],
        allow_empty=True,
    )
    if staged is None or changed is None:
        raise ValueError("parent_verification_git_paths_invalid")
    fingerprint_parts = [
        head,
        status,
        _git(root, "diff", "--binary", "--no-ext-diff").stdout,
        _git(root, "diff", "--cached", "--binary", "--no-ext-diff").stdout,
    ]
    canonical_untracked = _canonical_repo_paths(untracked, allow_empty=True)
    if canonical_untracked is None:
        raise ValueError("parent_verification_git_paths_invalid")
    for relative in canonical_untracked:
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
            digest = (
                hashlib.sha256(path.read_bytes()).hexdigest()
                if path.is_file()
                else "non_regular"
            )
        except (OSError, ValueError):
            digest = "unavailable"
        fingerprint_parts.append(f"{relative}\0{digest}")
    return {
        "head": head,
        "staged_paths": list(staged),
        "staged_clean": not staged,
        "status_short": status,
        "effective_changed_paths": list(changed),
        "fingerprint": hashlib.sha256(
            "\0".join(fingerprint_parts).encode("utf-8")
        ).hexdigest(),
    }


def _path_is_within(path: Path, root: Path) -> bool:
    candidate = os.path.normcase(str(path.resolve()))
    boundary = os.path.normcase(str(root.resolve()))
    try:
        return os.path.commonpath((candidate, boundary)) == boundary
    except ValueError:
        return False


def _write_artifacts(
    request_root: Path,
    *,
    canonical_evidence: dict[str, Any],
    artifacts: dict[str, Any],
    operator_summary: dict[str, Any],
    evidence_guard: _CanonicalEvidenceGuard | None = None,
) -> None:
    required = (
        "result_surface",
        "reviewer_report",
        "plain_language_zh_TW",
    )
    if (
        artifacts.get("result") != "success"
        or type(artifacts.get("result_surface")) is not dict
        or not all(key in artifacts for key in required)
    ):
        raise ValueError(artifacts.get("reason", "hgw_render_failed"))
    if evidence_guard is not None:
        evidence_guard.require_unchanged()
    _atomic_json(request_root / "canonical_evidence.json", canonical_evidence)
    if evidence_guard is not None:
        evidence_guard.require_unchanged()
    _atomic_json(request_root / "result_surface.json", artifacts["result_surface"])
    if evidence_guard is not None:
        evidence_guard.require_unchanged()
    _atomic_text(request_root / "reviewer_report.md", artifacts["reviewer_report"])
    if evidence_guard is not None:
        evidence_guard.require_unchanged()
    _atomic_text(
        request_root / "plain_language_zh_TW.md",
        artifacts["plain_language_zh_TW"],
    )
    if evidence_guard is not None:
        evidence_guard.require_unchanged()
    _atomic_text(
        request_root / "result_comment_candidate.md",
        artifacts["reviewer_report"],
    )
    if evidence_guard is not None:
        evidence_guard.require_unchanged()
    _atomic_json(request_root / "operator_summary.json", operator_summary)
    if evidence_guard is not None:
        evidence_guard.require_unchanged()


def run_foreground(
    *,
    state_root: str | Path,
    target_repo_root: str | Path,
    selector_reader: Callable[[], dict[str, Any] | None],
    target_reader: Callable[[int], dict[str, Any]],
    runner: Callable[
        [dict[str, Any], Path],
        RunnerInvocationResult | int,
    ],
    hgw_renderer: Callable[[dict[str, Any], str, str], dict[str, Any]],
    python_path: str | Path,
    runner_path: str | Path | None = None,
    powershell_path: str | Path | None = None,
    verifier: Callable[..., dict[str, str]] = execute_verification_command,
    git_observer: Callable[[str | Path], dict[str, Any]] = capture_git_observation,
    forbidden_state_roots: tuple[str | Path, ...] = (),
    max_cycles: int = DEFAULT_MAX_CYCLES,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    now: Callable[[], datetime] = _utc_now,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Poll one fixed selector and process at most one explicit request."""
    summary = _summary()
    if type(max_cycles) is not int or max_cycles <= 0:
        return _block(summary, "invalid_max_cycles")
    if poll_interval_seconds < 0:
        return _block(summary, "invalid_poll_interval")

    root = Path(state_root).resolve()
    forbidden_roots = (Path(target_repo_root).resolve(),) + tuple(
        Path(value).resolve() for value in forbidden_state_roots
    )
    if any(_path_is_within(root, forbidden) for forbidden in forbidden_roots):
        return _block(summary, "state_root_inside_git_worktree")
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / "operator.lock"
    lock_handle = _acquire_lock(lock_path)
    if lock_handle is None:
        return _block(summary, "active_lock_present")

    in_flight_path = root / "in_flight.json"
    processed_path = root / "processed_requests.jsonl"
    delegation_started = False
    machine_evidence_guard: _CanonicalEvidenceGuard | None = None
    try:
        os.write(lock_handle, f"pid={os.getpid()}\n".encode("ascii"))
        os.close(lock_handle)
        lock_handle = -1

        if in_flight_path.exists():
            return _block(summary, "unresolved_in_flight_state")
        try:
            processed = _processed_request_ids(processed_path)
        except (OSError, ValueError, json.JSONDecodeError):
            return _block(summary, "processed_records_invalid")

        for cycle in range(1, max_cycles + 1):
            summary["cycles"] = cycle
            _atomic_json(
                root / "heartbeat.json",
                {"cycle": cycle, "at": now().isoformat()},
            )
            if (root / "pause.flag").exists():
                return _block(summary, "pause_flag_present")
            if (root / "stop.flag").exists():
                return _block(summary, "stop_flag_present")

            try:
                selector_issue = selector_reader()
            except Exception:
                return _block(summary, "selector_read_failed")
            if selector_issue is None:
                if cycle < max_cycles:
                    sleep(poll_interval_seconds)
                continue

            selected = parse_selector(
                body=selector_issue.get("body"),
                creator=selector_issue.get("creator"),
                expected_body_sha256=selector_issue.get("body_sha256"),
            )
            if selected["result"] == "idle":
                if cycle < max_cycles:
                    sleep(poll_interval_seconds)
                continue
            if selected["result"] != "success":
                return _block(summary, selected["reason"])
            selector = selected["selector"]
            request_id = selector["request_id"]
            try:
                replay_tombstone = _load_replay_tombstone(
                    root,
                    request_id=request_id,
                    target_issue=selector["target_issue"],
                )
            except ValueError as exc:
                return _block(summary, str(exc))
            if request_id in processed or replay_tombstone is not None:
                if cycle < max_cycles:
                    sleep(poll_interval_seconds)
                continue
            summary["request_id"] = request_id

            try:
                target_issue = target_reader(selector["target_issue"])
            except Exception:
                return _block(summary, "target_read_failed")
            validated = validate_target(selector=selector, issue=target_issue)
            if validated["result"] != "success":
                return _block(summary, validated["reason"])
            runtime_contract = deepcopy(validated["runtime_contract"])
            canonical_allowed_files = _canonical_repo_paths(
                runtime_contract.get("allowed_files")
            )
            if canonical_allowed_files is None:
                return _block(summary, "runtime_contract_allowed_files_invalid")
            runtime_contract["allowed_files"] = list(canonical_allowed_files)

            try:
                for command in runtime_contract["verification_commands"]:
                    build_verification_argv(
                        command,
                        python_path=python_path,
                        repo_root=target_repo_root,
                    )
            except ValueError as exc:
                return _block(summary, str(exc))

            request_root = root / "requests" / request_id
            request_root.mkdir(parents=True, exist_ok=True)
            machine_evidence_path = request_root / "runner_machine_evidence.json"
            process_evidence_path = request_root / "runner_process_evidence.json"
            _atomic_json(
                in_flight_path,
                {
                    "request_id": request_id,
                    "target_issue": selector["target_issue"],
                    "state": "delegating_runner",
                    "at": now().isoformat(),
                },
            )
            delegation_started = True
            if os.path.lexists(process_evidence_path):
                return _block(
                    summary,
                    "runner_process_evidence_write_failed",
                )
            invocation_started_at = now()
            try:
                raw_runner_result = runner(
                    {
                        "selector": selector,
                        "runtime_contract": runtime_contract,
                        "target_issue": target_issue,
                    },
                    machine_evidence_path,
                )
                invocation_finished_at = now()
                runner_result = _normalize_runner_result(
                    raw_runner_result,
                    started_at=invocation_started_at,
                    finished_at=invocation_finished_at,
                )
            except subprocess.TimeoutExpired as exc:
                invocation_finished_at = now()
                stdout = exc.output if type(exc.output) is bytes else b""
                stderr = exc.stderr if type(exc.stderr) is bytes else b""
                runner_result = RunnerInvocationResult(
                    process_started=True,
                    exit_code=None,
                    timed_out=True,
                    launch_exception=None,
                    started_at=invocation_started_at.isoformat(),
                    finished_at=invocation_finished_at.isoformat(),
                    duration_ms=max(
                        0.0,
                        (
                            invocation_finished_at - invocation_started_at
                        ).total_seconds()
                        * 1_000,
                    ),
                    stdout=stdout,
                    stderr=stderr,
                )
            except Exception as exc:
                invocation_finished_at = now()
                runner_result = RunnerInvocationResult(
                    process_started=False,
                    exit_code=None,
                    timed_out=False,
                    launch_exception=_bounded_exception(exc),
                    started_at=invocation_started_at.isoformat(),
                    finished_at=invocation_finished_at.isoformat(),
                    duration_ms=max(
                        0.0,
                        (
                            invocation_finished_at - invocation_started_at
                        ).total_seconds()
                        * 1_000,
                    ),
                    stdout=b"",
                    stderr=b"",
                )
            summary["runner_invoked"] = True
            summary["safety_flags"]["runner_invoked"] = True
            summary["runner_process_started"] = runner_result.process_started
            summary["runner_exit_code"] = runner_result.exit_code
            summary["runner_timed_out"] = runner_result.timed_out
            machine_evidence_guard_error: str | None = None
            if os.path.lexists(machine_evidence_path):
                try:
                    machine_evidence_guard = (
                        _open_canonical_evidence_guard(
                            machine_evidence_path,
                            reason="runner_machine_evidence_invalid",
                        )
                    )
                except ValueError as exc:
                    machine_evidence_guard_error = str(exc)
            machine_evidence_bytes = (
                machine_evidence_guard.raw
                if machine_evidence_guard is not None
                else None
            )
            summary["machine_evidence_observed"] = (
                machine_evidence_bytes is not None
            )
            effective_runner_path = (
                runner_path
                if runner_path is not None
                else Path(target_repo_root) / ".display-pilot-runner-callback"
            )
            effective_powershell_path = (
                powershell_path
                if powershell_path is not None
                else Path(target_repo_root)
                / ".display-pilot-powershell-callback"
            )
            process_evidence = _process_evidence_value(
                request_id=request_id,
                target_issue=selector["target_issue"],
                target_repo_root=target_repo_root,
                runner_path=effective_runner_path,
                powershell_path=effective_powershell_path,
                machine_evidence_path=machine_evidence_path,
                machine_evidence_bytes=machine_evidence_bytes,
                result=runner_result,
                prepared_at=now().isoformat(),
            )
            try:
                _write_runner_process_evidence(
                    process_evidence_path,
                    process_evidence,
                    validation={
                        "request_id": request_id,
                        "target_issue": selector["target_issue"],
                        "target_repo_root": target_repo_root,
                        "runner_path": effective_runner_path,
                        "powershell_path": effective_powershell_path,
                        "machine_evidence_path": machine_evidence_path,
                        "stdout": runner_result.stdout,
                        "stderr": runner_result.stderr,
                        "machine_evidence_bytes": machine_evidence_bytes,
                    },
                )
            except (OSError, ValueError):
                return _block(
                    summary,
                    "runner_process_evidence_write_failed",
                )
            summary["runner_process_evidence_written"] = True
            if machine_evidence_guard is not None:
                try:
                    machine_evidence_guard.require_unchanged()
                except ValueError as exc:
                    return _block(summary, str(exc))

            if runner_result.process_started is False:
                return _block(summary, "runner_process_launch_failed")
            if runner_result.timed_out:
                return _block(summary, "runner_timeout")
            if machine_evidence_guard_error is not None:
                return _block(summary, machine_evidence_guard_error)
            if machine_evidence_bytes is None:
                return _block(
                    summary,
                    (
                        "runner_machine_evidence_missing"
                        if runner_result.exit_code == 0
                        else "runner_nonzero_exit_without_machine_evidence"
                    ),
                )
            try:
                machine_evidence_guard.require_unchanged()
                machine_evidence = _validate_machine_evidence_bytes(
                    machine_evidence_guard.raw,
                    request_id=request_id,
                    target_issue=selector["target_issue"],
                    target_repo_root=target_repo_root,
                    runtime_contract=runtime_contract,
                )
            except ValueError as exc:
                return _block(summary, str(exc))
            runner_exit_code = runner_result.exit_code

            blocked_reasons = list(machine_evidence.get("blocked_reasons") or [])
            safety, reconciliation_reasons = _reconcile_safety_truth(
                machine_evidence,
                runner_invoked=summary["runner_invoked"],
            )
            machine_evidence["safety_flags"] = safety
            blocked_reasons.extend(reconciliation_reasons)
            blocked_reasons.extend(
                _execution_consistency_reasons(
                    machine_evidence,
                    safety,
                    reconciliation_reasons=reconciliation_reasons,
                )
            )
            forbidden_true = {
                flag
                for flag in _FORBIDDEN_SIDE_EFFECT_FLAGS
                if safety.get(flag) is not False
            }
            if (
                forbidden_true - {"github_write_performed"}
                or (
                    "github_write_performed" in forbidden_true
                    and "github_write_fact_mismatch" not in reconciliation_reasons
                )
            ):
                blocked_reasons.append("runner_reported_forbidden_side_effect")
            if any(
                safety[flag] is True
                for flag in (
                    "dispatcher_invoked",
                    "watcher_invoked",
                    "broad_scan_performed",
                )
            ):
                blocked_reasons.append("runner_reported_unexpected_execution")

            verification: list[dict[str, str]] = []
            verification_git: dict[str, Any] | None = None
            if (
                runner_exit_code == 0
                and machine_evidence["result_status"] == "success"
                and not blocked_reasons
            ):
                handoff_reasons: list[str] = []
                try:
                    handoff_observation = _canonical_git_observation(
                        git_observer(target_repo_root)
                    )
                except ValueError:
                    handoff_observation = None
                    handoff_reasons.append(
                        "runner_parent_handoff_paths_invalid"
                    )
                if handoff_observation is not None:
                    if (
                        handoff_observation["head"].lower()
                        != machine_evidence["head_after"].lower()
                    ):
                        handoff_reasons.append(
                            "runner_parent_handoff_head_mismatch"
                        )
                    if (
                        handoff_observation["staged_clean"]
                        is not machine_evidence["staged_area_clean"]
                    ):
                        handoff_reasons.append(
                            "runner_parent_handoff_staged_mismatch"
                        )
                    if (
                        handoff_observation["effective_changed_paths"]
                        != machine_evidence["changed_files"]
                    ):
                        handoff_reasons.append(
                            "runner_parent_handoff_changed_files_mismatch"
                        )
                verification_git = {
                    "runner_parent_handoff": {
                        "machine_evidence": {
                            "head_after": machine_evidence["head_after"],
                            "staged_area_clean": machine_evidence[
                                "staged_area_clean"
                            ],
                            "changed_files": machine_evidence["changed_files"],
                        },
                        "parent_observation": handoff_observation,
                        "reasons": handoff_reasons,
                    },
                    "before": None,
                    "after": None,
                    "mutation_reasons": [],
                }
                if handoff_reasons:
                    blocked_reasons.extend(handoff_reasons)
                else:
                    summary["verification_invoked"] = True
                    before_verification = handoff_observation
                    for command in runtime_contract["verification_commands"]:
                        verification.append(
                            verifier(
                                command,
                                python_path=python_path,
                                repo_root=target_repo_root,
                            )
                        )
                    mutation_reasons: list[str] = []
                    try:
                        after_verification = _canonical_git_observation(
                            git_observer(target_repo_root)
                        )
                    except ValueError:
                        after_verification = None
                        mutation_reasons.append(
                            "parent_verification_paths_invalid"
                        )
                    if after_verification is not None:
                        if (
                            before_verification["head"].lower()
                            != after_verification["head"].lower()
                        ):
                            mutation_reasons.append(
                                "parent_verification_head_changed"
                            )
                        if (
                            not before_verification["staged_clean"]
                            or not after_verification["staged_clean"]
                        ):
                            mutation_reasons.append(
                                "parent_verification_staged_changes_detected"
                            )
                        allowed_files = set(canonical_allowed_files)
                        if any(
                            path not in allowed_files
                            for path in after_verification[
                                "effective_changed_paths"
                            ]
                        ):
                            mutation_reasons.append(
                                "parent_verification_changed_file_outside_allowed_files"
                            )
                        if (
                            before_verification["fingerprint"]
                            != after_verification["fingerprint"]
                        ):
                            mutation_reasons.append(
                                "parent_verification_repository_mutation"
                            )
                    verification_git["before"] = before_verification
                    verification_git["after"] = after_verification
                    verification_git["mutation_reasons"] = list(
                        dict.fromkeys(mutation_reasons)
                    )
                    if any(
                        record.get("result") != "success"
                        for record in verification
                    ):
                        blocked_reasons.append("parent_verification_failed")
                    blocked_reasons.extend(mutation_reasons)
            elif (
                runner_exit_code != 0
                or machine_evidence["result_status"] != "success"
            ):
                blocked_reasons.append("runner_blocked")

            try:
                machine_evidence_guard.require_unchanged()
            except ValueError as exc:
                return _block(summary, str(exc))

            result = "blocked" if blocked_reasons else "success"
            created_at = now().isoformat()
            canonical_evidence = {
                "protocol": EVIDENCE_PROTOCOL,
                "request_id": request_id,
                "selector": selector,
                "transport_validation": validated["validation_summary"],
                "runtime_contract": runtime_contract,
                "runner_machine_evidence": machine_evidence,
                "verification": verification,
                "verification_git_observation": verification_git,
                "result": result,
                "changed_files": list(machine_evidence.get("changed_files") or []),
                "blocked_reasons": list(dict.fromkeys(blocked_reasons)),
                "safety_flags": safety,
                "created_at": created_at,
            }
            try:
                machine_evidence_guard.require_unchanged()
            except ValueError as exc:
                return _block(summary, str(exc))
            artifacts = hgw_renderer(
                canonical_evidence,
                request_id,
                created_at,
            )
            try:
                machine_evidence_guard.require_unchanged()
            except ValueError as exc:
                return _block(summary, str(exc))
            summary["result"] = result
            summary["blocked_reasons"] = canonical_evidence["blocked_reasons"]
            summary["request_processed"] = True
            summary["changed_files"] = canonical_evidence["changed_files"]
            summary["result_comment_candidate_count"] = 1
            summary["safety_flags"] = safety
            for name, value in safety.items():
                if name in summary:
                    summary[name] = value
            try:
                machine_evidence_guard.require_unchanged()
            except ValueError as exc:
                return _block(summary, str(exc))
            _write_artifacts(
                request_root,
                canonical_evidence=canonical_evidence,
                artifacts=artifacts,
                operator_summary=summary,
                evidence_guard=machine_evidence_guard,
            )
            try:
                machine_evidence_guard.require_unchanged()
            except ValueError as exc:
                return _block(summary, str(exc))
            processed_append = _append_processed(
                processed_path,
                {
                    "request_id": request_id,
                    "result": result,
                    "processed_at": created_at,
                },
                evidence_guard=machine_evidence_guard,
            )
            try:
                machine_evidence_guard.require_unchanged()
                _release_in_flight(
                    in_flight_path,
                    evidence_guard=machine_evidence_guard,
                )
                machine_evidence_guard.require_unchanged()
            except (OSError, ValueError):
                _rollback_processed_append(processed_append)
                raise
            delegation_started = False
            return summary

        summary["polling_outcome"] = "no_eligible_request"
        return summary
    except Exception as exc:
        reason = (
            "runner_execution_uncertain"
            if delegation_started
            else f"operator_failed:{type(exc).__name__}"
        )
        return _block(summary, reason)
    finally:
        if machine_evidence_guard is not None:
            machine_evidence_guard.close()
        if lock_handle not in {None, -1}:
            os.close(lock_handle)
        lock_path.unlink(missing_ok=True)

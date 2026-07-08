"""Minimal local evidence collector for OPT-02."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import uuid


SESSION_SCHEMA_VERSION = "lawb.minimal_evidence_collector.session.v0.1"
COMMAND_RESULT_SCHEMA_VERSION = "lawb.minimal_evidence_collector.command_result.v0.1"
REVIEW_PACKET_SCHEMA_VERSION = "lawb.minimal_evidence_collector.review_packet.v0.1"

SUPPORTED_PROFILES = {"docs", "code"}
FORBIDDEN_COMMAND_WORDS = {
    "push",
    "commit",
    "merge",
    "reset",
    "clean",
    "checkout",
    "switch",
    "branch",
    "tag",
    "gh",
    "codex",
    "runner",
    "dispatcher",
    "poll",
    "auth",
    "token",
    "install",
    "pip",
    "npm",
}
SEMANTIC_APPROVAL_FIELDS = {"accepted", "approved", "done"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_safety() -> dict[str, bool]:
    return {
        "github_write_performed": False,
        "git_write_performed": False,
        "issue_write_performed": False,
        "bridge_invoked": False,
        "dispatcher_invoked": False,
        "runner_invoked": False,
        "codex_invoked": False,
        "dependency_install_performed": False,
        "config_modified": False,
        "path_modified": False,
    }


@dataclass(frozen=True)
class CollectorError(Exception):
    reason: str

    def __str__(self) -> str:
        return self.reason


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CollectorError("session_read_failed") from exc
    if not isinstance(payload, dict):
        raise CollectorError("session_invalid")
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_name(command_id: str, index: int) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", command_id).strip(".-")
    if not safe:
        safe = "command"
    return f"{index:03d}-{safe}"


def _command_words(argv: list[str]) -> set[str]:
    words: set[str] = set()
    for item in argv:
        lower = item.lower()
        words.add(lower)
        candidates = {lower}
        leaf = Path(lower).name
        if leaf:
            candidates.add(leaf)
            candidates.add(Path(leaf).stem)
        for candidate in candidates:
            words.add(candidate)
            for token in re.split(r"[^a-z0-9_-]+", candidate):
                if token:
                    words.add(token)
    return words


def find_forbidden_command_words(argv: list[str]) -> list[str]:
    return sorted(FORBIDDEN_COMMAND_WORDS.intersection(_command_words(argv)))


def begin_session(
    *,
    repo_root: Path,
    evidence_root: Path,
    profile: str,
    label: str | None,
) -> Path:
    if profile not in SUPPORTED_PROFILES:
        raise CollectorError("unsupported_profile")

    repo_root = repo_root.resolve()
    evidence_root = evidence_root.resolve()
    evidence_root.mkdir(parents=True, exist_ok=True)

    session = {
        "schema_version": SESSION_SCHEMA_VERSION,
        "session_id": str(uuid.uuid4()),
        "created_at": utc_now(),
        "repo_root": str(repo_root),
        "evidence_root": str(evidence_root),
        "profile": profile,
        "label": label,
        "commands": [],
        "safety": default_safety(),
    }
    session_path = evidence_root / "session.json"
    _write_json(session_path, session)
    return session_path


def run_command(*, session_path: Path, command_id: str, argv: list[str]) -> dict[str, object]:
    if not argv:
        raise CollectorError("missing_argv")
    forbidden = find_forbidden_command_words(argv)
    if forbidden:
        raise CollectorError("forbidden_command:" + ",".join(forbidden))

    session = _read_json(session_path)
    repo_root = Path(str(session.get("repo_root", "")))
    evidence_root = Path(str(session.get("evidence_root", "")))
    commands = session.get("commands")
    if not isinstance(commands, list):
        raise CollectorError("session_commands_invalid")

    command_dir = evidence_root / "commands" / _artifact_name(command_id, len(commands) + 1)
    command_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = command_dir / "stdout.txt"
    stderr_path = command_dir / "stderr.txt"

    started_at = utc_now()
    started = time.perf_counter()
    killed = False
    timed_out = False
    exit_code = 0

    with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
        try:
            completed = subprocess.run(
                argv,
                cwd=str(repo_root),
                stdout=stdout_handle,
                stderr=stderr_handle,
                shell=False,
                check=False,
            )
            exit_code = int(completed.returncode)
        except OSError as exc:
            exit_code = 127
            stderr_handle.write(str(exc).encode("utf-8", errors="replace"))

    duration_ms = int(round((time.perf_counter() - started) * 1000))
    ended_at = utc_now()

    result = {
        "schema_version": COMMAND_RESULT_SCHEMA_VERSION,
        "command_id": command_id,
        "argv": list(argv),
        "cwd": str(repo_root),
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_ms": duration_ms,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "killed": killed,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "stdout_bytes": stdout_path.stat().st_size,
        "stderr_bytes": stderr_path.stat().st_size,
        "stdout_sha256": _sha256_file(stdout_path),
        "stderr_sha256": _sha256_file(stderr_path),
        "decoding": {
            "stdout": "captured_bytes_no_decoding",
            "stderr": "captured_bytes_no_decoding",
        },
    }
    commands.append(result)
    _write_json(session_path, session)
    return result


def finalize_session(*, session_path: Path) -> Path:
    session = _read_json(session_path)
    commands = session.get("commands")
    if not isinstance(commands, list):
        raise CollectorError("session_commands_invalid")

    failed_count = sum(
        1 for command in commands
        if isinstance(command, dict) and int(command.get("exit_code", 1)) != 0
    )
    result = "success" if failed_count == 0 else "command_failed"
    evidence_root = Path(str(session.get("evidence_root", "")))

    review_packet = {
        "schema_version": REVIEW_PACKET_SCHEMA_VERSION,
        "session_id": session.get("session_id"),
        "result": result,
        "profile": session.get("profile"),
        "label": session.get("label"),
        "repo_root": session.get("repo_root"),
        "evidence_root": session.get("evidence_root"),
        "command_count": len(commands),
        "failed_command_count": failed_count,
        "commands": commands,
        "safety": session.get("safety", default_safety()),
        "created_at": session.get("created_at"),
        "finalized_at": utc_now(),
    }
    for field in SEMANTIC_APPROVAL_FIELDS:
        review_packet.pop(field, None)

    review_packet_path = evidence_root / "review_packet.json"
    _write_json(review_packet_path, review_packet)
    return review_packet_path


def compact_review_summary(review_packet_path: Path) -> dict[str, object]:
    review_packet = _read_json(review_packet_path)
    return {
        "schema_version": "lawb.minimal_evidence_collector.summary.v0.1",
        "session_id": review_packet.get("session_id"),
        "result": review_packet.get("result"),
        "profile": review_packet.get("profile"),
        "label": review_packet.get("label"),
        "evidence_root": review_packet.get("evidence_root"),
        "review_packet_path": str(review_packet_path),
        "command_count": review_packet.get("command_count"),
        "failed_command_count": review_packet.get("failed_command_count"),
        "safety": review_packet.get("safety", default_safety()),
    }

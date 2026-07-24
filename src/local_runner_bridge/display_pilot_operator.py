"""Bounded, foreground-only Display Pilot operator candidate."""

from __future__ import annotations

import json
import hashlib
import os
import re
import shlex
import subprocess
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable

from .display_pilot_transport import parse_selector, validate_target
from .runtime_contract_binding import normalize_repo_path


SUMMARY_PROTOCOL = "hgw.display_pilot.operator.v1"
EVIDENCE_PROTOCOL = "hgw.display_pilot.canonical_evidence.v1"
DEFAULT_MAX_CYCLES = 100
DEFAULT_POLL_INTERVAL_SECONDS = 5.0
MAX_CAPTURE_CHARS = 12_000
VERIFICATION_TIMEOUT_SECONDS = 600

_SHELL_SYNTAX = re.compile(r"[|;&><`$()\r\n]")
_ENV_EXPANSION = re.compile(r"%[^%]+%")
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


def _summary() -> dict[str, Any]:
    return {
        "protocol": SUMMARY_PROTOCOL,
        "result": "success",
        "blocked_reasons": [],
        "cycles": 0,
        "request_processed": False,
        "runner_invoked": False,
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


def _append_processed(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


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
    try:
        evidence = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
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
    _atomic_json(request_root / "canonical_evidence.json", canonical_evidence)
    _atomic_json(request_root / "result_surface.json", artifacts["result_surface"])
    _atomic_text(request_root / "reviewer_report.md", artifacts["reviewer_report"])
    _atomic_text(
        request_root / "plain_language_zh_TW.md",
        artifacts["plain_language_zh_TW"],
    )
    _atomic_text(
        request_root / "result_comment_candidate.md",
        artifacts["reviewer_report"],
    )
    _atomic_json(request_root / "operator_summary.json", operator_summary)


def run_foreground(
    *,
    state_root: str | Path,
    target_repo_root: str | Path,
    selector_reader: Callable[[], dict[str, Any] | None],
    target_reader: Callable[[int], dict[str, Any]],
    runner: Callable[[dict[str, Any], Path], int],
    hgw_renderer: Callable[[dict[str, Any], str, str], dict[str, Any]],
    python_path: str | Path,
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
            if request_id in processed:
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
            try:
                runner_exit_code = runner(
                    {
                        "selector": selector,
                        "runtime_contract": runtime_contract,
                        "target_issue": target_issue,
                    },
                    machine_evidence_path,
                )
            except subprocess.TimeoutExpired:
                summary["runner_invoked"] = True
                summary["safety_flags"]["runner_invoked"] = True
                return _block(summary, "runner_timeout")
            summary["runner_invoked"] = True
            summary["safety_flags"]["runner_invoked"] = True
            machine_evidence = _read_machine_evidence(
                machine_evidence_path,
                request_id=request_id,
                target_issue=selector["target_issue"],
                target_repo_root=target_repo_root,
                runtime_contract=runtime_contract,
            )

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
            artifacts = hgw_renderer(
                canonical_evidence,
                request_id,
                created_at,
            )
            summary["result"] = result
            summary["blocked_reasons"] = canonical_evidence["blocked_reasons"]
            summary["request_processed"] = True
            summary["changed_files"] = canonical_evidence["changed_files"]
            summary["result_comment_candidate_count"] = 1
            summary["safety_flags"] = safety
            for name, value in safety.items():
                if name in summary:
                    summary[name] = value
            _write_artifacts(
                request_root,
                canonical_evidence=canonical_evidence,
                artifacts=artifacts,
                operator_summary=summary,
            )
            _append_processed(
                processed_path,
                {
                    "request_id": request_id,
                    "result": result,
                    "processed_at": created_at,
                },
            )
            in_flight_path.unlink()
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
        if lock_handle not in {None, -1}:
            os.close(lock_handle)
        lock_path.unlink(missing_ok=True)

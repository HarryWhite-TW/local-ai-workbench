"""Read-only RV2-03 Phase A host check harness."""

from __future__ import annotations

import argparse
import json
import ntpath
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit, urlunsplit

PROTOCOL = "lawb.rv2_03_host_check.v1"
READY = "READY"
ATTENTION = "ATTENTION"
BLOCKED = "BLOCKED"

BLOCKING_REASONS = (
    "repo_root_invalid",
    "origin_url_unavailable",
    "branch_unavailable",
    "head_unavailable",
    "working_tree_status_unavailable",
    "final_working_tree_status_unavailable",
    "repository_mismatch",
    "branch_mismatch",
    "head_mismatch",
    "upstream_missing",
    "upstream_head_mismatch",
    "working_tree_dirty",
    "working_tree_changed_during_check",
    "git_identity_missing",
    "reviewed_python_missing",
    "python_version_probe_failed",
    "required_imports_failed",
    "reviewed_gh_missing",
    "gh_version_probe_failed",
    "gh_auth_failed",
    "gh_repository_read_failed",
    "gh_repository_mismatch",
    "reviewed_codex_missing",
    "codex_unsafe_launcher",
    "codex_version_probe_failed",
    "manifest_unreadable",
    "manifest_invalid",
)

ATTENTION_REASONS = (
    "path_python_differs_from_reviewed_python",
    "path_gh_differs_from_reviewed_gh",
    "path_codex_differs_from_reviewed_codex",
    "fresh_shell_python_differs_from_reviewed_python",
    "fresh_shell_gh_differs_from_reviewed_gh",
    "fresh_shell_codex_differs_from_reviewed_codex",
    "operational_venv_differs_from_manifest",
    "manifest_venv_not_gitignored",
    "codex_version_differs_from_manifest",
    "path_resolution_differs_from_reviewed_path",
    "fresh_shell_resolution_differs_from_reviewed_path",
)

REQUIRED_IMPORTS = (
    "fastapi",
    "pydantic",
    "httpx",
    "pytest",
    "pypdf",
    "docx",
    "local_runner_bridge.bridge_diagnostics",
)

SAFE_WINDOWS_SUFFIXES = (".exe", ".cmd", ".bat", ".com")
UNSAFE_SUFFIXES = (".ps1", ".sh")

CommandRunner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]
FreshShellRunner = Callable[[str, Path], str | None]


def run_host_check(
    *,
    repo_root: str | Path,
    expected_repository: str,
    expected_branch: str,
    expected_head: str,
    reviewed_python_path: str | Path,
    reviewed_gh_path: str | Path,
    reviewed_codex_path: str | Path,
    command_runner: CommandRunner | None = None,
    fresh_shell_runner: FreshShellRunner | None = None,
    environment: Mapping[str, str] | None = None,
    interactive_host_gh_auth_verified: bool | None = None,
) -> dict[str, Any]:
    """Inspect the current host without writing, installing, or repairing."""
    root = Path(repo_root).resolve()
    env = dict(os.environ if environment is None else environment)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    runner = command_runner or (lambda command, cwd: _run_command(command, cwd, env))
    fresh_runner = fresh_shell_runner or (lambda name, cwd: _fresh_shell_resolve(name, cwd, env))

    reasons: list[str] = []
    read_errors: list[dict[str, Any]] = []
    before_status = _git(root, runner, "status", "--porcelain")

    repository = _inspect_repository(
        root,
        runner,
        expected_repository,
        expected_branch,
        expected_head,
        before_status,
        read_errors,
        reasons,
    )
    python = _inspect_python(
        root,
        runner,
        reviewed_python_path,
        env,
        reasons,
    )
    fresh_shell = _inspect_fresh_shell(
        root,
        fresh_runner,
        reviewed_python_path,
        reviewed_gh_path,
        reviewed_codex_path,
        env,
        reasons,
    )
    github_cli = _inspect_gh(
        root,
        runner,
        reviewed_gh_path,
        expected_repository,
        fresh_shell,
        interactive_host_gh_auth_verified,
        env,
        reasons,
    )
    codex_cli = _inspect_codex(
        root,
        runner,
        reviewed_codex_path,
        fresh_shell,
        None,
        env,
        reasons,
    )
    bootstrap_contract = _inspect_bootstrap_contract(
        root,
        reviewed_python_path,
        github_cli,
        codex_cli,
        fresh_shell,
        reasons,
    )
    codex_cli["manifest_expected_version"] = bootstrap_contract["manifest_codex_version"]
    codex_cli["version_matches_manifest"] = bootstrap_contract["codex_version_matches_manifest"]

    after_status = _git(root, runner, "status", "--porcelain")
    repository["working_tree_clean_after"] = after_status["stdout"] == "" if after_status["ok"] else None
    if not after_status["ok"]:
        _add_reason(reasons, "final_working_tree_status_unavailable")
        repository["read_errors"].append(_failure("working_tree_after", after_status))
    repository["working_tree_unchanged"] = (
        before_status["ok"]
        and after_status["ok"]
        and before_status.get("stdout") == after_status.get("stdout")
    )
    repository["repository_integrity_verified"] = bool(repository["working_tree_unchanged"])
    if not repository["working_tree_unchanged"] and before_status["ok"] and after_status["ok"]:
        _add_reason(reasons, "working_tree_changed_during_check")

    safety = _safety(repository_modified_by_check=not repository["repository_integrity_verified"])
    status, ordered_reasons, operational = _status(reasons)
    return {
        "protocol": PROTOCOL,
        "status": status,
        "status_reasons": ordered_reasons,
        "operational_readiness": operational,
        "repository": repository,
        "python": python,
        "github_cli": github_cli,
        "codex_cli": codex_cli,
        "fresh_shell": fresh_shell,
        "bootstrap_contract": bootstrap_contract,
        "safety": safety,
    }


def _inspect_repository(
    root: Path,
    runner: CommandRunner,
    expected_repository: str,
    expected_branch: str,
    expected_head: str,
    before_status: dict[str, Any],
    read_errors: list[dict[str, Any]],
    reasons: list[str],
) -> dict[str, Any]:
    git_present = (root / ".git").exists()
    if not git_present:
        _add_reason(reasons, "repo_root_invalid")

    origin = _git(root, runner, "config", "--get", "remote.origin.url")
    branch = _git(root, runner, "rev-parse", "--abbrev-ref", "HEAD")
    head = _git(root, runner, "rev-parse", "HEAD")
    upstream = _git(root, runner, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    upstream_head = _git(root, runner, "rev-parse", "--verify", "@{u}")
    user_name = _git(root, runner, "config", "--local", "--get", "user.name")
    user_email = _git(root, runner, "config", "--local", "--get", "user.email")

    for stage, result in (
        ("origin_url", origin),
        ("current_branch", branch),
        ("head", head),
        ("working_tree_before", before_status),
    ):
        if not result["ok"]:
            read_errors.append(_failure(stage, result))

    if not origin["ok"]:
        _add_reason(reasons, "origin_url_unavailable")
    if not branch["ok"]:
        _add_reason(reasons, "branch_unavailable")
    if not head["ok"]:
        _add_reason(reasons, "head_unavailable")
    if not before_status["ok"]:
        _add_reason(reasons, "working_tree_status_unavailable")

    origin_repo = _normalize_repo(origin["stdout"])
    repository_matches = origin_repo == expected_repository.lower()
    branch_matches = branch["stdout"] == expected_branch
    head_matches = head["stdout"] == expected_head
    upstream_head_matches = upstream_head["stdout"] == expected_head
    clean_before = before_status["stdout"] == "" if before_status["ok"] else None
    git_identity_ready = bool(user_name["stdout"] and user_email["stdout"])

    if origin["ok"] and not repository_matches:
        _add_reason(reasons, "repository_mismatch")
    if branch["ok"] and not branch_matches:
        _add_reason(reasons, "branch_mismatch")
    if head["ok"] and not head_matches:
        _add_reason(reasons, "head_mismatch")
    if not upstream["ok"] or not upstream["stdout"]:
        _add_reason(reasons, "upstream_missing")
    elif not upstream_head_matches:
        _add_reason(reasons, "upstream_head_mismatch")
    if clean_before is False:
        _add_reason(reasons, "working_tree_dirty")
    if not git_identity_ready:
        _add_reason(reasons, "git_identity_missing")

    return {
        "repo_root": str(root),
        "git_directory_present": git_present,
        "origin_url": _sanitize_origin_url(origin["stdout"]),
        "origin_url_sanitized": True,
        "expected_repository": expected_repository,
        "repository_matches": repository_matches,
        "current_branch": branch["stdout"],
        "expected_branch": expected_branch,
        "branch_matches": branch_matches,
        "head": head["stdout"],
        "expected_head": expected_head,
        "head_matches": head_matches,
        "upstream": upstream["stdout"],
        "upstream_head": upstream_head["stdout"],
        "upstream_matches_head": upstream_head_matches,
        "working_tree_clean_before": clean_before,
        "working_tree_clean_after": None,
        "working_tree_unchanged": None,
        "repository_integrity_verified": False,
        "git_user_name_present": bool(user_name["stdout"]),
        "git_user_email_present": bool(user_email["stdout"]),
        "git_identity_ready": git_identity_ready,
        "read_errors": read_errors,
    }


def _inspect_python(
    root: Path,
    runner: CommandRunner,
    reviewed_python_path: str | Path,
    env: Mapping[str, str],
    reasons: list[str],
) -> dict[str, Any]:
    reviewed = Path(reviewed_python_path)
    reviewed_exists = reviewed.is_file()
    active = Path(sys.executable).resolve()
    path_python = _which("python.exe", env) or _which("python", env)
    if not reviewed_exists:
        _add_reason(reasons, "reviewed_python_missing")
    if not _same_path(path_python, str(reviewed)):
        _add_reason(reasons, "path_python_differs_from_reviewed_python")

    version = _run_capture(runner, _launcher_command(reviewed, ["--version"], env), root)
    pip = _run_capture(runner, _launcher_command(reviewed, ["-m", "pip", "--version"], env), root)
    pytest = _run_capture(runner, _launcher_command(reviewed, ["-m", "pytest", "--version"], env), root)
    imports = _run_capture(
        runner,
        _launcher_command(reviewed, ["-c", _import_probe_code()], env),
        root,
    )

    if reviewed_exists and version["exit_code"] != 0:
        _add_reason(reasons, "python_version_probe_failed")
    failures = _parse_import_failures(imports["stdout"])
    if reviewed_exists and imports["exit_code"] != 0:
        _add_reason(reasons, "required_imports_failed")

    return {
        "active_python_path": str(active),
        "reviewed_python_path": str(reviewed),
        "path_resolved_path": path_python,
        "reviewed_python_exists": reviewed_exists,
        "active_python_matches_reviewed": _same_path(str(active), str(reviewed)),
        "python_version": _first_line(version["stdout"]),
        "pip_available": pip["exit_code"] == 0,
        "pip_version": _first_line(pip["stdout"]),
        "pytest_available": pytest["exit_code"] == 0,
        "pytest_version": _first_line(pytest["stdout"]),
        "required_imports_ready": imports["exit_code"] == 0,
        "required_import_failures": failures,
        "probes": {
            "python_version": _probe("python_version", version),
            "python_pip": _probe("python_pip", pip),
            "python_pytest": _probe("python_pytest", pytest),
            "python_imports": _probe("python_imports", imports),
        },
    }


def _inspect_fresh_shell(
    root: Path,
    fresh_runner: FreshShellRunner,
    reviewed_python_path: str | Path,
    reviewed_gh_path: str | Path,
    reviewed_codex_path: str | Path,
    env: Mapping[str, str],
    reasons: list[str],
) -> dict[str, Any]:
    specs = {
        "python.exe": reviewed_python_path,
        "gh.exe": reviewed_gh_path,
        "codex.cmd": reviewed_codex_path,
    }
    result: dict[str, Any] = {}
    for name, reviewed in specs.items():
        current = _which(name, env)
        fresh = fresh_runner(name, root)
        current_matches = _same_path(current, str(reviewed))
        fresh_matches = _same_path(fresh, str(reviewed))
        key = name.split(".")[0]
        result[key] = {
            "current_process_resolved_path": current,
            "fresh_shell_resolved_path": fresh,
            "reviewed_path": str(reviewed),
            "current_matches_reviewed": current_matches,
            "fresh_shell_matches_reviewed": fresh_matches,
        }
        if not current_matches:
            _add_reason(reasons, f"path_{key}_differs_from_reviewed_{key}")
            _add_reason(reasons, "path_resolution_differs_from_reviewed_path")
        if not fresh_matches:
            _add_reason(reasons, f"fresh_shell_{key}_differs_from_reviewed_{key}")
            _add_reason(reasons, "fresh_shell_resolution_differs_from_reviewed_path")
    return result


def _inspect_gh(
    root: Path,
    runner: CommandRunner,
    reviewed_gh_path: str | Path,
    expected_repository: str,
    fresh_shell: dict[str, Any],
    interactive_host_gh_auth_verified: bool | None,
    env: Mapping[str, str],
    reasons: list[str],
) -> dict[str, Any]:
    reviewed = Path(reviewed_gh_path)
    exists = reviewed.is_file()
    selected = str(reviewed) if exists else None
    if not exists:
        _add_reason(reasons, "reviewed_gh_missing")

    version = _run_capture(runner, _launcher_command(reviewed, ["--version"], env), root)
    auth = _run_capture(runner, _launcher_command(reviewed, ["auth", "status"], env), root)
    repo = _run_capture(
        runner,
        _launcher_command(reviewed, ["repo", "view", expected_repository, "--json", "nameWithOwner"], env),
        root,
    )
    repo_name = _parse_repo_name(repo["stdout"])

    if exists and version["exit_code"] != 0:
        _add_reason(reasons, "gh_version_probe_failed")
    if exists and auth["exit_code"] != 0:
        _add_reason(reasons, "gh_auth_failed")
    if exists and repo["exit_code"] != 0:
        _add_reason(reasons, "gh_repository_read_failed")
    if repo["exit_code"] == 0 and _normalize_repo(repo_name) != _normalize_repo(expected_repository):
        _add_reason(reasons, "gh_repository_mismatch")

    path_resolved = _which("gh.exe", env) or _which("gh", env)
    return {
        "reviewed_path": str(reviewed),
        "reviewed_path_exists": exists,
        "path_resolved_path": path_resolved,
        "fresh_shell_resolved_path": fresh_shell["gh"]["fresh_shell_resolved_path"],
        "selected_path": selected,
        "selection_source": "reviewed_absolute_path" if selected else "none",
        "safe_launcher": _safe_windows_launcher(reviewed),
        "version_probe_exit_code": version["exit_code"],
        "version": _first_line(version["stdout"]),
        "interactive_host_gh_auth_verified": interactive_host_gh_auth_verified,
        "current_process_gh_auth_status": "authenticated" if auth["exit_code"] == 0 else "failed",
        "authenticated": auth["exit_code"] == 0,
        "gh_auth_probe_exit_code": auth["exit_code"],
        "repository_read_exit_code": repo["exit_code"],
        "repository_read_matches": _normalize_repo(repo_name) == _normalize_repo(expected_repository),
        "probes": {
            "gh_version": _probe("gh_version", version),
            "gh_auth": _probe("gh_auth", auth),
            "gh_repository_read": _probe("gh_repository_read", repo),
        },
    }


def _inspect_codex(
    root: Path,
    runner: CommandRunner,
    reviewed_codex_path: str | Path,
    fresh_shell: dict[str, Any],
    manifest_version: str | None,
    env: Mapping[str, str],
    reasons: list[str],
) -> dict[str, Any]:
    reviewed = Path(reviewed_codex_path)
    exists = reviewed.is_file()
    suffix = reviewed.suffix.lower()
    safe = _safe_windows_launcher(reviewed)
    if not exists:
        _add_reason(reasons, "reviewed_codex_missing")
    if not safe:
        _add_reason(reasons, "codex_unsafe_launcher")

    if exists and safe:
        version = _run_capture(runner, _launcher_command(reviewed, ["--version"], env), root)
        if version["exit_code"] != 0:
            _add_reason(reasons, "codex_version_probe_failed")
    elif exists:
        version = _not_executed("unsafe_launcher")
    else:
        version = _not_executed("missing_reviewed_path")

    path_resolved = _which("codex.cmd", env) or _which("codex.exe", env) or _which("codex", env)
    actual = _parse_version(_first_line(version["stdout"]))
    return {
        "reviewed_path": str(reviewed),
        "reviewed_path_exists": exists,
        "path_resolved_path": path_resolved,
        "fresh_shell_resolved_path": fresh_shell["codex"]["fresh_shell_resolved_path"],
        "selected_path": str(reviewed) if exists and safe else None,
        "selection_source": "reviewed_absolute_path" if exists and safe else "none",
        "suffix": suffix,
        "safe_launcher": safe,
        "version_probe_exit_code": version["exit_code"],
        "version": actual or _first_line(version["stdout"]),
        "manifest_expected_version": manifest_version,
        "version_matches_manifest": actual == manifest_version if manifest_version else None,
        "probes": {"codex_version": _probe("codex_version", version)},
    }


def _inspect_bootstrap_contract(
    root: Path,
    reviewed_python_path: str | Path,
    github_cli: dict[str, Any],
    codex_cli: dict[str, Any],
    fresh_shell: dict[str, Any],
    reasons: list[str],
) -> dict[str, Any]:
    manifest_path = root / "scripts" / "bootstrap_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _add_reason(reasons, "manifest_unreadable")
        manifest = {}
    manifest_valid = _manifest_valid(manifest)
    if not manifest_valid and "manifest_unreadable" not in reasons:
        _add_reason(reasons, "manifest_invalid")
    manifest_data = manifest if isinstance(manifest, dict) else {}

    paths_data = manifest_data.get("paths") if isinstance(manifest_data.get("paths"), dict) else {}
    codex_data = manifest_data.get("codex") if isinstance(manifest_data.get("codex"), dict) else {}
    manifest_venv = paths_data.get("venv")
    manifest_codex = codex_data.get("version")
    manifest_abs = str((root / manifest_venv).resolve()) if manifest_venv else None
    reviewed_venv = str(Path(reviewed_python_path).resolve().parents[1])
    venv_matches = _same_path(manifest_abs, reviewed_venv)

    gitignore_text = ""
    try:
        gitignore_text = (root / ".gitignore").read_text(encoding="utf-8")
    except OSError:
        pass
    manifest_ignored = _gitignore_mentions(gitignore_text, manifest_venv)

    actual_codex = codex_cli.get("version")
    codex_matches = actual_codex == manifest_codex
    drift_reasons: list[str] = []
    if not venv_matches:
        drift_reasons.append("operational_venv_differs_from_manifest")
        _add_reason(reasons, "operational_venv_differs_from_manifest")
    if manifest_venv and not manifest_ignored:
        drift_reasons.append("manifest_venv_not_gitignored")
        _add_reason(reasons, "manifest_venv_not_gitignored")
    if manifest_codex and actual_codex and not codex_matches:
        drift_reasons.append("codex_version_differs_from_manifest")
        _add_reason(reasons, "codex_version_differs_from_manifest")
    if any(not item["current_matches_reviewed"] for item in fresh_shell.values()):
        drift_reasons.append("path_resolution_differs_from_reviewed_path")
    if any(not item["fresh_shell_matches_reviewed"] for item in fresh_shell.values()):
        drift_reasons.append("fresh_shell_resolution_differs_from_reviewed_path")

    return {
        "bootstrap_manifest_protocol": manifest_data.get("protocol"),
        "manifest_venv_relative_path": manifest_venv,
        "manifest_venv_absolute_path": manifest_abs,
        "reviewed_venv_root": reviewed_venv,
        "venv_path_matches_manifest": venv_matches,
        "manifest_codex_version": manifest_codex,
        "actual_codex_version": actual_codex,
        "codex_version_matches_manifest": codex_matches if actual_codex else None,
        "manifest_venv_gitignored": manifest_ignored,
        "contract_drift_detected": bool(drift_reasons),
        "contract_drift_reasons": _ordered_subset(drift_reasons),
        "manifest_valid": manifest_valid,
    }


def _safety(*, repository_modified_by_check: bool) -> dict[str, bool]:
    return {
        "read_only": True,
        "packages_installed": False,
        "venv_created": False,
        "path_modified": False,
        "git_fetch_invoked": False,
        "git_pull_invoked": False,
        "git_switch_invoked": False,
        "git_reset_invoked": False,
        "git_clean_invoked": False,
        "git_stash_invoked": False,
        "github_write_performed": False,
        "bridge_operator_invoked": False,
        "dispatcher_invoked": False,
        "runner_invoked": False,
        "pollonce_invoked": False,
        "codex_task_executed": False,
        "interactive_codex_invoked": False,
        "repository_modified_by_check": repository_modified_by_check,
        "temporary_files_created_in_repository": False,
    }


def _status(reasons: list[str]) -> tuple[str, list[str], bool]:
    ordered = _ordered_subset(reasons)
    if any(reason in BLOCKING_REASONS for reason in ordered):
        return BLOCKED, ordered, False
    if any(reason in ATTENTION_REASONS for reason in ordered):
        return ATTENTION, ordered, True
    return READY, [], True


def _ordered_subset(values: list[str]) -> list[str]:
    order = list(BLOCKING_REASONS) + list(ATTENTION_REASONS)
    result: list[str] = []
    for reason in order:
        if reason in values and reason not in result:
            result.append(reason)
    for reason in values:
        if reason not in result:
            result.append(reason)
    return result


def _git(root: Path, runner: CommandRunner, *args: str) -> dict[str, Any]:
    return _run_capture(runner, ["git", *args], root)


def _run_capture(runner: CommandRunner, command: list[str], root: Path) -> dict[str, Any]:
    try:
        result = runner(command, root)
    except Exception as error:
        return {"ok": False, "exit_code": 99, "stdout": "", "safe_message": type(error).__name__}
    return {
        "ok": result.returncode == 0,
        "exit_code": result.returncode,
        "stdout": (result.stdout or "").strip(),
        "safe_message": "command_failed" if result.returncode else "ok",
    }


def _run_command(
    command: list[str],
    cwd: Path,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        env=dict(env) if env is not None else None,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        timeout=20,
    )


def _fresh_shell_resolve(name: str, root: Path, env: Mapping[str, str]) -> str | None:
    command = [
        "powershell.exe",
        "-NoProfile",
        "-Command",
        f"(Get-Command {json.dumps(name)} -ErrorAction SilentlyContinue).Source",
    ]
    result = _run_command(command, root, env)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _launcher_command(
    path: str | Path,
    args: list[str],
    env: Mapping[str, str] | None = None,
) -> list[str]:
    path_text = str(path)
    suffix = Path(path_text).suffix.lower()
    if suffix in {".cmd", ".bat"}:
        source_env = os.environ if env is None else env
        comspec = source_env.get("COMSPEC") or "cmd.exe"
        return [comspec, "/d", "/s", "/c", "call", path_text, *args]
    return [path_text, *args]


def _safe_windows_launcher(path: Path) -> bool:
    suffix = path.suffix.lower()
    return bool(suffix in SAFE_WINDOWS_SUFFIXES and suffix not in UNSAFE_SUFFIXES)


def _normalize_repo(origin: str | None) -> str | None:
    if not origin:
        return None
    text = origin.strip().split("?", 1)[0].split("#", 1)[0]
    if text.endswith(".git"):
        text = text[:-4]
    text = text.replace("\\", "/")
    if text.startswith("git@github.com:"):
        text = text.split(":", 1)[1]
    elif "github.com/" in text:
        text = text.split("github.com/", 1)[1]
    return text.lower()


def _sanitize_origin_url(value: str | None) -> str | None:
    if not value:
        return value
    text = value.strip()
    try:
        parsed = urlsplit(text)
        port = parsed.port
    except ValueError:
        return _sanitize_unparsed_origin(text)

    if parsed.scheme and parsed.netloc:
        hostname = parsed.hostname
        if not hostname:
            return _sanitize_unparsed_origin(text)
        host = hostname
        if port is not None:
            host = f"{host}:{port}"
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))

    return _sanitize_unparsed_origin(text)


def _sanitize_unparsed_origin(text: str) -> str:
    without_query = text.split("?", 1)[0].split("#", 1)[0]
    if "://" in without_query:
        scheme, remainder = without_query.split("://", 1)
        authority, separator, path = remainder.partition("/")
        if "@" in authority:
            authority = authority.rsplit("@", 1)[1]
        if not scheme or not authority:
            return "<unparseable-origin>"
        return f"{scheme}://{authority}{separator}{path}"
    if "@" in without_query and "://" not in without_query:
        userinfo, remainder = without_query.rsplit("@", 1)
        if ":" in userinfo or userinfo != "git":
            return remainder
    return without_query


def _which(name: str, env: Mapping[str, str]) -> str | None:
    path = env.get("PATH")
    if path is None:
        return None
    return shutil.which(name, path=path)


def _probe(stage: str, result: dict[str, Any]) -> dict[str, Any]:
    executed = bool(result.get("executed", True))
    return {
        "stage": stage,
        "ok": bool(result["ok"]),
        "executed": executed,
        "exit_code": result["exit_code"],
        "error_type": None if result["ok"] else ("CommandFailed" if executed else "NotExecuted"),
        "safe_message": result["safe_message"],
    }


def _not_executed(safe_message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "executed": False,
        "exit_code": None,
        "stdout": "",
        "safe_message": safe_message,
    }


def _manifest_valid(manifest: Any) -> bool:
    if not isinstance(manifest, dict):
        return False
    if not isinstance(manifest.get("protocol"), str) or not manifest["protocol"].strip():
        return False
    paths = manifest.get("paths")
    if not isinstance(paths, dict):
        return False
    if not isinstance(paths.get("venv"), str) or not paths["venv"].strip():
        return False
    codex = manifest.get("codex")
    if not isinstance(codex, dict):
        return False
    if not isinstance(codex.get("version"), str) or not codex["version"].strip():
        return False
    return True


def _parse_repo_name(text: str) -> str | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    value = payload.get("nameWithOwner")
    return value if isinstance(value, str) else None


def _parse_version(text: str | None) -> str | None:
    if not text:
        return None
    for token in text.replace("v", " ").split():
        if token.count(".") >= 1 and token[0].isdigit():
            return token
    return None


def _parse_import_failures(text: str) -> list[str]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return ["unknown"] if text else []
    failures = payload.get("failures", [])
    return failures if isinstance(failures, list) else ["unknown"]


def _import_probe_code() -> str:
    imports = repr(REQUIRED_IMPORTS)
    return (
        "import importlib,json;"
        f"mods={imports};fail=[];"
        "\nfor m in mods:\n"
        "    try: importlib.import_module(m)\n"
        "    except Exception: fail.append(m)\n"
        "print(json.dumps({'failures': fail}));"
        "raise SystemExit(1 if fail else 0)"
    )


def _gitignore_mentions(text: str, path: str | None) -> bool:
    if not path:
        return False
    normalized = path.strip().strip("/\\")
    for line in text.splitlines():
        item = line.strip().strip("/\\")
        if item == normalized:
            return True
    return False


def _same_path(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return _normalize_windows_path(left) == _normalize_windows_path(right)


def _normalize_windows_path(path: str) -> str:
    text = str(path).replace("/", "\\")
    absolute = ntpath.abspath(text)
    normalized = ntpath.normpath(absolute)
    return ntpath.normcase(normalized).rstrip("\\/")


def _first_line(text: str | None) -> str | None:
    if not text:
        return None
    lines = text.splitlines()
    return lines[0].strip() if lines else None


def _add_reason(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _failure(stage: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage": stage,
        "error_type": "CommandFailed" if result.get("exit_code") else result.get("safe_message"),
        "exit_code": result.get("exit_code"),
        "safe_message": result.get("safe_message"),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--expected-repository", required=True)
    parser.add_argument("--expected-branch", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--reviewed-python-path", required=True)
    parser.add_argument("--reviewed-gh-path", required=True)
    parser.add_argument("--reviewed-codex-path", required=True)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        summary = run_host_check(
            repo_root=args.repo_root,
            expected_repository=args.expected_repository,
            expected_branch=args.expected_branch,
            expected_head=args.expected_head,
            reviewed_python_path=args.reviewed_python_path,
            reviewed_gh_path=args.reviewed_gh_path,
            reviewed_codex_path=args.reviewed_codex_path,
        )
    except Exception as error:
        payload = {"protocol": PROTOCOL, "status": BLOCKED, "status_reasons": ["unexpected_harness_failure"], "safe_message": type(error).__name__}
        print(json.dumps(payload, indent=2 if args.pretty else None, sort_keys=True))
        return 3

    if args.json or args.pretty:
        print(json.dumps(summary, indent=2 if args.pretty else None, sort_keys=True))
    else:
        print(_human_summary(summary))
    return 2 if summary["status"] == BLOCKED else 0


def _human_summary(summary: dict[str, Any]) -> str:
    repo = summary["repository"]
    py = summary["python"]
    gh = summary["github_cli"]
    codex = summary["codex_cli"]
    drift = summary["bootstrap_contract"]
    safety = summary["safety"]
    return "\n".join(
        [
            f"protocol: {summary['protocol']}",
            f"status: {summary['status']}",
            f"operational readiness: {summary['operational_readiness']}",
            f"repository binding: {repo['repository_matches']} branch={repo['current_branch']} head={repo['head']}",
            f"Python: {py['reviewed_python_path']} version={py['python_version']} imports_ready={py['required_imports_ready']}",
            f"gh: {gh['selected_path']} version={gh['version']} authenticated={gh['authenticated']} repo_read={gh['repository_read_matches']}",
            f"Codex: {codex['selected_path']} version={codex['version']} safe_launcher={codex['safe_launcher']}",
            f"fresh-shell visibility: python={summary['fresh_shell']['python']['fresh_shell_resolved_path']} gh={summary['fresh_shell']['gh']['fresh_shell_resolved_path']} codex={summary['fresh_shell']['codex']['fresh_shell_resolved_path']}",
            f"contract drift: {drift['contract_drift_detected']} reasons={drift['contract_drift_reasons']}",
            f"safety assertions: read_only={safety['read_only']} repository_modified_by_check={safety['repository_modified_by_check']}",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())

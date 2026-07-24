"""JSON command surface for the bounded foreground Display Pilot candidate."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from functools import partial
from pathlib import Path
from typing import Any

from .display_pilot_hgw_adapter import render_from_evidence, verify_hgw_checkout
from .display_pilot_operator import (
    DEFAULT_MAX_CYCLES,
    DEFAULT_POLL_INTERVAL_SECONDS,
    _path_is_within,
    run_foreground,
)
from .display_pilot_transport import (
    SELECTOR_ISSUE,
    SELECTOR_REPOSITORY,
    TARGET_REPOSITORY,
    body_sha256,
)


LAWB_ORIGIN = "https://github.com/HarryWhite-TW/local-ai-workbench.git"
TARGET_ORIGIN = (
    "https://github.com/HarryWhite-TW/"
    "human-approval-automation-gateway.git"
)
CONTROL_ROOT = Path(__file__).resolve().parents[2]
RUNNER_TIMEOUT_SECONDS = 1500
_VERIFIED_RUNTIME_PATH_FIELDS = (
    "state_root",
    "lawb_root",
    "hgw_root",
    "target_repo_root",
    "python_path",
    "powershell_path",
    "gh_path",
    "codex_path",
    "runner_path",
)
_REVIEWED_FILE_FIELDS = (
    "python_path",
    "powershell_path",
    "gh_path",
    "codex_path",
    "runner_path",
)


def _summary(result: str, reasons: list[str] | None = None) -> dict[str, Any]:
    return {
        "protocol": "hgw.display_pilot.operator.v1",
        "result": result,
        "blocked_reasons": list(reasons or []),
        "live_start_performed": False,
        "github_write_performed": False,
        "runner_invoked": False,
        "codex_invoked": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("setup", "verify", "start"))
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--lawb-root")
    parser.add_argument("--lawb-branch")
    parser.add_argument("--lawb-head")
    parser.add_argument(
        "--lawb-expected-modified-file",
        action="append",
        default=[],
    )
    parser.add_argument("--hgw-root")
    parser.add_argument("--target-repo-root")
    parser.add_argument("--python-path")
    parser.add_argument("--powershell-path")
    parser.add_argument("--gh-path")
    parser.add_argument("--codex-path")
    parser.add_argument("--runner-path")
    parser.add_argument("--max-cycles", type=int, default=DEFAULT_MAX_CYCLES)
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
    )
    return parser


def _git(
    root: Path,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
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
        shell=False,
        check=False,
    )


def _verify_git_root(root: Path, origin: str, *, require_clean: bool) -> bool:
    if not root.is_dir():
        return False
    probes = (
        _git(root, "rev-parse", "--show-toplevel"),
        _git(root, "remote", "get-url", "origin"),
        _git(root, "branch", "--show-current"),
        _git(root, "rev-parse", "HEAD"),
        _git(root, "status", "--short", "--untracked-files=all"),
        _git(root, "diff", "--cached", "--name-only"),
    )
    if any(probe.returncode != 0 for probe in probes):
        return False
    try:
        observed_root = Path(probes[0].stdout.strip()).resolve()
    except OSError:
        return False
    if (
        os.path.normcase(str(observed_root))
        != os.path.normcase(str(root))
        or probes[1].stdout.strip() != origin
        or probes[5].stdout.strip()
    ):
        return False
    return not require_clean or not probes[4].stdout.strip()


def _status_paths(status: str) -> list[str] | None:
    paths: list[str] = []
    for line in status.splitlines():
        if len(line) < 4 or line.startswith("??") or " -> " in line:
            return None
        paths.append(line[3:].replace("\\", "/"))
    return sorted(set(paths))


def _verify_lawb_checkout(
    root: Path,
    *,
    branch: str,
    head: str,
    expected_modified_files: list[str],
) -> bool:
    if re.fullmatch(r"[0-9a-fA-F]{40}", head) is None:
        return False
    if not _verify_git_root(root, LAWB_ORIGIN, require_clean=False):
        return False
    branch_probe = _git(root, "branch", "--show-current")
    head_probe = _git(root, "rev-parse", "HEAD")
    status_probe = _git(root, "status", "--short", "--untracked-files=all")
    if any(
        probe.returncode != 0
        for probe in (branch_probe, head_probe, status_probe)
    ):
        return False
    observed_paths = _status_paths(status_probe.stdout.rstrip())
    expected_paths = sorted(
        set(value.replace("\\", "/") for value in expected_modified_files)
    )
    return (
        branch_probe.stdout.strip() == branch
        and head_probe.stdout.strip().lower() == head.lower()
        and observed_paths == expected_paths
    )


def _state_root_reasons(
    state_root: str | Path,
    roots: list[str | Path],
) -> list[str]:
    state = Path(state_root).resolve()
    return (
        ["state_root_inside_git_worktree"]
        if any(_path_is_within(state, Path(root)) for root in roots)
        else []
    )


def verify_start_prerequisites(arguments: argparse.Namespace) -> dict[str, Any]:
    required = (
        "lawb_root",
        "lawb_branch",
        "lawb_head",
        "hgw_root",
        "target_repo_root",
        "python_path",
        "powershell_path",
        "gh_path",
        "codex_path",
        "runner_path",
    )
    missing = [name for name in required if not getattr(arguments, name)]
    if missing:
        return _summary("blocked", ["required_start_path_missing"])

    lawb = Path(arguments.lawb_root).resolve()
    hgw_root = Path(arguments.hgw_root).resolve()
    target = Path(arguments.target_repo_root).resolve()
    state_root = Path(arguments.state_root).resolve()
    runner = Path(arguments.runner_path).resolve()
    reviewed_paths = {
        name: Path(getattr(arguments, name))
        for name in _REVIEWED_FILE_FIELDS
    }
    executable_paths = {
        name: path.resolve()
        for name, path in reviewed_paths.items()
    }
    reasons: list[str] = []
    if any(not path.is_absolute() for path in reviewed_paths.values()):
        reasons.append("reviewed_path_not_absolute")
    reasons.extend(
        _state_root_reasons(
            state_root,
            [lawb, hgw_root, target],
        )
    )
    if not _verify_lawb_checkout(
        lawb,
        branch=arguments.lawb_branch,
        head=arguments.lawb_head,
        expected_modified_files=arguments.lawb_expected_modified_file,
    ):
        reasons.append("lawb_checkout_invalid")
    if runner != (lawb / "scripts" / "local_runner_v1.ps1").resolve():
        reasons.append("runner_path_not_lawb_runner")
    if not _verify_git_root(target, TARGET_ORIGIN, require_clean=True):
        reasons.append("target_checkout_invalid")
    if any(not path.is_file() for path in executable_paths.values()):
        reasons.append("reviewed_executable_missing")
    hgw = verify_hgw_checkout(str(hgw_root))
    if hgw["result"] != "success":
        reasons.append(hgw["reason"])
    output = _summary("blocked" if reasons else "success", reasons)
    output["checks"] = {
        "state_root": (
            "blocked"
            if "state_root_inside_git_worktree" in reasons
            else "passed"
        ),
        "lawb_checkout": "passed" if "lawb_checkout_invalid" not in reasons else "blocked",
        "target_checkout": (
            "passed" if "target_checkout_invalid" not in reasons else "blocked"
        ),
        "hgw_checkout": "passed" if hgw["result"] == "success" else "blocked",
        "reviewed_paths": (
            "passed"
            if not {
                "reviewed_executable_missing",
                "reviewed_path_not_absolute",
            }.intersection(reasons)
            else "blocked"
        ),
    }
    if not reasons:
        output["verified_runtime_config"] = {
            "state_root": str(state_root),
            "lawb_root": str(lawb),
            "hgw_root": str(hgw_root),
            "target_repo_root": str(target),
            **{
                name: str(executable_paths[name])
                for name in _REVIEWED_FILE_FIELDS
            },
        }
    return output


def _read_issue(gh_path: str, repository: str, issue: int) -> dict[str, Any]:
    completed = subprocess.run(
        [
            gh_path,
            "issue",
            "view",
            str(issue),
            "--repo",
            repository,
            "--json",
            "number,body,state,author",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
        check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError("github_issue_read_failed")
    value = json.loads(completed.stdout)
    body = value.get("body")
    author = value.get("author")
    if not isinstance(body, str) or type(author) is not dict:
        raise RuntimeError("github_issue_shape_invalid")
    return {
        "repository": repository,
        "number": value.get("number"),
        "body": body,
        "state": value.get("state"),
        "creator": author.get("login"),
        "body_sha256": body_sha256(body),
    }


def _invoke_runner(
    request: dict[str, Any],
    evidence_path: Path,
    *,
    powershell_path: str,
    runner_path: str,
    target_repo_root: str,
    codex_path: str,
    gh_path: str,
) -> int:
    issue = request["selector"]["target_issue"]
    completed = subprocess.run(
        [
            powershell_path,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            runner_path,
            "-IssueNumber",
            str(issue),
            "-Mode",
            "ReviewBundle",
            "-Repo",
            TARGET_REPOSITORY,
            "-RepoPath",
            target_repo_root,
            "-ReviewedCodexPath",
            codex_path,
            "-ReviewedGhPath",
            gh_path,
            "-MachineEvidencePath",
            str(evidence_path),
            "-DisplayPilotRequestId",
            request["selector"]["request_id"],
            "-SuppressReviewBundleComment",
        ],
        cwd=target_repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
        check=False,
        timeout=RUNNER_TIMEOUT_SECONDS,
    )
    return completed.returncode


def _validated_runtime_config(value: Any) -> dict[str, str] | None:
    if type(value) is not dict or set(value) != set(
        _VERIFIED_RUNTIME_PATH_FIELDS
    ):
        return None
    verified: dict[str, str] = {}
    for name in _VERIFIED_RUNTIME_PATH_FIELDS:
        path_value = value[name]
        if type(path_value) is not str:
            return None
        path = Path(path_value)
        if (
            not path.is_absolute()
            or os.path.normcase(str(path.resolve()))
            != os.path.normcase(path_value)
        ):
            return None
        verified[name] = path_value
    return verified


def _start(
    verified_runtime_config: Any,
    *,
    max_cycles: int = DEFAULT_MAX_CYCLES,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> dict[str, Any]:
    config = _validated_runtime_config(verified_runtime_config)
    if config is None:
        return _summary("blocked", ["verified_runtime_config_invalid"])
    selector_reader = lambda: _read_issue(
        config["gh_path"],
        SELECTOR_REPOSITORY,
        SELECTOR_ISSUE,
    )
    target_reader = lambda issue: _read_issue(
        config["gh_path"],
        TARGET_REPOSITORY,
        issue,
    )
    runner = partial(
        _invoke_runner,
        powershell_path=config["powershell_path"],
        runner_path=config["runner_path"],
        target_repo_root=config["target_repo_root"],
        codex_path=config["codex_path"],
        gh_path=config["gh_path"],
    )
    renderer = lambda evidence, result_id, created_at: render_from_evidence(
        root=config["hgw_root"],
        python_path=config["python_path"],
        evidence=evidence,
        result_id=result_id,
        created_at=created_at,
    )
    return run_foreground(
        state_root=config["state_root"],
        target_repo_root=config["target_repo_root"],
        selector_reader=selector_reader,
        target_reader=target_reader,
        runner=runner,
        hgw_renderer=renderer,
        python_path=config["python_path"],
        forbidden_state_roots=(
            config["lawb_root"],
            config["hgw_root"],
            config["target_repo_root"],
        ),
        max_cycles=max_cycles,
        poll_interval_seconds=poll_interval_seconds,
    )


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = _parser().parse_args(argv)
    except SystemExit:
        print(json.dumps(_summary("blocked", ["invalid_arguments"]), sort_keys=True))
        return 2

    if arguments.action == "setup":
        root = Path(arguments.state_root).resolve()
        protected_roots = (
            arguments.lawb_root,
            arguments.hgw_root,
            arguments.target_repo_root,
        )
        if any(not value for value in protected_roots):
            output = _summary("blocked", ["required_setup_root_missing"])
            print(json.dumps(output, ensure_ascii=False, sort_keys=True))
            return 2
        reasons = _state_root_reasons(
            root,
            [CONTROL_ROOT, *protected_roots],
        )
        if reasons:
            output = _summary("blocked", reasons)
        else:
            root.mkdir(parents=True, exist_ok=True)
            (root / "requests").mkdir(exist_ok=True)
            output = _summary("success")
    else:
        output = verify_start_prerequisites(arguments)
        if output["result"] == "success" and arguments.action == "start":
            output = _start(
                output.get("verified_runtime_config"),
                max_cycles=arguments.max_cycles,
                poll_interval_seconds=arguments.poll_interval_seconds,
            )

    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0 if output["result"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())

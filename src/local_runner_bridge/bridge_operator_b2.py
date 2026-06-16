"""Bridge Operator B2 foreground one-shot delegation."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from local_runner_bridge.bridge_operator_b1 import (
    DEFAULT_REPOSITORY,
    TRUSTED_ACTORS,
    CommentRecord,
    GitHubApiClient,
    LocalReadiness,
    run_bridge_operator_b1_dry_run,
)

SUMMARY_PROTOCOL = "lawb.bridge_operator_b2_delegation_summary.v1"
RUNNER_RESULT_MARKER = "LAWBRUNNER-RESULT"
RUNNER_RESULT_PROTOCOL = "lawb.runner_result.v1"
DEFAULT_INBOX_ISSUE = 147
DEFAULT_TIMEOUT_SECONDS = 600


@dataclass(frozen=True)
class DispatcherInvocationResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


def run_bridge_operator_b2_once(
    *,
    repo_root: str | Path,
    repository: str = DEFAULT_REPOSITORY,
    inbox_issue: int = DEFAULT_INBOX_ISSUE,
    github_client: Any | None = None,
    local_checker: Any | None = None,
    dispatcher_invoker: Any | None = None,
    now_utc: Any | None = None,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Validate one fixed Inbox request, delegate once, and verify one result."""
    summary = _base_summary(repository, inbox_issue)

    if inbox_issue != DEFAULT_INBOX_ISSUE:
        _block(summary, "unsupported_inbox_issue")
        return summary
    if repository != DEFAULT_REPOSITORY:
        _block(summary, "unsupported_repository")
        return summary

    client = github_client or GitHubApiClient(repository)
    b1_summary = run_bridge_operator_b1_dry_run(
        inbox_issue=inbox_issue,
        repo_root=repo_root,
        repository=repository,
        github_client=client,
        local_checker=local_checker,
        now_utc=now_utc,
    )
    summary["b1_validation_result"] = b1_summary.get("result")
    _copy_b1_identity(summary, b1_summary)
    if b1_summary.get("result") != "success":
        _block(summary, "b1_validation_not_success")
        summary["blocked_reasons"].extend(
            reason
            for reason in b1_summary.get("blocked_reasons", [])
            if reason not in summary["blocked_reasons"]
        )
        return summary

    preexisting = _read_matching_results(client, summary)
    if preexisting["read_error"] is not None:
        _failure(summary, "github_read_unavailable")
        summary["delegation_result"] = "failure"
        summary["github_read_error_type"] = preexisting["read_error"]
        return summary
    if preexisting["matching_count"] > 0:
        summary["matching_result_preexisting"] = True
        match = preexisting["matches"][0]
        summary["target_result_comment_id"] = match["comment_id"]
        summary["target_result_author"] = match["author"]
        _block(summary, "matching_result_already_exists")
        summary["delegation_result"] = "blocked"
        return summary

    invoker = dispatcher_invoker or default_dispatcher_invoker
    timeout = timeout_seconds if timeout_seconds is not None else DEFAULT_TIMEOUT_SECONDS
    args = build_dispatcher_command(
        repo_root=repo_root,
        target_issue=int(summary["target_issue"]),
        repository=repository,
    )
    summary["dispatcher_invocation_args"] = args
    summary["dispatcher_invoked"] = True
    summary["dispatcher_invocation_count"] = 1

    try:
        invocation = invoker(args=args, cwd=str(Path(repo_root).resolve()), timeout_seconds=timeout)
    except TimeoutError as error:
        invocation = DispatcherInvocationResult(returncode=1, stderr=str(error), timed_out=True)
    except Exception as error:
        invocation = DispatcherInvocationResult(returncode=1, stderr=str(error), timed_out=False)

    summary["dispatcher_exit_code"] = invocation.returncode
    summary["dispatcher_timed_out"] = bool(invocation.timed_out)
    summary["dispatcher_stdout"] = invocation.stdout
    summary["dispatcher_stderr"] = invocation.stderr

    if invocation.timed_out:
        _failure(summary, "dispatcher_timeout")
        summary["delegation_result"] = "failure"
        return summary
    if invocation.returncode != 0:
        _failure(summary, "dispatcher_nonzero_exit")
        summary["delegation_result"] = "failure"
        return summary

    post = _read_matching_results(client, summary)
    if post["read_error"] is not None:
        _failure(summary, "github_read_unavailable")
        summary["github_read_error_type"] = post["read_error"]
        summary["delegation_result"] = "failure"
        return summary
    if post["matching_count"] == 0:
        _failure(summary, "target_result_missing")
        summary["delegation_result"] = "failure"
        return summary
    if post["matching_count"] > 1:
        _failure(summary, "multiple_matching_results")
        summary["delegation_result"] = "failure"
        return summary

    match = post["matches"][0]
    summary["target_result_comment_id"] = match["comment_id"]
    summary["target_result_author"] = match["author"]
    if match["author"] not in TRUSTED_ACTORS:
        _failure(summary, "untrusted_result_author")
        summary["delegation_result"] = "failure"
        return summary

    payload = match["payload"]
    result_value = str(payload.get("result") or "")
    if result_value != "success":
        _failure(summary, "target_result_not_success")
        summary["delegation_result"] = result_value or "failure"
        return summary

    summary["result"] = "success"
    summary["phase"] = "verified"
    summary["target_result_verified"] = True
    summary["delegation_result"] = "success"
    summary["next_recommended_action"] = "chatgpt_review_verified_result"
    return summary


def build_dispatcher_command(
    *,
    repo_root: str | Path,
    target_issue: int,
    repository: str = DEFAULT_REPOSITORY,
) -> list[str]:
    return [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(Path(repo_root).resolve() / "scripts" / "local_dispatcher_v1.ps1"),
        "-PollOnce",
        "-IssueNumber",
        str(target_issue),
        "-Repo",
        repository,
        "-PostResultComment",
    ]


def default_dispatcher_invoker(
    *,
    args: list[str],
    cwd: str,
    timeout_seconds: int,
) -> DispatcherInvocationResult:
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        return DispatcherInvocationResult(
            returncode=1,
            stdout=error.stdout or "",
            stderr=error.stderr or "",
            timed_out=True,
        )
    return DispatcherInvocationResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        timed_out=False,
    )


def parse_lawbrunner_result_comment(comment: CommentRecord) -> dict[str, Any]:
    body = comment.body.strip()
    marker = f"{RUNNER_RESULT_MARKER} protocol={RUNNER_RESULT_PROTOCOL}"
    marker_index = body.find(marker)
    if marker_index < 0:
        return {"result": "not_result"}
    json_text = body[marker_index + len(marker) :].strip()
    if not json_text:
        return {"result": "partial_result"}
    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError:
        return {"result": "malformed_json"}
    if not isinstance(payload, dict):
        return {"result": "malformed_json"}
    protocol = payload.get("protocol", payload.get("schema"))
    if protocol != RUNNER_RESULT_PROTOCOL:
        return {"result": "identity_mismatch", "payload": payload}
    return {
        "result": "success",
        "payload": payload,
        "comment_id": comment.id,
        "author": comment.author,
    }


def _read_matching_results(client: Any, summary: dict[str, Any]) -> dict[str, Any]:
    try:
        comments = client.list_issue_comments(int(summary["target_issue"]))
    except Exception as error:
        return {"read_error": type(error).__name__, "matching_count": 0, "matches": []}

    matches = []
    for comment in comments:
        parsed = parse_lawbrunner_result_comment(comment)
        if parsed["result"] != "success":
            continue
        payload = parsed["payload"]
        if _payload_matches_expected(payload, summary):
            matches.append(parsed)
    return {"read_error": None, "matching_count": len(matches), "matches": matches}


def _payload_matches_expected(payload: dict[str, Any], summary: dict[str, Any]) -> bool:
    expected = {
        "issue": summary["target_issue"],
        "action": summary["requested_action"],
        "repo": summary["repository"],
        "branch": summary["expected_branch"],
        "head": summary["expected_head"],
        "request_id": summary["target_dispatch_request_id"],
    }
    return all(str(payload.get(key)) == str(value) for key, value in expected.items())


def _base_summary(repository: str, inbox_issue: int) -> dict[str, Any]:
    return {
        "protocol": SUMMARY_PROTOCOL,
        "phase": "preflight",
        "result": "blocked",
        "repository": repository,
        "configured_inbox_issue": inbox_issue,
        "request_id": None,
        "target_issue": None,
        "target_dispatch_request_id": None,
        "requested_action": None,
        "expected_branch": None,
        "expected_head": None,
        "b1_validation_result": None,
        "matching_result_preexisting": False,
        "dispatcher_invoked": False,
        "dispatcher_invocation_count": 0,
        "dispatcher_exit_code": None,
        "dispatcher_timed_out": False,
        "target_result_verified": False,
        "target_result_comment_id": None,
        "target_result_author": None,
        "delegation_result": "blocked",
        "blocked_reasons": [],
        "next_recommended_action": "chatgpt_review",
        "broad_issue_scan_performed": False,
        "latest_next_inference_performed": False,
        "retry_performed": False,
        "loop_started": False,
        "background_service_started": False,
        "commit_performed": False,
        "push_performed": False,
        "issue_closed": False,
        "label_changed": False,
        "pr_created": False,
        "merge_performed": False,
        "branch_deleted": False,
        "approval_consumed": False,
        "github_write_performed": False,
    }


def _copy_b1_identity(summary: dict[str, Any], b1_summary: dict[str, Any]) -> None:
    for source, target in (
        ("request_id", "request_id"),
        ("target_issue", "target_issue"),
        ("target_dispatch_request_id", "target_dispatch_request_id"),
        ("requested_action", "requested_action"),
        ("expected_branch", "expected_branch"),
        ("expected_head", "expected_head"),
    ):
        summary[target] = b1_summary.get(source)


def _block(summary: dict[str, Any], reason: str) -> None:
    if reason not in summary["blocked_reasons"]:
        summary["blocked_reasons"].append(reason)
    summary["result"] = "blocked"
    summary["phase"] = "blocked"


def _failure(summary: dict[str, Any], reason: str) -> None:
    if reason not in summary["blocked_reasons"]:
        summary["blocked_reasons"].append(reason)
    summary["result"] = "failure"
    summary["phase"] = "failed"

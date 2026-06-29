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
TOOL_PREFLIGHT_PROTOCOL = "lawb.rv2_03_tool_resolution_preflight.v1"
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
    preflight_invoker: Any | None = None,
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
    preflight = preflight_invoker or default_dispatcher_invoker
    timeout = timeout_seconds if timeout_seconds is not None else DEFAULT_TIMEOUT_SECONDS
    preflight_args = build_dispatcher_preflight_command(
        repo_root=repo_root,
        required_action=str(summary["requested_action"]),
        repository=repository,
    )
    summary["tool_resolution_preflight_invocation_args"] = preflight_args
    summary["tool_resolution_preflight_invoked"] = True
    summary["tool_resolution_preflight_invocation_count"] = 1

    try:
        preflight_result = preflight(
            args=preflight_args,
            cwd=str(Path(repo_root).resolve()),
            timeout_seconds=timeout,
        )
    except TimeoutError as error:
        preflight_result = DispatcherInvocationResult(returncode=1, stderr=str(error), timed_out=True)
    except Exception as error:
        preflight_result = DispatcherInvocationResult(returncode=1, stderr=str(error), timed_out=False)

    summary["tool_resolution_preflight_exit_code"] = preflight_result.returncode
    summary["tool_resolution_preflight_timed_out"] = bool(preflight_result.timed_out)
    summary["tool_resolution_preflight_stdout"] = preflight_result.stdout
    summary["tool_resolution_preflight_stderr"] = preflight_result.stderr

    preflight_validation = _validate_tool_resolution_preflight(
        preflight_result,
        required_action=str(summary["requested_action"]),
    )
    _copy_preflight_validation(summary, preflight_validation)
    if not preflight_validation["ok"]:
        reason = preflight_validation["reason"]
        if preflight_validation["structured_blocked"]:
            _block(summary, reason)
            for blocked_reason in summary["tool_resolution_preflight_blocked_reasons"]:
                if blocked_reason not in summary["blocked_reasons"]:
                    summary["blocked_reasons"].append(blocked_reason)
            summary["delegation_result"] = "blocked"
        else:
            _failure(summary, reason)
            summary["delegation_result"] = "failure"
        return summary

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


def build_dispatcher_preflight_command(
    *,
    repo_root: str | Path,
    required_action: str,
    repository: str = DEFAULT_REPOSITORY,
) -> list[str]:
    return [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(Path(repo_root).resolve() / "scripts" / "local_dispatcher_v1.ps1"),
        "-ToolResolutionPreflight",
        "-RequiredAction",
        required_action,
        "-Repo",
        repository,
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


def _validate_tool_resolution_preflight(
    invocation: DispatcherInvocationResult,
    *,
    required_action: str,
) -> dict[str, Any]:
    base = {
        "ok": False,
        "reason": "tool_resolution_preflight_contract_failure",
        "structured_blocked": False,
        "payload": None,
    }
    if invocation.timed_out:
        return {**base, "reason": "tool_resolution_preflight_timeout"}
    if invocation.returncode not in (0, 2):
        return {**base, "reason": "tool_resolution_preflight_nonzero_exit"}
    if not invocation.stdout.strip():
        return {**base, "reason": "tool_resolution_preflight_empty_stdout"}
    try:
        payload = json.loads(invocation.stdout)
    except json.JSONDecodeError:
        return {**base, "reason": "tool_resolution_preflight_malformed_json"}
    if not isinstance(payload, dict):
        return {**base, "reason": "tool_resolution_preflight_non_object_json"}

    result = payload.get("result")
    blocked_reasons = payload.get("blocked_reasons")
    if payload.get("protocol") != TOOL_PREFLIGHT_PROTOCOL:
        return {**base, "reason": "tool_resolution_preflight_wrong_protocol", "payload": payload}
    if payload.get("component") != "dispatcher":
        return {**base, "reason": "tool_resolution_preflight_wrong_component", "payload": payload}
    if payload.get("required_action") != required_action:
        return {**base, "reason": "tool_resolution_preflight_wrong_required_action", "payload": payload}
    if result not in ("success", "blocked"):
        return {**base, "reason": "tool_resolution_preflight_invalid_result", "payload": payload}
    if not isinstance(blocked_reasons, list):
        return {**base, "reason": "tool_resolution_preflight_invalid_blocked_reasons", "payload": payload}
    if any(not isinstance(reason, str) or not reason.strip() for reason in blocked_reasons):
        return {**base, "reason": "tool_resolution_preflight_invalid_blocked_reasons", "payload": payload}
    if result == "success" and blocked_reasons:
        return {**base, "reason": "tool_resolution_preflight_success_with_blocked_reasons", "payload": payload}
    if result == "blocked" and not blocked_reasons:
        return {**base, "reason": "tool_resolution_preflight_blocked_without_reasons", "payload": payload}
    if result == "success" and invocation.returncode != 0:
        return {**base, "reason": "tool_resolution_preflight_success_exit_mismatch", "payload": payload}
    if result == "blocked" and invocation.returncode != 2:
        return {**base, "reason": "tool_resolution_preflight_blocked_exit_mismatch", "payload": payload}

    if result == "success":
        tools = payload.get("tools")
        if not isinstance(tools, dict):
            return {**base, "reason": "tool_resolution_preflight_missing_tools", "payload": payload}
        tool_error = _validate_tool_resolution_tool_entry(tools.get("dispatcher_gh"))
        if tool_error is not None:
            return {**base, "reason": f"tool_resolution_preflight_dispatcher_gh_{tool_error}", "payload": payload}

        nested_runner = payload.get("nested_runner")
        if required_action == "maybe-status-check":
            if nested_runner is not None:
                return {**base, "reason": "tool_resolution_preflight_unexpected_nested_runner", "payload": payload}
        elif required_action == "run-reviewbundle":
            nested_error = _validate_nested_runner_tool_resolution_preflight(nested_runner)
            if nested_error is not None:
                return {**base, "reason": f"tool_resolution_preflight_nested_runner_{nested_error}", "payload": payload}

    safety = payload.get("safety")
    if not isinstance(safety, dict):
        return {**base, "reason": "tool_resolution_preflight_missing_safety", "payload": payload}
    for field in _TOOL_RESOLUTION_SAFETY_FIELDS:
        if safety.get(field) is not False:
            return {
                **base,
                "reason": f"tool_resolution_preflight_safety_contradiction_{field}",
                "payload": payload,
            }

    if result == "blocked":
        return {
            **base,
            "reason": "tool_resolution_preflight_blocked",
            "structured_blocked": True,
            "payload": payload,
        }
    return {"ok": True, "reason": "none", "structured_blocked": False, "payload": payload}


def _validate_nested_runner_tool_resolution_preflight(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return "missing"
    if payload.get("protocol") != TOOL_PREFLIGHT_PROTOCOL:
        return "wrong_protocol"
    if payload.get("component") != "runner":
        return "wrong_component"
    if payload.get("result") != "success":
        return "not_success"
    if payload.get("required_action") != "run-reviewbundle":
        return "wrong_required_action"
    blocked_reasons = payload.get("blocked_reasons")
    if not isinstance(blocked_reasons, list) or blocked_reasons:
        return "invalid_blocked_reasons"
    if payload.get("nested_runner") is not None:
        return "unexpected_nested_runner"
    safety = payload.get("safety")
    if not isinstance(safety, dict):
        return "missing_safety"
    for field in _TOOL_RESOLUTION_SAFETY_FIELDS:
        if safety.get(field) is not False:
            return f"safety_contradiction_{field}"
    tools = payload.get("tools")
    if not isinstance(tools, dict):
        return "missing_tools"
    for tool_name in ("runner_gh", "codex"):
        tool_error = _validate_tool_resolution_tool_entry(tools.get(tool_name))
        if tool_error is not None:
            return f"{tool_name}_{tool_error}"
    return None


_TOOL_RESOLUTION_SAFE_SUFFIXES = {".exe", ".cmd", ".bat", ".com"}
_TOOL_RESOLUTION_SAFETY_FIELDS = (
    "pollonce_invoked",
    "dispatcher_action_executed",
    "github_issue_read_performed",
    "github_write_performed",
    "runner_work_invoked",
    "codex_task_executed",
)


def _validate_tool_resolution_tool_entry(tool: Any) -> str | None:
    if not isinstance(tool, dict):
        return "missing"
    selected_path = tool.get("selected_path")
    suffix = tool.get("suffix")
    selection_source = tool.get("selection_source")
    if not isinstance(selected_path, str) or not selected_path.strip():
        return "missing_selected_path"
    if not isinstance(suffix, str) or not suffix.strip():
        return "missing_suffix"
    normalized_suffix = suffix.lower()
    if normalized_suffix not in _TOOL_RESOLUTION_SAFE_SUFFIXES:
        return "unsafe_suffix"
    if not selected_path.lower().endswith(normalized_suffix):
        return "suffix_path_mismatch"
    if not isinstance(selection_source, str) or not selection_source.strip():
        return "missing_selection_source"
    version_probe = tool.get("version_probe")
    if not isinstance(version_probe, dict):
        return "missing_version_probe"
    if version_probe.get("executed") is not True:
        return "version_probe_not_executed"
    if version_probe.get("exit_code") != 0:
        return "version_probe_nonzero_exit"
    if version_probe.get("ok") is not True:
        return "version_probe_not_ok"
    if version_probe.get("safe_message") != "ok":
        return "version_probe_unsafe_message"
    return None


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
        "tool_resolution_preflight_invoked": False,
        "tool_resolution_preflight_invocation_count": 0,
        "tool_resolution_preflight_exit_code": None,
        "tool_resolution_preflight_timed_out": False,
        "tool_resolution_preflight_protocol": None,
        "tool_resolution_preflight_result": None,
        "tool_resolution_preflight_component": None,
        "tool_resolution_preflight_required_action": None,
        "tool_resolution_preflight_blocked_reasons": [],
        "tool_resolution_preflight_safety": None,
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


def _copy_preflight_validation(summary: dict[str, Any], validation: dict[str, Any]) -> None:
    payload = validation.get("payload")
    if not isinstance(payload, dict):
        return
    summary["tool_resolution_preflight_protocol"] = payload.get("protocol")
    summary["tool_resolution_preflight_result"] = payload.get("result")
    summary["tool_resolution_preflight_component"] = payload.get("component")
    summary["tool_resolution_preflight_required_action"] = payload.get("required_action")
    blocked_reasons = payload.get("blocked_reasons")
    summary["tool_resolution_preflight_blocked_reasons"] = (
        [reason for reason in blocked_reasons if isinstance(reason, str)]
        if isinstance(blocked_reasons, list)
        else []
    )
    safety = payload.get("safety")
    summary["tool_resolution_preflight_safety"] = safety if isinstance(safety, dict) else None


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

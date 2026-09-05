"""Bridge Operator B2 foreground one-shot delegation."""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Mapping

from local_runner_bridge.bridge_operator_b1 import (
    DEFAULT_REPOSITORY,
    NORMAL_CONTROL_RELAY_ISSUE,
    SUPPORTED_TARGET_REPOSITORIES,
    TRUSTED_ACTORS,
    CommentRecord,
    GitHubApiClient,
    LocalReadiness,
    run_bridge_operator_b1_dry_run,
)
from local_runner_bridge.bridge_operator_lifecycle_state import (
    LifecycleEvidenceError,
    capture_process_identity,
)

SUMMARY_PROTOCOL = "lawb.bridge_operator_b2_delegation_summary.v1"
TOOL_PREFLIGHT_PROTOCOL = "lawb.rv2_03_tool_resolution_preflight.v1"
RUNNER_RESULT_MARKER = "LAWBRUNNER-RESULT"
RUNNER_RESULT_PROTOCOL = "lawb.runner_result.v1"
DEFAULT_INBOX_ISSUE = NORMAL_CONTROL_RELAY_ISSUE
DEFAULT_TIMEOUT_SECONDS = 600
DISPATCHER_REJECTED_BEFORE_RUNNER_EXIT_CODE = 20
DISPATCHER_RUNNER_REACH_UNCERTAIN_EXIT_CODE = 21
DISPATCHER_FAILED_BEFORE_RUNNER_EXIT_CODE = 22
DISPATCHER_REJECTED_BEFORE_RUNNER = "rejected_before_runner"
DISPATCHER_RUNNER_MAY_HAVE_STARTED = "runner_may_have_started"
DISPATCHER_FAILED_BEFORE_RUNNER = "failed_before_runner"


@dataclass(frozen=True)
class DispatcherInvocationResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    execution_reach: str | None = None
    process_identity: dict[str, Any] | None = None


def run_bridge_operator_b2_once(
    *,
    repo_root: str | Path,
    control_repo_root: str | Path | None = None,
    repository: str = DEFAULT_REPOSITORY,
    inbox_issue: int = DEFAULT_INBOX_ISSUE,
    github_client: Any | None = None,
    target_github_client: Any | None = None,
    local_checker: Any | None = None,
    preflight_invoker: Any | None = None,
    dispatcher_invoker: Any | None = None,
    now_utc: Any | None = None,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Validate one fixed Inbox request, delegate once, and verify one result."""
    control_root = Path(control_repo_root if control_repo_root is not None else repo_root).resolve()
    target_root = Path(repo_root).resolve()
    summary = _base_summary(repository, inbox_issue, control_root, target_root)

    if inbox_issue != DEFAULT_INBOX_ISSUE:
        _block(summary, "unsupported_control_relay_issue")
        return summary
    if repository not in SUPPORTED_TARGET_REPOSITORIES:
        _block(summary, "unsupported_target_repository")
        return summary

    control_client = github_client or GitHubApiClient(DEFAULT_REPOSITORY)
    target_client = target_github_client
    if target_client is None:
        target_client = (
            control_client if repository == DEFAULT_REPOSITORY else GitHubApiClient(repository)
        )
    b1_summary = run_bridge_operator_b1_dry_run(
        inbox_issue=inbox_issue,
        repo_root=repo_root,
        repository=repository,
        github_client=control_client,
        target_github_client=target_client,
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

    preexisting = _read_matching_results(target_client, summary)
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
        repo_root=control_root,
        target_repo_root=target_root,
        required_action=str(summary["requested_action"]),
        repository=repository,
    )
    summary["tool_resolution_preflight_invocation_args"] = preflight_args
    summary["tool_resolution_preflight_invoked"] = True
    summary["tool_resolution_preflight_invocation_count"] = 1

    try:
        preflight_result = preflight(
            args=preflight_args,
            cwd=str(control_root),
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
        repo_root=control_root,
        target_repo_root=target_root,
        target_issue=int(summary["target_issue"]),
        relay_request=build_relay_dispatch_contract(b1_summary),
        repository=repository,
        reviewed_codex_path=preflight_validation.get("codex_path_binding"),
    )
    summary["dispatcher_invocation_args"] = args
    summary["dispatcher_invoked"] = True
    summary["dispatcher_invocation_count"] = 1

    try:
        invocation = invoker(args=args, cwd=str(control_root), timeout_seconds=timeout)
    except TimeoutError as error:
        invocation = DispatcherInvocationResult(returncode=1, stderr=str(error), timed_out=True)
    except Exception as error:
        invocation = DispatcherInvocationResult(returncode=1, stderr=str(error), timed_out=False)

    summary["dispatcher_exit_code"] = invocation.returncode
    summary["dispatcher_timed_out"] = bool(invocation.timed_out)
    summary["dispatcher_stdout"] = invocation.stdout
    summary["dispatcher_stderr"] = invocation.stderr
    summary["dispatcher_execution_reach"] = invocation.execution_reach

    if invocation.timed_out:
        _unresolved(summary, "dispatcher_timeout")
        summary["delegation_result"] = "unresolved"
        return summary
    if invocation.returncode != 0:
        _failure(summary, "dispatcher_nonzero_exit")
        summary["delegation_result"] = "failure"
        return summary

    post = _read_matching_results(target_client, summary)
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
    target_repo_root: str | Path | None = None,
    target_issue: int,
    expected_dispatch_request_id: str | None = None,
    relay_request: Mapping[str, Any] | None = None,
    repository: str = DEFAULT_REPOSITORY,
    reviewed_codex_path: str | None = None,
) -> list[str]:
    args = [
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
    if expected_dispatch_request_id and relay_request is not None:
        raise ValueError("relay_request_and_expected_dispatch_request_id_are_mutually_exclusive")
    if relay_request is not None:
        encoded_relay = base64.b64encode(
            json.dumps(dict(relay_request), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
        args.extend(["-RelayRequestBase64", encoded_relay])
    elif expected_dispatch_request_id:
        args.extend(["-ExpectedDispatchRequestId", expected_dispatch_request_id])
    if reviewed_codex_path:
        args.extend(["-ReviewedCodexPath", reviewed_codex_path])
    target_root = Path(target_repo_root).resolve() if target_repo_root is not None else Path(repo_root).resolve()
    if target_root != Path(repo_root).resolve():
        args.extend(["-TargetRepoRoot", str(target_root)])
    return args


def build_relay_dispatch_contract(b1_summary: Mapping[str, Any]) -> dict[str, Any]:
    """Create the exact local handoff for one B1-validated #279 relay request."""
    required = (
        "configured_inbox_issue",
        "inbox_comment_id",
        "inbox_request_author",
        "request_id",
        "target_dispatch_request_id",
        "target_issue",
        "target_repository",
        "expected_branch",
        "expected_head",
        "expires",
        "requested_action",
    )
    if b1_summary.get("control_relay_mode") != "single_relay":
        raise ValueError("single_control_relay_required")
    if any(b1_summary.get(key) is None for key in required):
        raise ValueError("relay_dispatch_contract_incomplete")
    if b1_summary["target_dispatch_request_id"] != b1_summary["request_id"]:
        raise ValueError("relay_dispatch_contract_identity_mismatch")
    contract: dict[str, Any] = {
        "protocol": "lawb.bridge_relay_dispatch.v1",
        "relay_issue": b1_summary["configured_inbox_issue"],
        "relay_comment_id": str(b1_summary["inbox_comment_id"]),
        "relay_author": b1_summary["inbox_request_author"],
        "request_id": b1_summary["request_id"],
        "target_dispatch_request_id": b1_summary["target_dispatch_request_id"],
        "target_issue": b1_summary["target_issue"],
        "repo": b1_summary["target_repository"],
        "branch": b1_summary["expected_branch"],
        "head": b1_summary["expected_head"],
        "expires": b1_summary["expires"],
        "action": b1_summary["requested_action"],
        "requested_by": "chatgpt",
    }
    expected_state = b1_summary.get("target_expected_state")
    if expected_state is not None:
        contract["expected_state"] = expected_state
    return contract


def build_dispatcher_preflight_command(
    *,
    repo_root: str | Path,
    target_repo_root: str | Path | None = None,
    required_action: str,
    repository: str = DEFAULT_REPOSITORY,
) -> list[str]:
    args = [
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
    target_root = Path(target_repo_root).resolve() if target_repo_root is not None else Path(repo_root).resolve()
    if target_root != Path(repo_root).resolve():
        args.extend(["-TargetRepoRoot", str(target_root)])
    return args


def default_dispatcher_invoker(
    *,
    args: list[str],
    cwd: str,
    timeout_seconds: int,
) -> DispatcherInvocationResult:
    child_environment = os.environ.copy()
    executable_name = PureWindowsPath(args[0]).name.casefold() if args else ""
    if executable_name == "powershell.exe":
        for key in tuple(child_environment):
            if key.casefold() == "psmodulepath":
                del child_environment[key]

    with tempfile.TemporaryFile(mode="w+b") as stdout_file, tempfile.TemporaryFile(
        mode="w+b"
    ) as stderr_file:
        process = subprocess.Popen(
            args,
            cwd=cwd,
            env=child_environment,
            stdout=stdout_file,
            stderr=stderr_file,
        )
        try:
            process_identity = capture_process_identity(process.pid)
        except LifecycleEvidenceError:
            process_identity = None
        try:
            returncode = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            # The dispatcher synchronously owns Runner/Codex. Killing only this
            # immediate process would orphan work and manufacture a terminal
            # timeout. Leave the owned chain running and let B3 reconcile its
            # exact durable result instead.
            return DispatcherInvocationResult(
                returncode=1,
                timed_out=True,
                execution_reach=DISPATCHER_RUNNER_MAY_HAVE_STARTED,
                process_identity=process_identity,
            )
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout = stdout_file.read().decode("utf-8", errors="replace")
        stderr = stderr_file.read().decode("utf-8", errors="replace")
    return DispatcherInvocationResult(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=False,
        execution_reach=_dispatcher_execution_reach(returncode),
        process_identity=process_identity,
    )


def _dispatcher_execution_reach(returncode: int) -> str | None:
    if returncode == DISPATCHER_REJECTED_BEFORE_RUNNER_EXIT_CODE:
        return DISPATCHER_REJECTED_BEFORE_RUNNER
    if returncode == DISPATCHER_RUNNER_REACH_UNCERTAIN_EXIT_CODE:
        return DISPATCHER_RUNNER_MAY_HAVE_STARTED
    if returncode == DISPATCHER_FAILED_BEFORE_RUNNER_EXIT_CODE:
        return DISPATCHER_FAILED_BEFORE_RUNNER
    return None


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
            codex_path_binding = _extract_nested_runner_codex_path(nested_runner)
            if codex_path_binding is None:
                return {
                    **base,
                    "reason": "tool_resolution_preflight_nested_runner_codex_missing_selected_path",
                    "payload": payload,
                }

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
    return {
        "ok": True,
        "reason": "none",
        "structured_blocked": False,
        "payload": payload,
        "codex_path_binding": _extract_nested_runner_codex_path(payload.get("nested_runner")),
    }


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
    codex_path = _extract_nested_runner_codex_path(payload)
    if codex_path is None:
        return "codex_missing_selected_path"
    if not _is_absolute_windows_path(codex_path):
        return "codex_selected_path_not_absolute"
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


def _extract_nested_runner_codex_path(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    tools = payload.get("tools")
    if not isinstance(tools, dict):
        return None
    codex = tools.get("codex")
    if not isinstance(codex, dict):
        return None
    selected_path = codex.get("selected_path")
    if not isinstance(selected_path, str) or not selected_path.strip():
        return None
    return selected_path.strip()


def _is_absolute_windows_path(path: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:[\\/]", path) or re.match(r"^\\\\[^\\]+\\[^\\]+\\", path))


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


def _base_summary(
    repository: str,
    inbox_issue: int,
    control_repo_root: str | Path,
    target_repo_root: str | Path,
) -> dict[str, Any]:
    return {
        "protocol": SUMMARY_PROTOCOL,
        "phase": "preflight",
        "result": "blocked",
        "repository": repository,
        "control_repository": DEFAULT_REPOSITORY,
        "target_repository": repository,
        "control_repo_root": str(control_repo_root),
        "target_repo_root": str(target_repo_root),
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
        "dispatcher_execution_reach": None,
        "target_result_verified": False,
        "target_result_comment_id": None,
        "target_result_author": None,
        "delegation_result": "blocked",
        "unresolved_reason": None,
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
    codex_path_binding = validation.get("codex_path_binding")
    summary["tool_resolution_preflight_codex_path_binding"] = (
        codex_path_binding if isinstance(codex_path_binding, str) and codex_path_binding.strip() else None
    )
    summary["dispatcher_codex_path_binding_propagated"] = isinstance(codex_path_binding, str) and bool(codex_path_binding.strip())


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


def _unresolved(summary: dict[str, Any], reason: str) -> None:
    summary["result"] = "unresolved"
    summary["phase"] = "awaiting_reconciliation"
    summary["unresolved_reason"] = reason
    summary["next_recommended_action"] = "reconcile_exact_durable_result"

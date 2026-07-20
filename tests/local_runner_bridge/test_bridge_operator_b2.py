import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import local_runner_bridge.bridge_operator_b2 as b2
from local_runner_bridge.bridge_operator_b1 import CommentRecord, IssueRecord, LocalReadiness
from local_runner_bridge.bridge_operator_b2 import (
    DispatcherInvocationResult,
    build_dispatcher_command,
    build_dispatcher_preflight_command,
    parse_lawbrunner_result_comment,
    run_bridge_operator_b2_once,
)

NOW = datetime(2026, 6, 15, 1, 0, 0, tzinfo=timezone.utc)
HEAD = "590bacc7e5f91c97a6ae427df56baff17ae716db"
ROOT_PATH = r"C:\Users\harry\Desktop\project\local-ai-workbench"


def inbox_marker(**overrides):
    fields = {
        "protocol": "lawb.bridge_inbox_request.v1",
        "request_id": "b2-148-20260615T010000Z",
        "repo": "HarryWhite-TW/local-ai-workbench",
        "target_issue": "148",
        "target_dispatch_request_id": "dispatch-148",
        "branch": "feature/bridge-operator-b2",
        "head": HEAD,
        "expires": "20260616T010000Z",
        "action": "maybe-status-check",
        "requested_by": "chatgpt",
    }
    fields.update(overrides)
    return "BRIDGE-INBOX-REQUEST " + " ".join(
        f"{key}={value}" for key, value in fields.items()
    )


def dispatch_marker(**overrides):
    fields = {
        "protocol": "lawb.dispatch.v1",
        "action": "maybe-status-check",
        "issue": "148",
        "repo": "HarryWhite-TW/local-ai-workbench",
        "branch": "feature/bridge-operator-b2",
        "head": HEAD,
        "expires": "20260616T010000Z",
        "requested_by": "chatgpt",
        "request_id": "dispatch-148",
    }
    fields.update(overrides)
    return "CHATGPT-DISPATCH " + " ".join(
        f"{key}={value}" for key, value in fields.items()
    )


def result_comment(**overrides):
    payload = {
        "schema": "lawb.runner_result.v1",
        "repo": "HarryWhite-TW/local-ai-workbench",
        "issue": 148,
        "action": "maybe-status-check",
        "result": "success",
        "branch": "feature/bridge-operator-b2",
        "head": HEAD,
        "request_id": "dispatch-148",
    }
    payload.update(overrides)
    import json

    return "LAWBRUNNER-RESULT protocol=lawb.runner_result.v1\n" + json.dumps(payload)


def tool_entry(path=r"C:\Tools\gh.exe", suffix=".exe", **overrides):
    entry = {
        "selected_path": path,
        "suffix": suffix,
        "selection_source": "path",
        "version_probe": {
            "executed": True,
            "exit_code": 0,
            "ok": True,
            "safe_message": "ok",
        },
    }
    entry.update(overrides)
    return entry


def nested_runner_payload(**overrides):
    payload = {
        "protocol": "lawb.rv2_03_tool_resolution_preflight.v1",
        "component": "runner",
        "result": "success",
        "required_action": "run-reviewbundle",
        "blocked_reasons": [],
        "tools": {
            "runner_gh": tool_entry(r"C:\Tools\gh.exe"),
            "codex": tool_entry(r"C:\Tools\codex.cmd", ".cmd"),
        },
        "nested_runner": None,
        "safety": safety_flags(),
    }
    payload.update(overrides)
    return payload


def safety_flags(**overrides):
    values = {
        "pollonce_invoked": False,
        "dispatcher_action_executed": False,
        "github_issue_read_performed": False,
        "github_write_performed": False,
        "runner_work_invoked": False,
        "codex_task_executed": False,
    }
    values.update(overrides)
    return values


def preflight_payload(**overrides):
    payload = {
        "protocol": "lawb.rv2_03_tool_resolution_preflight.v1",
        "component": "dispatcher",
        "result": "success",
        "required_action": "maybe-status-check",
        "blocked_reasons": [],
        "tools": {"dispatcher_gh": tool_entry()},
        "nested_runner": None,
        "safety": safety_flags(),
    }
    payload.update(overrides)
    import json

    return json.dumps(payload)


class FakeGitHub:
    def __init__(
        self,
        *,
        inbox_comments=None,
        target_comments_before=None,
        target_comments_after=None,
        target_state="open",
    ):
        self.inbox_comments = inbox_comments if inbox_comments is not None else [
            CommentRecord(id=1, body=inbox_marker(), author="HarryWhite-TW")
        ]
        self.target_comments_before = (
            target_comments_before
            if target_comments_before is not None
            else [CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW")]
        )
        self.target_comments_after = (
            target_comments_after
            if target_comments_after is not None
            else [
                CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW"),
                CommentRecord(id=20, body=result_comment(), author="HarryWhite-TW"),
            ]
        )
        self.target_state = target_state
        self.target_comment_reads = 0
        self.issues_read = []

    def get_issue(self, issue_number):
        self.issues_read.append(issue_number)
        if issue_number == 147:
            return IssueRecord(number=147, state="open", body="")
        return IssueRecord(number=issue_number, state=self.target_state, body="")

    def list_issue_comments(self, issue_number):
        if issue_number == 147:
            return self.inbox_comments
        self.target_comment_reads += 1
        if self.target_comment_reads <= 2:
            return self.target_comments_before
        return self.target_comments_after


def ready(**overrides):
    values = {
        "repo_root": str(Path(ROOT_PATH).resolve()),
        "branch": "feature/bridge-operator-b2",
        "head": HEAD,
        "clean": True,
        "gh_available": True,
        "gh_authenticated": True,
        "gh_read_available": True,
        "errors": (),
    }
    values.update(overrides)
    return LocalReadiness(**values)


def assert_safety(summary):
    assert summary["broad_issue_scan_performed"] is False
    assert summary["latest_next_inference_performed"] is False
    assert summary["retry_performed"] is False
    assert summary["loop_started"] is False
    assert summary["background_service_started"] is False
    assert summary["commit_performed"] is False
    assert summary["push_performed"] is False
    assert summary["issue_closed"] is False
    assert summary["label_changed"] is False
    assert summary["pr_created"] is False
    assert summary["merge_performed"] is False
    assert summary["branch_deleted"] is False
    assert summary["approval_consumed"] is False


def run(client, invoker=None, readiness=None, preflight_invoker=None, **kwargs):
    return run_bridge_operator_b2_once(
        repo_root=ROOT_PATH,
        github_client=client,
        local_checker=lambda root: readiness or ready(),
        preflight_invoker=preflight_invoker
        or (lambda **_: DispatcherInvocationResult(0, preflight_payload(), "")),
        dispatcher_invoker=invoker or (lambda **_: DispatcherInvocationResult(0, "ok", "")),
        now_utc=NOW,
        timeout_seconds=30,
        **kwargs,
    )


def test_success_invokes_dispatcher_once_and_verifies_matching_result():
    calls = []
    preflight_calls = []

    def invoker(**kwargs):
        calls.append(kwargs)
        return DispatcherInvocationResult(returncode=0, stdout="中文 stdout", stderr="")

    def preflight_invoker(**kwargs):
        preflight_calls.append(kwargs)
        return DispatcherInvocationResult(returncode=0, stdout=preflight_payload(), stderr="")

    summary = run(FakeGitHub(), invoker, preflight_invoker=preflight_invoker)

    assert summary["result"] == "success"
    assert summary["configured_inbox_issue"] == 147
    assert summary["target_issue"] == 148
    assert summary["target_dispatch_request_id"] == "dispatch-148"
    assert summary["tool_resolution_preflight_invoked"] is True
    assert summary["tool_resolution_preflight_invocation_count"] == 1
    assert summary["tool_resolution_preflight_result"] == "success"
    assert summary["dispatcher_invoked"] is True
    assert summary["dispatcher_invocation_count"] == 1
    assert summary["dispatcher_stdout"] == "中文 stdout"
    assert summary["target_result_verified"] is True
    assert summary["target_result_comment_id"] == 20
    assert preflight_calls[0]["args"] == build_dispatcher_preflight_command(
        repo_root=ROOT_PATH,
        required_action="maybe-status-check",
        repository="HarryWhite-TW/local-ai-workbench",
    )
    assert calls[0]["args"] == build_dispatcher_command(
        repo_root=ROOT_PATH,
        target_issue=148,
        repository="HarryWhite-TW/local-ai-workbench",
    )
    assert summary["tool_resolution_preflight_codex_path_binding"] is None
    assert summary["dispatcher_codex_path_binding_propagated"] is False
    assert "-BoundedPoll" not in calls[0]["args"]
    assert "-DryRunBoundedPoll" not in calls[0]["args"]
    assert_safety(summary)


def test_run_reviewbundle_preflight_propagates_action_before_dispatch():
    calls = []
    preflight_calls = []
    client = FakeGitHub(
        inbox_comments=[CommentRecord(id=1, body=inbox_marker(action="run-reviewbundle"), author="HarryWhite-TW")],
        target_comments_before=[
            CommentRecord(id=10, body=dispatch_marker(action="run-reviewbundle"), author="HarryWhite-TW")
        ],
        target_comments_after=[
            CommentRecord(id=10, body=dispatch_marker(action="run-reviewbundle"), author="HarryWhite-TW"),
            CommentRecord(id=20, body=result_comment(action="run-reviewbundle"), author="HarryWhite-TW"),
        ],
    )

    def preflight_invoker(**kwargs):
        preflight_calls.append(kwargs)
        return DispatcherInvocationResult(
            returncode=0,
            stdout=preflight_payload(required_action="run-reviewbundle", nested_runner=nested_runner_payload()),
            stderr="",
        )

    summary = run(
        client,
        lambda **kwargs: calls.append(kwargs) or DispatcherInvocationResult(0, "ok", ""),
        preflight_invoker=preflight_invoker,
    )

    assert summary["result"] == "success"
    assert preflight_calls[0]["args"] == build_dispatcher_preflight_command(
        repo_root=ROOT_PATH,
        required_action="run-reviewbundle",
        repository="HarryWhite-TW/local-ai-workbench",
    )
    assert calls[0]["args"] == build_dispatcher_command(
        repo_root=ROOT_PATH,
        target_issue=148,
        repository="HarryWhite-TW/local-ai-workbench",
        reviewed_codex_path=r"C:\Tools\codex.cmd",
    )
    assert summary["tool_resolution_preflight_codex_path_binding"] == r"C:\Tools\codex.cmd"
    assert summary["dispatcher_codex_path_binding_propagated"] is True


def test_b1_blocked_does_not_invoke_dispatcher():
    calls = []
    preflight_calls = []
    client = FakeGitHub(inbox_comments=[])

    summary = run(
        client,
        lambda **kwargs: calls.append(kwargs),
        preflight_invoker=lambda **kwargs: preflight_calls.append(kwargs),
    )

    assert summary["result"] == "blocked"
    assert "b1_validation_not_success" in summary["blocked_reasons"]
    assert summary["tool_resolution_preflight_invoked"] is False
    assert summary["dispatcher_invoked"] is False
    assert preflight_calls == []
    assert calls == []
    assert_safety(summary)


def test_structured_blocked_preflight_blocks_without_dispatch():
    calls = []
    summary = run(
        FakeGitHub(),
        lambda **kwargs: calls.append(kwargs),
        preflight_invoker=lambda **_: DispatcherInvocationResult(
            2,
            preflight_payload(result="blocked", blocked_reasons=["dispatcher_gh_unavailable"]),
            "",
        ),
    )

    assert summary["result"] == "blocked"
    assert summary["delegation_result"] == "blocked"
    assert "tool_resolution_preflight_blocked" in summary["blocked_reasons"]
    assert "dispatcher_gh_unavailable" in summary["blocked_reasons"]
    assert summary["dispatcher_invoked"] is False
    assert summary["dispatcher_invocation_count"] == 0
    assert summary["retry_performed"] is False
    assert isinstance(summary["tool_resolution_preflight_blocked_reasons"], list)
    assert calls == []


@pytest.mark.parametrize(
    ("invocation", "expected_reason"),
    [
        (DispatcherInvocationResult(1, preflight_payload(), "", timed_out=True), "tool_resolution_preflight_timeout"),
        (DispatcherInvocationResult(7, preflight_payload(), ""), "tool_resolution_preflight_nonzero_exit"),
        (DispatcherInvocationResult(0, "", ""), "tool_resolution_preflight_empty_stdout"),
        (DispatcherInvocationResult(0, "{", ""), "tool_resolution_preflight_malformed_json"),
        (DispatcherInvocationResult(0, "[]", ""), "tool_resolution_preflight_non_object_json"),
        (DispatcherInvocationResult(0, preflight_payload(protocol="wrong"), ""), "tool_resolution_preflight_wrong_protocol"),
        (DispatcherInvocationResult(0, preflight_payload(component="runner"), ""), "tool_resolution_preflight_wrong_component"),
        (DispatcherInvocationResult(0, preflight_payload(required_action="run-reviewbundle"), ""), "tool_resolution_preflight_wrong_required_action"),
        (DispatcherInvocationResult(0, preflight_payload(result="blocked", blocked_reasons=["missing"]), ""), "tool_resolution_preflight_blocked_exit_mismatch"),
        (DispatcherInvocationResult(2, preflight_payload(), ""), "tool_resolution_preflight_success_exit_mismatch"),
        (DispatcherInvocationResult(2, preflight_payload(result="blocked", blocked_reasons=None), ""), "tool_resolution_preflight_invalid_blocked_reasons"),
        (DispatcherInvocationResult(2, preflight_payload(result="blocked", blocked_reasons="missing"), ""), "tool_resolution_preflight_invalid_blocked_reasons"),
        (DispatcherInvocationResult(2, preflight_payload(result="blocked", blocked_reasons=[7]), ""), "tool_resolution_preflight_invalid_blocked_reasons"),
        (DispatcherInvocationResult(0, preflight_payload(blocked_reasons=["unexpected"]), ""), "tool_resolution_preflight_success_with_blocked_reasons"),
        (DispatcherInvocationResult(2, preflight_payload(result="blocked", blocked_reasons=[]), ""), "tool_resolution_preflight_blocked_without_reasons"),
        (DispatcherInvocationResult(0, preflight_payload(tools=None), ""), "tool_resolution_preflight_missing_tools"),
        (DispatcherInvocationResult(0, preflight_payload(tools={}), ""), "tool_resolution_preflight_dispatcher_gh_missing"),
        (DispatcherInvocationResult(0, preflight_payload(tools={"codex": tool_entry(r"C:\Tools\codex.exe")}), ""), "tool_resolution_preflight_dispatcher_gh_missing"),
        (DispatcherInvocationResult(0, preflight_payload(tools={"dispatcher_gh": tool_entry(version_probe=None)}), ""), "tool_resolution_preflight_dispatcher_gh_missing_version_probe"),
        (
            DispatcherInvocationResult(
                0,
                preflight_payload(tools={"dispatcher_gh": tool_entry(version_probe={"executed": True, "exit_code": 0, "ok": False, "safe_message": "ok"})}),
                "",
            ),
            "tool_resolution_preflight_dispatcher_gh_version_probe_not_ok",
        ),
        (
            DispatcherInvocationResult(
                0,
                preflight_payload(tools={"dispatcher_gh": tool_entry(version_probe={"executed": True, "exit_code": 1, "ok": True, "safe_message": "ok"})}),
                "",
            ),
            "tool_resolution_preflight_dispatcher_gh_version_probe_nonzero_exit",
        ),
        (DispatcherInvocationResult(0, preflight_payload(tools={"dispatcher_gh": tool_entry(r"C:\Tools\gh.ps1", ".ps1")}), ""), "tool_resolution_preflight_dispatcher_gh_unsafe_suffix"),
        (DispatcherInvocationResult(0, preflight_payload(tools={"dispatcher_gh": tool_entry(r"C:\Tools\gh.exe", ".cmd")}), ""), "tool_resolution_preflight_dispatcher_gh_suffix_path_mismatch"),
        (DispatcherInvocationResult(2, preflight_payload(result="blocked", blocked_reasons=["   "]), ""), "tool_resolution_preflight_invalid_blocked_reasons"),
        (DispatcherInvocationResult(0, preflight_payload(nested_runner=nested_runner_payload()), ""), "tool_resolution_preflight_unexpected_nested_runner"),
        (DispatcherInvocationResult(0, preflight_payload(required_action="run-reviewbundle"), ""), "tool_resolution_preflight_nested_runner_missing"),
        (
            DispatcherInvocationResult(
                0,
                preflight_payload(
                    required_action="run-reviewbundle",
                    nested_runner=nested_runner_payload(
                        tools={
                            "runner_gh": tool_entry(),
                            "codex": tool_entry("codex.cmd", ".cmd"),
                        }
                    ),
                ),
                "",
            ),
            "tool_resolution_preflight_nested_runner_codex_selected_path_not_absolute",
        ),
        (
            DispatcherInvocationResult(
                0,
                preflight_payload(required_action="run-reviewbundle", nested_runner=nested_runner_payload(tools={"codex": tool_entry(r"C:\Tools\codex.exe")})),
                "",
            ),
            "tool_resolution_preflight_nested_runner_runner_gh_missing",
        ),
        (
            DispatcherInvocationResult(
                0,
                preflight_payload(required_action="run-reviewbundle", nested_runner=nested_runner_payload(tools={"runner_gh": tool_entry()})),
                "",
            ),
            "tool_resolution_preflight_nested_runner_codex_missing",
        ),
        (
            DispatcherInvocationResult(
                0,
                preflight_payload(
                    required_action="run-reviewbundle",
                    nested_runner=nested_runner_payload(
                        tools={
                            "runner_gh": tool_entry(version_probe={"executed": True, "exit_code": 1, "ok": False, "safe_message": "version_probe_failed"}),
                            "codex": tool_entry(r"C:\Tools\codex.exe"),
                        }
                    ),
                ),
                "",
            ),
            "tool_resolution_preflight_nested_runner_runner_gh_version_probe_nonzero_exit",
        ),
        (
            DispatcherInvocationResult(0, preflight_payload(safety=safety_flags(pollonce_invoked=True)), ""),
            "tool_resolution_preflight_safety_contradiction_pollonce_invoked",
        ),
        (
            DispatcherInvocationResult(0, preflight_payload(safety=safety_flags(github_write_performed=True)), ""),
            "tool_resolution_preflight_safety_contradiction_github_write_performed",
        ),
        (
            DispatcherInvocationResult(0, preflight_payload(safety=safety_flags(codex_task_executed=True)), ""),
            "tool_resolution_preflight_safety_contradiction_codex_task_executed",
        ),
    ],
)

def test_preflight_contract_failures_do_not_invoke_dispatcher(invocation, expected_reason):
    calls = []
    client = FakeGitHub()
    if expected_reason.startswith("tool_resolution_preflight_nested_runner_"):
        client = FakeGitHub(
            inbox_comments=[CommentRecord(id=1, body=inbox_marker(action="run-reviewbundle"), author="HarryWhite-TW")],
            target_comments_before=[
                CommentRecord(id=10, body=dispatch_marker(action="run-reviewbundle"), author="HarryWhite-TW")
            ],
        )
    summary = run(
        client,
        lambda **kwargs: calls.append(kwargs),
        preflight_invoker=lambda **_: invocation,
    )

    assert summary["result"] == "failure"
    assert summary["delegation_result"] == "failure"
    assert summary["blocked_reasons"] == [expected_reason]
    assert summary["dispatcher_invoked"] is False
    assert summary["dispatcher_invocation_count"] == 0
    assert summary["retry_performed"] is False
    assert isinstance(summary["tool_resolution_preflight_blocked_reasons"], list)
    assert calls == []


def test_fixed_inbox_and_repository_are_not_overridable():
    assert run(FakeGitHub(), inbox_issue=999)["blocked_reasons"] == ["unsupported_inbox_issue"]
    assert run(FakeGitHub(), repository="other/repo")["blocked_reasons"] == [
        "unsupported_target_repository"
    ]


def test_preexisting_matching_result_blocks_without_dispatch():
    calls = []
    preflight_calls = []
    comments = [
        CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW"),
        CommentRecord(id=20, body=result_comment(), author="HarryWhite-TW"),
    ]

    summary = run(
        FakeGitHub(target_comments_before=comments),
        lambda **kwargs: calls.append(kwargs),
        preflight_invoker=lambda **kwargs: preflight_calls.append(kwargs),
    )

    assert summary["result"] == "blocked"
    assert summary["matching_result_preexisting"] is True
    assert summary["blocked_reasons"] == ["matching_result_already_exists"]
    assert summary["tool_resolution_preflight_invoked"] is False
    assert summary["dispatcher_invoked"] is False
    assert preflight_calls == []
    assert calls == []
    assert_safety(summary)


def test_malformed_partial_and_mismatched_results_do_not_count_as_completion():
    comments_after = [
        CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW"),
        CommentRecord(id=20, body="LAWBRUNNER-RESULT protocol=lawb.runner_result.v1", author="HarryWhite-TW"),
        CommentRecord(id=21, body="LAWBRUNNER-RESULT protocol=lawb.runner_result.v1\n{", author="HarryWhite-TW"),
        CommentRecord(id=22, body=result_comment(request_id="other"), author="HarryWhite-TW"),
    ]

    summary = run(FakeGitHub(target_comments_after=comments_after))

    assert summary["result"] == "failure"
    assert summary["blocked_reasons"] == ["target_result_missing"]
    assert summary["target_result_verified"] is False
    assert_safety(summary)


def test_multiple_matching_results_fail_closed_after_dispatch():
    comments_after = [
        CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW"),
        CommentRecord(id=20, body=result_comment(), author="HarryWhite-TW"),
        CommentRecord(id=21, body=result_comment(), author="HarryWhite-TW"),
    ]

    summary = run(FakeGitHub(target_comments_after=comments_after))

    assert summary["result"] == "failure"
    assert summary["blocked_reasons"] == ["multiple_matching_results"]
    assert_safety(summary)


def test_dispatcher_nonzero_timeout_and_missing_result_are_failures():
    nonzero = run(
        FakeGitHub(),
        lambda **_: DispatcherInvocationResult(returncode=7, stderr="no"),
    )
    timeout = run(
        FakeGitHub(),
        lambda **_: DispatcherInvocationResult(returncode=1, timed_out=True),
    )
    missing = run(
        FakeGitHub(target_comments_after=[CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW")])
    )

    assert nonzero["blocked_reasons"] == ["dispatcher_nonzero_exit"]
    assert timeout["blocked_reasons"] == ["dispatcher_timeout"]
    assert missing["blocked_reasons"] == ["target_result_missing"]
    assert nonzero["dispatcher_invocation_count"] == 1
    assert timeout["dispatcher_invocation_count"] == 1
    assert missing["dispatcher_invocation_count"] == 1
    assert_safety(nonzero)
    assert_safety(timeout)
    assert_safety(missing)


def test_result_failure_untrusted_author_and_identity_mismatch_fail():
    failure = run(
        FakeGitHub(
            target_comments_after=[
                CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW"),
                CommentRecord(id=20, body=result_comment(result="failure"), author="HarryWhite-TW"),
            ]
        )
    )
    untrusted = run(
        FakeGitHub(
            target_comments_after=[
                CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW"),
                CommentRecord(id=20, body=result_comment(), author="other-user"),
            ]
        )
    )
    mismatch = run(
        FakeGitHub(
            target_comments_after=[
                CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW"),
                CommentRecord(id=20, body=result_comment(branch="other"), author="HarryWhite-TW"),
            ]
        )
    )

    assert failure["blocked_reasons"] == ["target_result_not_success"]
    assert untrusted["blocked_reasons"] == ["untrusted_result_author"]
    assert mismatch["blocked_reasons"] == ["target_result_missing"]
    assert_safety(failure)
    assert_safety(untrusted)
    assert_safety(mismatch)


def test_parse_result_requires_marker_protocol_and_json_schema():
    valid = parse_lawbrunner_result_comment(
        CommentRecord(id=1, body=result_comment(), author="HarryWhite-TW")
    )
    wrong_schema = parse_lawbrunner_result_comment(
        CommentRecord(id=2, body=result_comment(schema="other"), author="HarryWhite-TW")
    )
    nearby = parse_lawbrunner_result_comment(
        CommentRecord(id=3, body="plain text", author="HarryWhite-TW")
    )

    assert valid["result"] == "success"
    assert wrong_schema["result"] == "identity_mismatch"
    assert nearby["result"] == "not_result"


def test_default_invoker_uses_utf8_replacement_decoding(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return b2.subprocess.CompletedProcess(command, 0, stdout="中文", stderr="")

    monkeypatch.setattr(b2.subprocess, "run", fake_run)

    result = b2.default_dispatcher_invoker(
        args=["powershell.exe", "-File", "script.ps1"],
        cwd=ROOT_PATH,
        timeout_seconds=12,
    )

    assert result.returncode == 0
    assert result.stdout == "中文"
    assert calls[0][1]["encoding"] == "utf-8"
    assert calls[0][1]["errors"] == "replace"
    assert calls[0][1]["timeout"] == 12


def test_default_invoker_removes_powershell_module_path_from_child_only(monkeypatch):
    calls = []
    monkeypatch.setenv("PSModulePath", "inherited-powershell-7-modules")
    monkeypatch.setenv("BRIDGE_ENV_SENTINEL", "preserved")

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return b2.subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(b2.subprocess, "run", fake_run)

    result = b2.default_dispatcher_invoker(
        args=[
            r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
            "-File",
            "probe.ps1",
        ],
        cwd=ROOT_PATH,
        timeout_seconds=12,
    )

    child_environment = calls[0][1]["env"]
    assert result.returncode == 0
    assert all(key.casefold() != "psmodulepath" for key in child_environment)
    assert child_environment["BRIDGE_ENV_SENTINEL"] == "preserved"
    assert os.environ["PSModulePath"] == "inherited-powershell-7-modules"
    assert os.environ["BRIDGE_ENV_SENTINEL"] == "preserved"


@pytest.mark.parametrize("executable", ["pwsh.exe", "unrelated-tool.exe"])
def test_default_invoker_preserves_module_path_for_other_executables(
    monkeypatch, executable
):
    calls = []
    monkeypatch.setenv("PSModulePath", "parent-module-path")

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return b2.subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(b2.subprocess, "run", fake_run)

    result = b2.default_dispatcher_invoker(
        args=[executable, "--version"],
        cwd=ROOT_PATH,
        timeout_seconds=12,
    )

    assert result.returncode == 0
    child_module_paths = [
        value
        for key, value in calls[0][1]["env"].items()
        if key.casefold() == "psmodulepath"
    ]
    assert child_module_paths == ["parent-module-path"]
    assert os.environ["PSModulePath"] == "parent-module-path"


def test_default_invoker_windows_powershell_restores_native_module_discovery(
    monkeypatch, tmp_path
):
    if os.name != "nt":
        pytest.skip("Windows PowerShell integration regression requires Windows")
    powershell = shutil.which("powershell.exe")
    if powershell is None:
        pytest.skip("Windows PowerShell powershell.exe is unavailable")

    incompatible_modules = tmp_path / "incompatible-powershell-modules"
    incompatible_modules.mkdir()
    monkeypatch.setenv("PSModulePath", str(incompatible_modules))
    probe = tmp_path / "windows_powershell_module_probe.ps1"
    probe.write_text(
        """$ErrorActionPreference = "Stop"
$temporaryFile = $null
try {
    $temporaryFile = New-TemporaryFile
    if (-not (Test-Path -LiteralPath $temporaryFile.FullName -PathType Leaf)) {
        throw "New-TemporaryFile did not create a file."
    }
    Write-Output "WINDOWS_POWERSHELL_TEMPFILE_OK"
}
finally {
    if ($null -ne $temporaryFile -and (Test-Path -LiteralPath $temporaryFile.FullName)) {
        Remove-Item -LiteralPath $temporaryFile.FullName -Force
    }
}
""",
        encoding="utf-8-sig",
    )

    result = b2.default_dispatcher_invoker(
        args=[
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(probe),
        ],
        cwd=str(tmp_path),
        timeout_seconds=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "WINDOWS_POWERSHELL_TEMPFILE_OK" in result.stdout
    assert os.environ["PSModulePath"] == str(incompatible_modules)


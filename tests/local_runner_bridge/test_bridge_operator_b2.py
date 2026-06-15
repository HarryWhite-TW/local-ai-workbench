import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import local_runner_bridge.bridge_operator_b2 as b2
from local_runner_bridge.bridge_operator_b1 import CommentRecord, IssueRecord, LocalReadiness
from local_runner_bridge.bridge_operator_b2 import (
    DispatcherInvocationResult,
    build_dispatcher_command,
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


def run(client, invoker=None, readiness=None, **kwargs):
    return run_bridge_operator_b2_once(
        repo_root=ROOT_PATH,
        github_client=client,
        local_checker=lambda root: readiness or ready(),
        dispatcher_invoker=invoker or (lambda **_: DispatcherInvocationResult(0, "ok", "")),
        now_utc=NOW,
        timeout_seconds=30,
        **kwargs,
    )


def test_success_invokes_dispatcher_once_and_verifies_matching_result():
    calls = []

    def invoker(**kwargs):
        calls.append(kwargs)
        return DispatcherInvocationResult(returncode=0, stdout="中文 stdout", stderr="")

    summary = run(FakeGitHub(), invoker)

    assert summary["result"] == "success"
    assert summary["configured_inbox_issue"] == 147
    assert summary["target_issue"] == 148
    assert summary["target_dispatch_request_id"] == "dispatch-148"
    assert summary["dispatcher_invoked"] is True
    assert summary["dispatcher_invocation_count"] == 1
    assert summary["dispatcher_stdout"] == "中文 stdout"
    assert summary["target_result_verified"] is True
    assert summary["target_result_comment_id"] == 20
    assert calls[0]["args"] == build_dispatcher_command(
        repo_root=ROOT_PATH,
        target_issue=148,
        repository="HarryWhite-TW/local-ai-workbench",
    )
    assert "-BoundedPoll" not in calls[0]["args"]
    assert "-DryRunBoundedPoll" not in calls[0]["args"]
    assert_safety(summary)


def test_b1_blocked_does_not_invoke_dispatcher():
    calls = []
    client = FakeGitHub(inbox_comments=[])

    summary = run(client, lambda **kwargs: calls.append(kwargs))

    assert summary["result"] == "blocked"
    assert "b1_validation_not_success" in summary["blocked_reasons"]
    assert summary["dispatcher_invoked"] is False
    assert calls == []
    assert_safety(summary)


def test_fixed_inbox_and_repository_are_not_overridable():
    assert run(FakeGitHub(), inbox_issue=999)["blocked_reasons"] == ["unsupported_inbox_issue"]
    assert run(FakeGitHub(), repository="other/repo")["blocked_reasons"] == ["unsupported_repository"]


def test_preexisting_matching_result_blocks_without_dispatch():
    calls = []
    comments = [
        CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW"),
        CommentRecord(id=20, body=result_comment(), author="HarryWhite-TW"),
    ]

    summary = run(
        FakeGitHub(target_comments_before=comments),
        lambda **kwargs: calls.append(kwargs),
    )

    assert summary["result"] == "blocked"
    assert summary["matching_result_preexisting"] is True
    assert summary["blocked_reasons"] == ["matching_result_already_exists"]
    assert summary["dispatcher_invoked"] is False
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


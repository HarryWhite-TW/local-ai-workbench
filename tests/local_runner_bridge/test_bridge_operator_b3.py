import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from local_runner_bridge.bridge_operator_b1 import CommentRecord, IssueRecord, LocalReadiness
from local_runner_bridge.bridge_operator_b3 import (
    B3B_MODE,
    B3C_MODE,
    DEFAULT_INBOX_ISSUE,
    run_bridge_operator_b3_dry_run_loop,
)
from local_runner_bridge.bridge_operator_b2 import DispatcherInvocationResult

NOW = datetime(2026, 6, 16, 8, 0, 0, tzinfo=timezone.utc)
HEAD = "3aedc4925e9da241429a7905418b6a815fd9ee37"
ROOT_PATH = r"C:\Users\admin\Desktop\local-ai-workbench-course"


def inbox_marker(**overrides):
    fields = {
        "protocol": "lawb.bridge_inbox_request.v1",
        "request_id": "b3a-151-20260616T080000Z",
        "repo": "HarryWhite-TW/local-ai-workbench",
        "target_issue": "151",
        "target_dispatch_request_id": "dispatch-151",
        "branch": "feature/bridge-operator-b3a",
        "head": HEAD,
        "expires": "20260617T080000Z",
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
        "issue": "151",
        "repo": "HarryWhite-TW/local-ai-workbench",
        "branch": "feature/bridge-operator-b3a",
        "head": HEAD,
        "expires": "20260617T080000Z",
        "requested_by": "chatgpt",
        "request_id": "dispatch-151",
    }
    fields.update(overrides)
    return "CHATGPT-DISPATCH " + " ".join(
        f"{key}={value}" for key, value in fields.items()
    )


def result_comment(**overrides):
    fields = {
        "schema": "lawb.runner_result.v1",
        "repo": "HarryWhite-TW/local-ai-workbench",
        "issue": 151,
        "action": "maybe-status-check",
        "result": "success",
        "branch": "feature/bridge-operator-b3a",
        "head": HEAD,
        "request_id": "dispatch-151",
    }
    fields.update(overrides)
    return "LAWBRUNNER-RESULT protocol=lawb.runner_result.v1\n" + json.dumps(fields)


class FakeGitHub:
    def __init__(self, *, inbox_comments=None, target_comments=None, fail_reads=False):
        self.inbox_comments = inbox_comments if inbox_comments is not None else [
            CommentRecord(id=1, body=inbox_marker(), author="HarryWhite-TW")
        ]
        self.target_comments = target_comments if target_comments is not None else [
            CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW")
        ]
        self.fail_reads = fail_reads
        self.issues_read = []
        self.comments_read = []

    def get_issue(self, issue_number):
        self.issues_read.append(issue_number)
        if self.fail_reads:
            raise RuntimeError("network")
        if issue_number == DEFAULT_INBOX_ISSUE:
            return IssueRecord(number=DEFAULT_INBOX_ISSUE, state="open", body="")
        return IssueRecord(number=issue_number, state="open", body="")

    def list_issue_comments(self, issue_number):
        self.comments_read.append(issue_number)
        if self.fail_reads:
            raise RuntimeError("network")
        if issue_number == DEFAULT_INBOX_ISSUE:
            return self.inbox_comments
        return self.target_comments


def ready(state_dir=None, *, assert_lock=False, **overrides):
    def checker(root):
        if assert_lock:
            assert (Path(state_dir) / "operator.lock").exists()
        values = {
            "repo_root": str(Path(ROOT_PATH).resolve()),
            "branch": "feature/bridge-operator-b3a",
            "head": HEAD,
            "clean": True,
            "gh_available": True,
            "gh_authenticated": True,
            "gh_read_available": True,
            "errors": (),
        }
        values.update(overrides)
        return LocalReadiness(**values)

    return checker


def run(tmp_path, client=None, readiness=None, **kwargs):
    return run_bridge_operator_b3_dry_run_loop(
        repo_root=ROOT_PATH,
        state_dir=tmp_path,
        github_client=client or FakeGitHub(),
        local_checker=readiness or ready(tmp_path),
        now_utc=NOW,
        sleeper=lambda seconds: None,
        **kwargs,
    )


def run_b3b(tmp_path, client=None, readiness=None, dispatcher_invoker=None, **kwargs):
    return run_bridge_operator_b3_dry_run_loop(
        repo_root=ROOT_PATH,
        state_dir=tmp_path,
        github_client=client or FakeGitHub(
            target_comments=[
                CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW"),
                CommentRecord(id=20, body=result_comment(), author="HarryWhite-TW"),
            ]
        ),
        local_checker=readiness or ready(tmp_path),
        now_utc=NOW,
        sleeper=lambda seconds: None,
        mode=B3B_MODE,
        dispatcher_invoker=dispatcher_invoker
        or (lambda **_: DispatcherInvocationResult(returncode=0, stdout="ok", stderr="")),
        timeout_seconds=30,
        **kwargs,
    )


def run_b3c(tmp_path, client=None, readiness=None, dispatcher_invoker=None, **kwargs):
    return run_bridge_operator_b3_dry_run_loop(
        repo_root=ROOT_PATH,
        state_dir=tmp_path,
        github_client=client or FakeGitHub(
            inbox_comments=[
                CommentRecord(
                    id=1,
                    body=inbox_marker(action="run-reviewbundle"),
                    author="HarryWhite-TW",
                )
            ],
            target_comments=[
                CommentRecord(
                    id=10,
                    body=dispatch_marker(action="run-reviewbundle"),
                    author="HarryWhite-TW",
                ),
                CommentRecord(
                    id=20,
                    body=result_comment(action="run-reviewbundle"),
                    author="HarryWhite-TW",
                ),
            ],
        ),
        local_checker=readiness or ready(tmp_path),
        now_utc=NOW,
        sleeper=lambda seconds: None,
        mode=B3C_MODE,
        dispatcher_invoker=dispatcher_invoker
        or (lambda **_: DispatcherInvocationResult(returncode=0, stdout="ok", stderr="")),
        timeout_seconds=30,
        **kwargs,
    )


def assert_safety(summary):
    assert summary["broad_issue_scan_performed"] is False
    assert summary["latest_next_inference_performed"] is False
    assert summary["dispatcher_invoked"] is False
    assert summary["dispatcher_invocation_count"] == 0
    assert summary["dispatcher_result_writeback_reached"] is False
    assert summary["dispatcher_result_writeback_verified"] is False
    assert summary["runner_invoked"] is False
    assert summary["codex_invoked"] is False
    assert summary["github_write_performed"] is False
    assert summary["background_service_started"] is False
    assert summary["commit_performed"] is False
    assert summary["push_performed"] is False
    assert summary["issue_closed"] is False
    assert summary["label_changed"] is False
    assert summary["pr_created"] is False
    assert summary["merge_performed"] is False
    assert summary["branch_deleted"] is False
    assert summary["approval_consumed"] is False


def assert_high_risk_safety(summary):
    assert summary["broad_issue_scan_performed"] is False
    assert summary["latest_next_inference_performed"] is False
    assert summary["runner_invoked"] is False
    assert summary["codex_invoked"] is False
    assert summary["github_write_performed"] is False
    assert summary["background_service_started"] is False
    assert summary["commit_performed"] is False
    assert summary["push_performed"] is False
    assert summary["issue_closed"] is False
    assert summary["label_changed"] is False
    assert summary["pr_created"] is False
    assert summary["merge_performed"] is False
    assert summary["branch_deleted"] is False
    assert summary["approval_consumed"] is False


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_log_events(path):
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def assert_b1_failure_blocks(tmp_path, summary, reason):
    assert summary["result"] == "blocked"
    assert reason in summary["blocked_reasons"]
    assert read_json(tmp_path / "last_failure.json")["reason"] == reason
    assert not (tmp_path / "dry_run_observations.jsonl").exists()
    assert not (tmp_path / "processed_requests.jsonl").exists()
    assert_safety(summary)


def test_dry_run_loop_observes_fixed_inbox_without_dispatcher(tmp_path):
    client = FakeGitHub()

    summary = run(tmp_path, client)

    assert summary["result"] == "success"
    assert summary["configured_inbox_issue"] == 147
    assert summary["eligible_request_observed"] is True
    assert summary["dry_run_observation_written"] is True
    assert summary["processed_request_written"] is False
    assert client.issues_read == [147, 151]
    assert client.comments_read == [147, 151]
    assert not (tmp_path / "processed_requests.jsonl").exists()
    observations = (tmp_path / "dry_run_observations.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(observations) == 1
    assert json.loads(observations[0])["request_id"] == "b3a-151-20260616T080000Z"
    assert_safety(summary)


def test_b3b_maybe_status_check_invokes_dispatcher_once_and_processes_request(tmp_path):
    calls = []

    def invoker(**kwargs):
        calls.append(kwargs)
        return DispatcherInvocationResult(returncode=0, stdout="dispatcher ok", stderr="")

    summary = run_b3b(tmp_path, dispatcher_invoker=invoker)

    assert summary["result"] == "success"
    assert summary["mode"] == "b3b-maybe-status-check"
    assert summary["dispatcher_invoked"] is True
    assert summary["dispatcher_invocation_count"] == 1
    assert summary["dispatcher_stdout"] == "dispatcher ok"
    assert summary["dispatcher_result_writeback_reached"] is True
    assert summary["dispatcher_result_writeback_verified"] is True
    assert summary["target_result_verified"] is True
    assert summary["operator_direct_execution_performed"] is True
    assert summary["current_run"] == {
        "request_id": "b3a-151-20260616T080000Z",
        "issue_number": 151,
        "mode": "b3b-maybe-status-check",
        "max_cycles": 1,
        "operator_dispatcher_invocation_performed": True,
        "dispatcher_invoked": True,
        "operator_direct_runner_invoked": False,
        "operator_direct_codex_invoked": False,
        "github_result_writeback_observed": True,
        "current_failure_recorded": False,
        "current_failure_reason": None,
        "last_failure_json_applies_to_current_run": False,
        "last_failure_json_status": "not_present",
    }
    assert summary["github_write_performed"] is False
    assert summary["processed_request_written"] is True
    assert calls[0]["args"][0] == "powershell.exe"
    assert "-PollOnce" in calls[0]["args"]
    assert "-PostResultComment" in calls[0]["args"]
    assert calls[0]["args"][calls[0]["args"].index("-IssueNumber") + 1] == "151"
    processed = (tmp_path / "processed_requests.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(processed) == 1
    assert json.loads(processed[0])["request_id"] == "b3a-151-20260616T080000Z"
    assert json.loads(processed[0])["lifecycle_state"] == "CONSUMED"
    log = read_log_events(tmp_path / "operator.log")[-1]
    assert log["dispatcher_invoked"] is True
    assert log["current_run"]["request_id"] == "b3a-151-20260616T080000Z"
    assert log["current_run"]["operator_dispatcher_invocation_performed"] is True
    assert log["dispatcher_result_writeback_reached"] is True
    assert log["dispatcher_result_writeback_verified"] is True
    assert log["github_write_performed"] is False
    assert not (tmp_path / "dry_run_observations.jsonl").exists()
    assert_high_risk_safety(summary)


def test_b3b_processed_a_plus_new_b_dispatches_only_b_and_appends_one_record(tmp_path):
    original = {
        "protocol": "lawb.bridge_operator_b3_processed_request.v1",
        "processed_at_utc": "2026-06-16T07:00:00Z",
        "cycle": 1,
        "request_id": "processed-a",
        "lifecycle_state": "CONSUMED",
    }
    (tmp_path / "processed_requests.jsonl").write_text(
        json.dumps(original, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    calls = []
    client = FakeGitHub(
        inbox_comments=[
            CommentRecord(id=1, body=inbox_marker(request_id="processed-a"), author="HarryWhite-TW"),
            CommentRecord(
                id=2,
                body=inbox_marker(request_id="current-b", target_dispatch_request_id="dispatch-b"),
                author="HarryWhite-TW",
            ),
        ],
        target_comments=[
            CommentRecord(id=10, body=dispatch_marker(request_id="dispatch-b"), author="HarryWhite-TW"),
            CommentRecord(id=20, body=result_comment(request_id="dispatch-b"), author="HarryWhite-TW"),
        ],
    )

    summary = run_b3b(
        tmp_path,
        client,
        dispatcher_invoker=lambda **kwargs: calls.append(kwargs)
        or DispatcherInvocationResult(returncode=0, stdout="ok", stderr=""),
    )

    assert summary["result"] == "success"
    assert summary["request_id"] == "current-b"
    assert summary["inbox_comment_id"] == 2
    assert summary["current_request_count"] == 1
    assert summary["consumed_request_count"] == 1
    assert summary["selected_request_state"] == "CURRENT"
    assert summary["dispatcher_invocation_count"] == 1
    assert calls[0]["args"][calls[0]["args"].index("-IssueNumber") + 1] == "151"
    processed = [
        json.loads(line)
        for line in (tmp_path / "processed_requests.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [record["request_id"] for record in processed] == ["processed-a", "current-b"]
    assert processed[1]["lifecycle_state"] == "CONSUMED"
    assert_high_risk_safety(summary)


def test_b3b_two_cycle_consumed_transition_clears_selected_current_lifecycle(tmp_path):
    calls = []

    summary = run_b3b(
        tmp_path,
        dispatcher_invoker=lambda **kwargs: calls.append(kwargs)
        or DispatcherInvocationResult(returncode=0, stdout="ok", stderr=""),
        max_cycles=2,
    )

    assert summary["result"] == "success"
    assert summary["dispatcher_invocation_count"] == 1
    assert summary["last_b1_blocked_reasons"] == ["no_current_request_after_consumption"]
    assert summary["current_request_count"] == 0
    assert summary["consumed_request_count"] == 1
    assert summary["selected_request_state"] is None
    assert summary["inbox_comment_id"] is None
    assert summary["expires"] is None
    assert summary["request_id"] == "b3a-151-20260616T080000Z"
    assert summary["target_issue"] == 151
    assert summary["current_run"]["request_id"] == "b3a-151-20260616T080000Z"
    assert summary["current_run"]["issue_number"] == 151
    assert summary["processed_request_written"] is True
    assert summary["current_failure_recorded"] is False
    assert len(calls) == 1
    processed = (tmp_path / "processed_requests.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(processed) == 1
    assert read_json(tmp_path / "state.json")["last_request_id"] == "b3a-151-20260616T080000Z"
    assert read_json(tmp_path / "heartbeat.json")["request_id"] == "b3a-151-20260616T080000Z"

    waiting_events = [
        event
        for event in read_log_events(tmp_path / "operator.log")
        if event["event"] == "waiting"
    ]
    assert waiting_events
    final_waiting = waiting_events[-1]
    assert final_waiting["reason"] == "no_eligible_current_request"
    assert final_waiting["current_request_count"] == 0
    assert final_waiting["consumed_request_count"] == 1
    assert final_waiting["selected_request_state"] is None
    assert final_waiting["request_id"] == "b3a-151-20260616T080000Z"
    assert_high_risk_safety(summary)


def test_b3b_consumed_only_inbox_is_safe_wait_without_dispatcher_or_failure(tmp_path):
    (tmp_path / "processed_requests.jsonl").write_text(
        json.dumps(
            {
                "protocol": "lawb.bridge_operator_b3_processed_request.v1",
                "request_id": "b3a-151-20260616T080000Z",
                "lifecycle_state": "CONSUMED",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    calls = []

    summary = run_b3b(tmp_path, dispatcher_invoker=lambda **kwargs: calls.append(kwargs))

    assert summary["result"] == "success"
    assert summary["last_b1_blocked_reasons"] == ["no_current_request_after_consumption"]
    assert summary["empty_or_blocked_cycles"] == 1
    assert summary["dispatcher_invoked"] is False
    assert summary["dispatcher_invocation_count"] == 0
    assert summary["current_request_count"] == 0
    assert summary["consumed_request_count"] == 1
    assert summary["selected_request_state"] is None
    assert summary["request_id"] is None
    assert summary["current_run"]["request_id"] is None
    assert calls == []
    assert not (tmp_path / "last_failure.json").exists()
    processed = (tmp_path / "processed_requests.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(processed) == 1
    assert_high_risk_safety(summary)


def test_b3c_run_reviewbundle_invokes_dispatcher_once_and_processes_request(tmp_path):
    calls = []

    def invoker(**kwargs):
        calls.append(kwargs)
        return DispatcherInvocationResult(returncode=0, stdout="dispatcher ok", stderr="")

    summary = run_b3c(tmp_path, dispatcher_invoker=invoker)

    assert summary["result"] == "success"
    assert summary["mode"] == "b3c-run-reviewbundle"
    assert summary["requested_action"] == "run-reviewbundle"
    assert summary["dispatcher_invoked"] is True
    assert summary["dispatcher_invocation_count"] == 1
    assert summary["dispatcher_result_writeback_reached"] is True
    assert summary["dispatcher_result_writeback_verified"] is True
    assert summary["target_result_verified"] is True
    assert summary["processed_request_written"] is True
    assert calls[0]["args"][0] == "powershell.exe"
    assert "-PollOnce" in calls[0]["args"]
    assert "-PostResultComment" in calls[0]["args"]
    assert calls[0]["args"][calls[0]["args"].index("-IssueNumber") + 1] == "151"
    command_text = " ".join(calls[0]["args"])
    assert "local_dispatcher_v1.ps1" in command_text
    assert "local_runner_v1.ps1" not in command_text
    assert "codex" not in command_text.lower()
    processed = (tmp_path / "processed_requests.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(processed) == 1
    payload = json.loads(processed[0])
    assert payload["request_id"] == "b3a-151-20260616T080000Z"
    assert payload["requested_action"] == "run-reviewbundle"
    assert payload["dispatcher_invoked"] is True
    assert payload["result_verified"] is True
    assert payload["lifecycle_state"] == "CONSUMED"
    assert_high_risk_safety(summary)


def test_b3a_dry_run_still_does_not_invoke_dispatcher_when_invoker_is_available(tmp_path):
    calls = []

    summary = run(
        tmp_path,
        dispatcher_invoker=lambda **kwargs: calls.append(kwargs),
    )

    assert summary["result"] == "success"
    assert summary["dispatcher_invoked"] is False
    assert calls == []
    assert_safety(summary)


def test_b3b_blocks_run_reviewbundle_before_dispatcher(tmp_path):
    calls = []
    comment = CommentRecord(
        id=1,
        body=inbox_marker(action="run-reviewbundle"),
        author="HarryWhite-TW",
    )
    target = CommentRecord(
        id=10,
        body=dispatch_marker(action="run-reviewbundle"),
        author="HarryWhite-TW",
    )

    summary = run_b3b(
        tmp_path,
        FakeGitHub(inbox_comments=[comment], target_comments=[target]),
        dispatcher_invoker=lambda **kwargs: calls.append(kwargs),
    )

    assert summary["result"] == "blocked"
    assert summary["blocked_reasons"] == ["run_reviewbundle_not_enabled_in_b3b"]
    assert summary["dispatcher_invoked"] is False
    assert calls == []
    assert not (tmp_path / "processed_requests.jsonl").exists()
    assert_high_risk_safety(summary)


def test_b3c_blocks_maybe_status_check_before_dispatcher(tmp_path):
    calls = []

    summary = run_b3c(
        tmp_path,
        FakeGitHub(
            target_comments=[
                CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW"),
                CommentRecord(id=20, body=result_comment(), author="HarryWhite-TW"),
            ]
        ),
        dispatcher_invoker=lambda **kwargs: calls.append(kwargs),
    )

    assert summary["result"] == "blocked"
    assert summary["blocked_reasons"] == ["maybe_status_check_not_enabled_in_b3c"]
    assert summary["dispatcher_invoked"] is False
    assert calls == []
    assert not (tmp_path / "processed_requests.jsonl").exists()
    assert_high_risk_safety(summary)


def test_b3b_unsupported_action_and_duplicate_request_fail_before_dispatcher(tmp_path):
    calls = []
    unsupported = run_b3b(
        tmp_path / "unsupported",
        FakeGitHub(
            inbox_comments=[
                CommentRecord(id=1, body=inbox_marker(action="delete-branch"), author="HarryWhite-TW")
            ]
        ),
        dispatcher_invoker=lambda **kwargs: calls.append(kwargs),
    )
    duplicate = run_b3b(
        tmp_path / "duplicate",
        FakeGitHub(
            inbox_comments=[
                CommentRecord(id=1, body=inbox_marker(request_id="first"), author="HarryWhite-TW"),
                CommentRecord(id=2, body=inbox_marker(request_id="second"), author="HarryWhite-TW"),
            ]
        ),
        dispatcher_invoker=lambda **kwargs: calls.append(kwargs),
    )

    assert unsupported["blocked_reasons"] == ["unsupported_action"]
    assert duplicate["blocked_reasons"] == ["multiple_current_requests"]
    assert unsupported["dispatcher_invoked"] is False
    assert duplicate["dispatcher_invoked"] is False
    assert calls == []
    assert_high_risk_safety(unsupported)
    assert_high_risk_safety(duplicate)


def test_b3b_dispatcher_failures_do_not_write_processed_request(tmp_path):
    cases = [
        ("dispatcher_missing", lambda **_: (_ for _ in ()).throw(FileNotFoundError("missing"))),
        ("dispatcher_nonzero_exit", lambda **_: DispatcherInvocationResult(returncode=2, stderr="bad")),
        ("dispatcher_timeout", lambda **_: DispatcherInvocationResult(returncode=1, timed_out=True)),
        ("dispatcher_nonzero_exit", lambda **_: (_ for _ in ()).throw(RuntimeError("boom"))),
    ]

    for reason, invoker in cases:
        case_dir = tmp_path / reason
        summary = run_b3b(case_dir, dispatcher_invoker=invoker)
        assert summary["result"] == "blocked"
        assert summary["blocked_reasons"] == [reason]
        assert summary["dispatcher_invocation_count"] == 1
        failure = read_json(case_dir / "last_failure.json")
        assert failure["reason"] == reason
        assert failure["current_failure_recorded"] is True
        assert failure["last_failure_json_applies_to_current_run"] is True
        assert failure["last_failure_json_status"] == "current_failure"
        assert failure["current_run"]["current_failure_reason"] == reason
        assert summary["current_run"]["last_failure_json_status"] == "current_failure"
        assert failure["dispatcher_reached"] is True
        assert failure["dispatcher_result_writeback_reached"] is False
        assert failure["dispatcher_result_writeback_verified"] is False
        log = read_log_events(case_dir / "operator.log")[-1]
        assert log["dispatcher_result_writeback_reached"] is False
        assert log["dispatcher_result_writeback_verified"] is False
        assert not (case_dir / "processed_requests.jsonl").exists()
        assert_high_risk_safety(summary)


def test_b3c_dispatcher_failures_do_not_write_processed_request(tmp_path):
    cases = [
        ("dispatcher_missing", lambda **_: (_ for _ in ()).throw(FileNotFoundError("missing"))),
        ("dispatcher_nonzero_exit", lambda **_: DispatcherInvocationResult(returncode=2, stderr="bad")),
        ("dispatcher_timeout", lambda **_: DispatcherInvocationResult(returncode=1, timed_out=True)),
        ("dispatcher_nonzero_exit", lambda **_: (_ for _ in ()).throw(RuntimeError("boom"))),
    ]

    for reason, invoker in cases:
        case_dir = tmp_path / reason
        summary = run_b3c(case_dir, dispatcher_invoker=invoker)
        assert summary["result"] == "blocked"
        assert summary["blocked_reasons"] == [reason]
        assert summary["dispatcher_invocation_count"] == 1
        failure = read_json(case_dir / "last_failure.json")
        assert failure["reason"] == reason
        assert failure["dispatcher_reached"] is True
        assert failure["dispatcher_result_writeback_reached"] is False
        assert failure["dispatcher_result_writeback_verified"] is False
        assert not (case_dir / "processed_requests.jsonl").exists()
        assert_high_risk_safety(summary)


def test_b3b_dispatcher_success_without_verifiable_result_fails_closed(tmp_path):
    missing = run_b3b(
        tmp_path,
        FakeGitHub(target_comments=[CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW")]),
    )
    mismatched = run_b3b(
        tmp_path / "mismatched",
        FakeGitHub(
            target_comments=[
                CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW"),
                CommentRecord(id=20, body=result_comment(request_id="other"), author="HarryWhite-TW"),
            ]
        ),
    )

    for summary, case_dir in ((missing, tmp_path), (mismatched, tmp_path / "mismatched")):
        assert summary["result"] == "blocked"
        assert summary["blocked_reasons"] == ["target_result_missing"]
        assert summary["dispatcher_invocation_count"] == 1
        assert summary["dispatcher_result_writeback_reached"] is False
        assert summary["dispatcher_result_writeback_verified"] is False
        failure = read_json(case_dir / "last_failure.json")
        assert failure["dispatcher_reached"] is True
        assert failure["dispatcher_result_writeback_reached"] is False
        assert failure["dispatcher_result_writeback_verified"] is False
        assert_high_risk_safety(summary)
    assert not (tmp_path / "processed_requests.jsonl").exists()


def test_b3c_dispatcher_success_without_verifiable_result_fails_closed(tmp_path):
    missing = run_b3c(
        tmp_path,
        FakeGitHub(
            inbox_comments=[
                CommentRecord(
                    id=1,
                    body=inbox_marker(action="run-reviewbundle"),
                    author="HarryWhite-TW",
                )
            ],
            target_comments=[
                CommentRecord(
                    id=10,
                    body=dispatch_marker(action="run-reviewbundle"),
                    author="HarryWhite-TW",
                )
            ],
        ),
    )
    mismatched = run_b3c(
        tmp_path / "mismatched",
        FakeGitHub(
            inbox_comments=[
                CommentRecord(
                    id=1,
                    body=inbox_marker(action="run-reviewbundle"),
                    author="HarryWhite-TW",
                )
            ],
            target_comments=[
                CommentRecord(
                    id=10,
                    body=dispatch_marker(action="run-reviewbundle"),
                    author="HarryWhite-TW",
                ),
                CommentRecord(
                    id=20,
                    body=result_comment(action="run-reviewbundle", request_id="other"),
                    author="HarryWhite-TW",
                ),
            ],
        ),
    )

    for summary, case_dir in ((missing, tmp_path), (mismatched, tmp_path / "mismatched")):
        assert summary["result"] == "blocked"
        assert summary["blocked_reasons"] == ["target_result_missing"]
        assert summary["dispatcher_invocation_count"] == 1
        assert summary["dispatcher_result_writeback_reached"] is False
        assert summary["dispatcher_result_writeback_verified"] is False
        assert read_json(case_dir / "last_failure.json")["dispatcher_reached"] is True
        assert not (case_dir / "processed_requests.jsonl").exists()
        assert_high_risk_safety(summary)


def test_b3b_dirty_repo_and_wrong_head_fail_before_dispatcher(tmp_path):
    calls = []
    dirty = run_b3b(
        tmp_path / "dirty",
        readiness=ready(tmp_path / "dirty", clean=False),
        dispatcher_invoker=lambda **kwargs: calls.append(kwargs),
    )
    wrong_head = run_b3b(
        tmp_path / "head",
        readiness=ready(tmp_path / "head", head="0" * 40),
        dispatcher_invoker=lambda **kwargs: calls.append(kwargs),
    )

    assert dirty["blocked_reasons"] == ["dirty_repository"]
    assert dirty["dispatcher_invoked"] is False
    assert wrong_head["blocked_reasons"] == ["wrong_head"]
    assert wrong_head["dispatcher_invoked"] is False
    assert calls == []
    assert_high_risk_safety(dirty)
    assert_high_risk_safety(wrong_head)


def test_b3b_untrusted_or_failure_result_reaches_writeback_but_is_not_verified(tmp_path):
    untrusted = run_b3b(
        tmp_path / "untrusted",
        FakeGitHub(
            target_comments=[
                CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW"),
                CommentRecord(id=20, body=result_comment(), author="other-user"),
            ]
        ),
    )
    failure_result = run_b3b(
        tmp_path / "failure-result",
        FakeGitHub(
            target_comments=[
                CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW"),
                CommentRecord(id=20, body=result_comment(result="failure"), author="HarryWhite-TW"),
            ]
        ),
    )

    cases = (
        (untrusted, tmp_path / "untrusted", "untrusted_result_author"),
        (failure_result, tmp_path / "failure-result", "target_result_not_success"),
    )
    for summary, case_dir, reason in cases:
        assert summary["blocked_reasons"] == [reason]
        assert summary["dispatcher_invocation_count"] == 1
        assert summary["dispatcher_result_writeback_reached"] is True
        assert summary["dispatcher_result_writeback_verified"] is False
        assert summary["target_result_verified"] is False
        failure = read_json(case_dir / "last_failure.json")
        assert failure["dispatcher_result_writeback_reached"] is True
        assert failure["dispatcher_result_writeback_verified"] is False
        log = read_log_events(case_dir / "operator.log")[-1]
        assert log["dispatcher_result_writeback_reached"] is True
        assert log["dispatcher_result_writeback_verified"] is False
        assert not (case_dir / "processed_requests.jsonl").exists()
        assert_high_risk_safety(summary)


def test_b3b_already_processed_request_does_not_rerun_dispatcher(tmp_path):
    first = run_b3b(tmp_path)
    calls = []
    second = run_b3b(tmp_path, dispatcher_invoker=lambda **kwargs: calls.append(kwargs))

    assert first["processed_request_written"] is True
    assert second["result"] == "success"
    assert second["processed_request_already_seen"] is True
    assert second["dispatcher_invoked"] is False
    assert calls == []
    processed = (tmp_path / "processed_requests.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(processed) == 1
    assert_high_risk_safety(second)


def test_success_summary_marks_existing_last_failure_as_historical(tmp_path):
    stale_failure = {
        "protocol": "lawb.bridge_operator_b3_failure.v1",
        "failed_at_utc": "2026-06-15T08:00:00Z",
        "reason": "dispatcher_timeout",
        "request_id": "old-request",
        "last_failure_json_status": "current_failure",
    }
    (tmp_path / "last_failure.json").write_text(
        json.dumps(stale_failure, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    summary = run_b3b(tmp_path)

    assert summary["result"] == "success"
    assert summary["current_failure_recorded"] is False
    assert summary["historical_last_failure_file_present"] is True
    assert summary["last_failure_json_applies_to_current_run"] is False
    assert summary["last_failure_json_status"] == "historical_not_current_run"
    assert summary["current_run"]["last_failure_json_status"] == "historical_not_current_run"
    assert summary["current_run"]["current_failure_recorded"] is False
    assert read_json(tmp_path / "last_failure.json") == stale_failure
    log = read_log_events(tmp_path / "operator.log")[-1]
    assert log["last_failure_json_status"] == "historical_not_current_run"
    assert log["current_run"]["last_failure_json_applies_to_current_run"] is False


def test_b3c_already_processed_request_does_not_rerun_dispatcher(tmp_path):
    first = run_b3c(tmp_path)
    calls = []
    second = run_b3c(tmp_path, dispatcher_invoker=lambda **kwargs: calls.append(kwargs))

    assert first["processed_request_written"] is True
    assert second["result"] == "success"
    assert second["processed_request_already_seen"] is True
    assert second["dispatcher_invoked"] is False
    assert calls == []
    processed = (tmp_path / "processed_requests.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(processed) == 1
    assert_high_risk_safety(second)


def test_b3c_lock_pause_and_stop_block_before_delegation(tmp_path):
    calls = []
    lock_dir = tmp_path / "lock"
    lock_dir.mkdir()
    (lock_dir / "operator.lock").write_text('{"pid": 1}\n', encoding="utf-8")
    active_lock = run_b3c(lock_dir, dispatcher_invoker=lambda **kwargs: calls.append(kwargs))

    pause_dir = tmp_path / "pause"
    pause_dir.mkdir()
    (pause_dir / "pause.flag").write_text("", encoding="utf-8")
    paused = run_b3c(pause_dir, dispatcher_invoker=lambda **kwargs: calls.append(kwargs))

    stop_dir = tmp_path / "stop"
    stop_dir.mkdir()
    (stop_dir / "stop.flag").write_text("", encoding="utf-8")
    stopped = run_b3c(stop_dir, dispatcher_invoker=lambda **kwargs: calls.append(kwargs))

    assert active_lock["blocked_reasons"] == ["active_lock_present"]
    assert active_lock["dispatcher_invoked"] is False
    assert paused["result"] == "success"
    assert paused["pause_observed"] is True
    assert paused["dispatcher_invoked"] is False
    assert stopped["result"] == "success"
    assert stopped["stop_requested"] is True
    assert stopped["dispatcher_invoked"] is False
    assert calls == []
    assert_high_risk_safety(active_lock)
    assert_high_risk_safety(paused)
    assert_high_risk_safety(stopped)


def test_no_current_request_is_safe_wait_condition(tmp_path):
    summary = run(tmp_path, FakeGitHub(inbox_comments=[]))

    assert summary["result"] == "success"
    assert summary["last_b1_blocked_reasons"] == ["missing_request"]
    assert summary["empty_or_blocked_cycles"] == 1
    assert not (tmp_path / "last_failure.json").exists()
    assert not (tmp_path / "dry_run_observations.jsonl").exists()
    assert not (tmp_path / "processed_requests.jsonl").exists()
    assert_safety(summary)


def test_malformed_or_invalid_inbox_request_blocks(tmp_path):
    malformed = CommentRecord(id=1, body=inbox_marker() + "\nextra", author="HarryWhite-TW")

    summary = run(tmp_path, FakeGitHub(inbox_comments=[malformed]))

    assert_b1_failure_blocks(tmp_path, summary, "malformed_marker")


def test_untrusted_request_author_blocks(tmp_path):
    comment = CommentRecord(id=1, body=inbox_marker(), author="other-user")

    summary = run(tmp_path, FakeGitHub(inbox_comments=[comment]))

    assert_b1_failure_blocks(tmp_path, summary, "untrusted_inbox_author")


def test_expired_request_blocks(tmp_path):
    comment = CommentRecord(
        id=1,
        body=inbox_marker(expires="20260615T080000Z"),
        author="HarryWhite-TW",
    )

    summary = run(tmp_path, FakeGitHub(inbox_comments=[comment]))

    assert_b1_failure_blocks(tmp_path, summary, "missing_current_request")


def test_wrong_branch_or_wrong_head_blocks(tmp_path):
    wrong_branch = run(
        tmp_path / "branch",
        readiness=ready(tmp_path / "branch", branch="other-branch"),
    )
    wrong_head = run(
        tmp_path / "head",
        readiness=ready(tmp_path / "head", head="0" * 40),
    )

    assert_b1_failure_blocks(tmp_path / "branch", wrong_branch, "wrong_branch")
    assert_b1_failure_blocks(tmp_path / "head", wrong_head, "wrong_head")


def test_closed_target_issue_blocks(tmp_path):
    class ClosedTargetGitHub(FakeGitHub):
        def get_issue(self, issue_number):
            self.issues_read.append(issue_number)
            if issue_number == DEFAULT_INBOX_ISSUE:
                return IssueRecord(number=DEFAULT_INBOX_ISSUE, state="open", body="")
            return IssueRecord(number=issue_number, state="closed", body="")

    summary = run(tmp_path, ClosedTargetGitHub())

    assert_b1_failure_blocks(tmp_path, summary, "target_issue_closed")


def test_missing_or_duplicate_target_dispatch_marker_blocks(tmp_path):
    missing = run(
        tmp_path / "missing",
        FakeGitHub(target_comments=[]),
    )
    duplicate = run(
        tmp_path / "duplicate",
        FakeGitHub(
            target_comments=[
                CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW"),
                CommentRecord(id=11, body=dispatch_marker(), author="HarryWhite-TW"),
            ]
        ),
    )

    assert_b1_failure_blocks(tmp_path / "missing", missing, "target_dispatch_request_not_found")
    assert_b1_failure_blocks(tmp_path / "duplicate", duplicate, "ambiguous_target_dispatch_request")


def test_dirty_repo_or_local_readiness_failure_blocks(tmp_path):
    comment = CommentRecord(
        id=1,
        body=inbox_marker(action="run-reviewbundle"),
        author="HarryWhite-TW",
    )
    target = CommentRecord(
        id=10,
        body=dispatch_marker(action="run-reviewbundle"),
        author="HarryWhite-TW",
    )

    dirty = run(
        tmp_path / "dirty",
        FakeGitHub(inbox_comments=[comment], target_comments=[target]),
        readiness=ready(tmp_path / "dirty", clean=False),
    )
    missing_gh = run(
        tmp_path / "missing-gh",
        readiness=ready(tmp_path / "missing-gh", gh_available=False),
    )

    assert_b1_failure_blocks(tmp_path / "dirty", dirty, "dirty_repository")
    assert_b1_failure_blocks(tmp_path / "missing-gh", missing_gh, "missing_github_cli")


def test_rejects_inbox_override_and_does_not_read_github(tmp_path):
    client = FakeGitHub()

    summary = run(tmp_path, client, inbox_issue=999)

    assert summary["result"] == "blocked"
    assert summary["blocked_reasons"] == ["unsupported_inbox_issue"]
    assert client.issues_read == []
    assert client.comments_read == []
    assert_safety(summary)


def test_max_cycles_and_poll_interval_are_bounded_and_testable(tmp_path):
    sleeps = []

    summary = run_bridge_operator_b3_dry_run_loop(
        repo_root=ROOT_PATH,
        state_dir=tmp_path,
        github_client=FakeGitHub(inbox_comments=[]),
        local_checker=ready(tmp_path),
        now_utc=NOW,
        sleeper=lambda seconds: sleeps.append(seconds),
        max_cycles=3,
        poll_interval_seconds=1.25,
    )

    assert summary["result"] == "success"
    assert summary["cycles_completed"] == 3
    assert summary["sleep_call_count"] == 2
    assert sleeps == [1.25, 1.25]
    assert run(tmp_path / "bad1", max_cycles=0)["blocked_reasons"] == ["invalid_max_cycles"]
    assert run(tmp_path / "bad2", poll_interval_seconds=-1)["blocked_reasons"] == [
        "invalid_poll_interval_seconds"
    ]
    assert_safety(summary)


def test_lock_created_during_run_and_removed_after_success(tmp_path):
    summary = run_bridge_operator_b3_dry_run_loop(
        repo_root=ROOT_PATH,
        state_dir=tmp_path,
        github_client=FakeGitHub(),
        local_checker=ready(tmp_path, assert_lock=True),
        now_utc=NOW,
        sleeper=lambda seconds: None,
    )

    assert summary["result"] == "success"
    assert summary["lock_acquired"] is True
    assert not (tmp_path / "operator.lock").exists()
    assert_safety(summary)


def test_active_or_stale_lock_blocks_without_removal(tmp_path):
    lock = tmp_path / "operator.lock"
    lock.write_text('{"pid": 1, "created_at_utc": "old"}\n', encoding="utf-8")

    summary = run(tmp_path)

    assert summary["result"] == "blocked"
    assert summary["blocked_reasons"] == ["active_lock_present"]
    assert lock.exists()
    assert "old" in lock.read_text(encoding="utf-8")
    assert read_json(tmp_path / "last_failure.json")["reason"] == "active_lock_present"
    assert_safety(summary)


def test_heartbeat_writes_expected_fields(tmp_path):
    summary = run(tmp_path)
    heartbeat = read_json(tmp_path / "heartbeat.json")

    assert heartbeat["protocol"] == "lawb.bridge_operator_b3_heartbeat.v1"
    assert heartbeat["mode"] == "b3a-dry-run"
    assert heartbeat["repo"] == "HarryWhite-TW/local-ai-workbench"
    assert heartbeat["inbox_issue"] == 147
    assert heartbeat["request_id"] == "b3a-151-20260616T080000Z"
    assert summary["result"] == "success"
    assert_safety(summary)


def test_pause_flag_pauses_without_delegation_or_read(tmp_path):
    (tmp_path / "pause.flag").write_text("", encoding="utf-8")
    client = FakeGitHub(fail_reads=True)

    summary = run(tmp_path, client, max_cycles=1)

    assert summary["result"] == "success"
    assert summary["pause_observed"] is True
    assert summary["paused_cycles"] == 1
    assert client.issues_read == []
    assert read_json(tmp_path / "heartbeat.json")["status"] == "paused"
    assert_safety(summary)


def test_stop_flag_exits_cleanly_without_polling(tmp_path):
    (tmp_path / "stop.flag").write_text("", encoding="utf-8")
    client = FakeGitHub(fail_reads=True)

    summary = run(tmp_path, client, max_cycles=3)

    assert summary["result"] == "success"
    assert summary["phase"] == "stopped"
    assert summary["stop_requested"] is True
    assert client.issues_read == []
    assert_safety(summary)


def test_duplicate_dry_run_observation_is_idempotent(tmp_path):
    first = run(tmp_path)
    second = run(tmp_path)

    assert first["dry_run_observation_written"] is True
    assert second["dry_run_observation_written"] is False
    assert second["dry_run_duplicate_observation"] is True
    lines = (tmp_path / "dry_run_observations.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert not (tmp_path / "processed_requests.jsonl").exists()
    assert_safety(second)


def test_corrupted_state_fails_closed(tmp_path):
    (tmp_path / "state.json").write_text("{", encoding="utf-8")

    summary = run(tmp_path)

    assert summary["result"] == "blocked"
    assert summary["blocked_reasons"] == ["corrupted_state"]
    assert read_json(tmp_path / "last_failure.json")["reason"] == "corrupted_state"
    assert_safety(summary)


def test_corrupted_processed_history_fails_closed_before_dispatcher(tmp_path):
    (tmp_path / "processed_requests.jsonl").write_text("{not-json}\n", encoding="utf-8")
    calls = []

    summary = run_b3b(tmp_path, dispatcher_invoker=lambda **kwargs: calls.append(kwargs))

    assert summary["result"] == "blocked"
    assert summary["blocked_reasons"] == ["corrupted_state"]
    assert summary["dispatcher_invoked"] is False
    assert calls == []
    assert read_json(tmp_path / "last_failure.json")["reason"] == "corrupted_state"
    assert_high_risk_safety(summary)


def test_local_checker_value_error_is_not_mislabeled_as_corrupted_processed_history(tmp_path):
    existing = {
        "protocol": "lawb.bridge_operator_b3_processed_request.v1",
        "request_id": "unrelated-processed",
        "lifecycle_state": "CONSUMED",
    }
    (tmp_path / "processed_requests.jsonl").write_text(
        json.dumps(existing, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    calls = []

    def raising_checker(_root):
        raise ValueError("local checker failed")

    summary = run_b3b(
        tmp_path,
        readiness=raising_checker,
        dispatcher_invoker=lambda **kwargs: calls.append(kwargs),
    )

    assert summary["result"] == "blocked"
    assert "corrupted_state" not in summary["blocked_reasons"]
    assert summary["dispatcher_invoked"] is False
    assert summary["dispatcher_invocation_count"] == 0
    assert calls == []
    processed = (tmp_path / "processed_requests.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(processed) == 1
    assert json.loads(processed[0]) == existing
    assert_high_risk_safety(summary)


def test_network_read_failure_uses_bounded_retry_only(tmp_path):
    summary = run(tmp_path, FakeGitHub(fail_reads=True), read_retry_count=2)

    assert summary["result"] == "blocked"
    assert summary["blocked_reasons"] == ["github_read_unavailable"]
    assert summary["github_read_attempts"] == 3
    assert summary["retry_performed"] is True
    assert read_json(tmp_path / "last_failure.json")["reason"] == "github_read_unavailable"
    assert_safety(summary)


def test_logs_do_not_contain_secret_or_full_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("B3_SECRET", "ghp_TEST_SECRET_DO_NOT_LEAK")

    summary = run(tmp_path)
    log_text = (tmp_path / "operator.log").read_text(encoding="utf-8")

    assert "ghp_TEST_SECRET_DO_NOT_LEAK" not in log_text
    assert "B3_SECRET" not in log_text
    assert "PATH" not in log_text
    assert summary["result"] == "success"
    assert_safety(summary)

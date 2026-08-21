import base64
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from local_runner_bridge.bridge_operator_b1 import (
    DEFAULT_REPOSITORY,
    HAG_REPOSITORY,
    CommentRecord,
    IssueRecord,
    LocalReadiness,
)
import local_runner_bridge.bridge_operator_b3 as bridge_operator_b3
from local_runner_bridge.bridge_operator_b3 import (
    B3B_MODE,
    B3C_MODE,
    DEFAULT_INBOX_ISSUE,
    PROCESSED_REQUEST_PROTOCOL,
    read_processed_request_ids,
    read_processed_request_records,
    run_bridge_operator_b3_dry_run_loop,
)
from local_runner_bridge.bridge_operator_b2 import (
    DISPATCHER_FAILED_BEFORE_RUNNER,
    DISPATCHER_FAILED_BEFORE_RUNNER_EXIT_CODE,
    DISPATCHER_REJECTED_BEFORE_RUNNER,
    DISPATCHER_REJECTED_BEFORE_RUNNER_EXIT_CODE,
    DISPATCHER_RUNNER_MAY_HAVE_STARTED,
    DISPATCHER_RUNNER_REACH_UNCERTAIN_EXIT_CODE,
    DispatcherInvocationResult,
)
from local_runner_bridge.durable_evidence_reconciliation import (
    EvidenceReadResult,
    ProviderStatus,
)
from local_runner_bridge.bridge_operator_lifecycle_state import (
    DISPATCHED_NOT_LOCALLY_SETTLED,
    PREPARED,
    PROCESSED,
    REJECTED_BEFORE_RUNNER,
    create_lock_payload,
    write_exclusive_json,
)
from local_runner_bridge.workflow_result_notifications import (
    SUBMITTED,
    NotificationSubmission,
)

NOW = datetime(2026, 6, 16, 8, 0, 0, tzinfo=timezone.utc)
HEAD = "3aedc4925e9da241429a7905418b6a815fd9ee37"
ROOT_PATH = r"C:\Users\admin\Desktop\local-ai-workbench-course"


def inbox_marker(**overrides):
    fields = {
        "protocol": "lawb.bridge_inbox_request.v1",
        "request_id": "b3a-151-20260616T080000Z",
        "repo": "HarryWhite-TW/local-ai-workbench",
        "target_issue": "151",
        "target_dispatch_request_id": "b3a-151-20260616T080000Z",
        "branch": "feature/bridge-operator-b3a",
        "head": HEAD,
        "expires": "20260616T080500Z",
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
        "expires": "20260616T080500Z",
        "requested_by": "chatgpt",
        "request_id": "b3a-151-20260616T080000Z",
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
        "request_id": "b3a-151-20260616T080000Z",
    }
    fields.update(overrides)
    return "LAWBRUNNER-RESULT protocol=lawb.runner_result.v1\n" + json.dumps(fields)


class FakeGitHub:
    def __init__(self, *, inbox_comments=None, target_comments=None, fail_reads=False):
        self.inbox_comments = inbox_comments if inbox_comments is not None else [
            CommentRecord(id=1, body=inbox_marker(), author="HarryWhite-TW")
        ]
        self.target_comments = target_comments if target_comments is not None else []
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
    created_default_client = client is None
    if client is None:
        client = FakeGitHub(
            target_comments=[
                CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW"),
            ]
        )
    base_invoker = dispatcher_invoker or (
        lambda **_: DispatcherInvocationResult(returncode=0, stdout="ok", stderr="")
    )

    def invoker(**call_kwargs):
        result = base_invoker(**call_kwargs)
        if created_default_client and result.returncode == 0 and not result.timed_out:
            client.target_comments.append(
                CommentRecord(id=20, body=result_comment(), author="HarryWhite-TW")
            )
        return result

    configured_timeout = kwargs.pop("timeout_seconds", 30)
    return run_bridge_operator_b3_dry_run_loop(
        repo_root=ROOT_PATH,
        state_dir=tmp_path,
        github_client=client,
        local_checker=readiness or ready(tmp_path),
        now_utc=NOW,
        sleeper=lambda seconds: None,
        mode=B3B_MODE,
        dispatcher_invoker=invoker,
        timeout_seconds=configured_timeout,
        **kwargs,
    )


def run_b3c(tmp_path, client=None, readiness=None, dispatcher_invoker=None, **kwargs):
    created_default_client = client is None
    if client is None:
        client = FakeGitHub(
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
            ],
        )
    base_invoker = dispatcher_invoker or (
        lambda **_: DispatcherInvocationResult(returncode=0, stdout="ok", stderr="")
    )

    def invoker(**call_kwargs):
        result = base_invoker(**call_kwargs)
        if created_default_client and result.returncode == 0 and not result.timed_out:
            client.target_comments.append(
                CommentRecord(
                    id=20,
                    body=result_comment(action="run-reviewbundle"),
                    author="HarryWhite-TW",
                )
            )
        return result

    configured_timeout = kwargs.pop("timeout_seconds", 30)
    return run_bridge_operator_b3_dry_run_loop(
        repo_root=ROOT_PATH,
        state_dir=tmp_path,
        github_client=client,
        local_checker=readiness or ready(tmp_path),
        now_utc=NOW,
        sleeper=lambda seconds: None,
        mode=B3C_MODE,
        dispatcher_invoker=invoker,
        timeout_seconds=configured_timeout,
        **kwargs,
    )


SESSION_A = "a" * 32
SESSION_B = "b" * 32


def fake_process_identity(pid=4101, token="windows-filetime:41010000"):
    return {
        "platform": "windows",
        "pid": pid,
        "start_token": token,
        "started_at_utc": "2026-06-16T07:59:00Z",
    }


def process_observation(process_status, descendant_status="none"):
    return {
        "process_status": process_status,
        "descendant_status": descendant_status,
        "observed_process_identity": None,
        "descendant_pids": [] if descendant_status == "none" else [9001],
        "reason": "none",
    }


def inject_at(target_stage):
    def injector(stage):
        if stage == target_stage:
            raise RuntimeError(f"fault:{stage}")

    return injector


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


def processed_record(**overrides):
    payload = {
        "protocol": "lawb.bridge_operator_b3_processed_request.v1",
        "request_id": "processed-a",
        "target_issue": 151,
        "target_dispatch_request_id": None,
        "requested_action": "maybe-status-check",
        "expected_branch": "feature/bridge-operator-b3a",
        "expected_head": HEAD,
    }
    payload.update(overrides)
    if payload["target_dispatch_request_id"] is None:
        payload["target_dispatch_request_id"] = payload["request_id"]
    return payload


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
    assert summary["configured_inbox_issue"] == DEFAULT_INBOX_ISSUE
    assert summary["eligible_request_observed"] is True
    assert summary["dry_run_observation_written"] is True
    assert summary["processed_request_written"] is False
    assert client.issues_read == [DEFAULT_INBOX_ISSUE, 151]
    assert client.comments_read == [DEFAULT_INBOX_ISSUE]
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
        "lifecycle": {
            "stage": "TERMINAL_RESULT_READY",
            "certainty": "verified",
            "basis": "trusted_terminal_result",
        },
        "mode": "b3b-maybe-status-check",
        "max_cycles": 1,
        "operator_dispatcher_invocation_performed": True,
        "dispatcher_invoked": True,
        "dispatcher_execution_reach": None,
        "runner_reached": None,
        "codex_reached": None,
        "operator_direct_runner_invoked": False,
        "operator_direct_codex_invoked": False,
        "github_result_writeback_observed": True,
        "durable_reconciliation_performed": True,
        "durable_reconciliation_decision": "COMPLETED",
        "durable_reconciliation_reason": "EXACTLY_ONE_TRUSTED_MATCH",
        "durable_reconciliation_matched_evidence_ids": ["20"],
        "durable_completion_reconciled": False,
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
        "target_issue": 151,
        "target_dispatch_request_id": "processed-a",
        "requested_action": "maybe-status-check",
        "expected_branch": "feature/bridge-operator-b3a",
        "expected_head": HEAD,
        "lifecycle_state": "CONSUMED",
    }
    (tmp_path / "processed_requests.jsonl").write_text(
        json.dumps(original, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    calls = []
    client = FakeGitHub(
        inbox_comments=[
            CommentRecord(id=1, body=inbox_marker(request_id="processed-a", target_dispatch_request_id="processed-a"), author="HarryWhite-TW"),
            CommentRecord(
                id=2,
                body=inbox_marker(request_id="current-b", target_dispatch_request_id="current-b"),
                author="HarryWhite-TW",
            ),
        ],
        target_comments=[
            CommentRecord(id=10, body=dispatch_marker(request_id="dispatch-b"), author="HarryWhite-TW"),
        ],
    )

    summary = run_b3b(
        tmp_path,
        client,
        dispatcher_invoker=lambda **kwargs: calls.append(kwargs)
        or client.target_comments.append(
            CommentRecord(
                id=20,
                body=result_comment(request_id="current-b"),
                author="HarryWhite-TW",
            )
        )
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
                "target_issue": 151,
                "target_dispatch_request_id": "b3a-151-20260616T080000Z",
                "requested_action": "maybe-status-check",
                "expected_branch": "feature/bridge-operator-b3a",
                "expected_head": HEAD,
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


def test_b3c_mixed_supported_repository_history_selects_hag_and_dispatches_once(tmp_path):
    hag_root = r"C:\Users\admin\Desktop\human-approval-automation-gateway"
    hag_branch = "hag-01-request-contracts"
    hag_request_id = "hag-current-request"
    hag_dispatch_id = "hag-current-dispatch"
    control = FakeGitHub(
        inbox_comments=[
            CommentRecord(
                id=1,
                body=inbox_marker(
                    request_id="local-current-history",
                    repo=DEFAULT_REPOSITORY,
                    target_dispatch_request_id="local-current-history",
                ),
                author="HarryWhite-TW",
            ),
            CommentRecord(
                id=2,
                body=inbox_marker(
                    request_id=hag_request_id,
                    repo=HAG_REPOSITORY,
                    target_issue="1",
                    target_dispatch_request_id=hag_request_id,
                    branch=hag_branch,
                    action="run-reviewbundle",
                ),
                author="HarryWhite-TW",
            ),
        ]
    )
    target = FakeGitHub(
        target_comments=[
            CommentRecord(
                id=10,
                body=dispatch_marker(
                    repo=HAG_REPOSITORY,
                    issue="1",
                    request_id=hag_request_id,
                    branch=hag_branch,
                    action="run-reviewbundle",
                ),
                author="HarryWhite-TW",
            )
        ]
    )
    calls = []

    def invoker(**kwargs):
        calls.append(kwargs)
        target.target_comments.append(
            CommentRecord(
                id=20,
                body=result_comment(
                    repo=HAG_REPOSITORY,
                    issue=1,
                    request_id=hag_request_id,
                    branch=hag_branch,
                    action="run-reviewbundle",
                ),
                author="HarryWhite-TW",
            )
        )
        return DispatcherInvocationResult(returncode=0, stdout="dispatcher ok", stderr="")

    summary = run_bridge_operator_b3_dry_run_loop(
        repo_root=hag_root,
        control_repo_root=ROOT_PATH,
        repository=HAG_REPOSITORY,
        state_dir=tmp_path,
        github_client=control,
        target_github_client=target,
        local_checker=ready(
            tmp_path,
            repo_root=str(Path(hag_root).resolve()),
            branch=hag_branch,
            origin_repository=HAG_REPOSITORY,
            staged_clean=True,
        ),
        now_utc=NOW,
        sleeper=lambda seconds: None,
        mode=B3C_MODE,
        dispatcher_invoker=invoker,
        timeout_seconds=30,
    )

    assert summary["result"] == "success"
    assert summary["request_id"] == hag_request_id
    assert summary["inbox_comment_id"] == 2
    assert summary["current_request_count"] == 1
    assert summary["dispatcher_invoked"] is True
    assert summary["dispatcher_invocation_count"] == 1
    assert len(calls) == 1
    assert calls[0]["args"][calls[0]["args"].index("-Repo") + 1] == HAG_REPOSITORY
    assert calls[0]["args"][calls[0]["args"].index("-TargetRepoRoot") + 1] == str(
        Path(hag_root).resolve()
    )
    assert summary["runner_invoked"] is False
    assert summary["codex_invoked"] is False
    assert summary["github_write_performed"] is False
    assert summary["commit_performed"] is False
    assert summary["push_performed"] is False
    assert summary["pr_created"] is False
    assert summary["merge_performed"] is False
    assert_high_risk_safety(summary)


def test_b3b_preexisting_matching_durable_completion_reconciles_without_dispatcher(tmp_path):
    calls = []
    client = FakeGitHub(
        target_comments=[
            CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW"),
            CommentRecord(id=20, body=result_comment(), author="HarryWhite-TW"),
        ]
    )

    summary = run_b3b(
        tmp_path,
        client,
        dispatcher_invoker=lambda **kwargs: calls.append(kwargs),
    )

    assert summary["result"] == "success"
    assert summary["phase"] == "reconciled_completed"
    assert summary["durable_reconciliation_performed"] is True
    assert summary["durable_reconciliation_decision"] == "COMPLETED"
    assert summary["durable_reconciliation_reason"] == "EXACTLY_ONE_TRUSTED_MATCH"
    assert summary["durable_reconciliation_matched_evidence_ids"] == ["20"]
    assert summary["durable_completion_reconciled"] is True
    assert summary["dispatcher_invoked"] is False
    assert summary["dispatcher_invocation_count"] == 0
    assert summary["operator_direct_execution_performed"] is False
    assert summary["runner_invoked"] is False
    assert summary["codex_invoked"] is False
    assert summary["github_write_performed"] is False
    assert calls == []
    processed = (tmp_path / "processed_requests.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(processed) == 1
    payload = json.loads(processed[0])
    assert payload["request_id"] == "b3a-151-20260616T080000Z"
    assert payload["target_dispatch_request_id"] == "b3a-151-20260616T080000Z"
    assert payload["completion_source"] == "durable_evidence_reconciliation"
    assert payload["dispatcher_invoked"] is False
    assert payload["result_verified"] is True
    assert payload["reconciliation_decision"] == "COMPLETED"
    assert payload["reconciliation_reason"] == "EXACTLY_ONE_TRUSTED_MATCH"
    assert payload["reconciliation_matched_evidence_ids"] == ["20"]
    log = read_log_events(tmp_path / "operator.log")[-1]
    assert log["event"] == "reconciled"
    assert log["reason"] == "durable_completion_reconciled"
    assert log["dispatcher_invoked"] is False
    assert log["durable_completion_reconciled"] is True
    assert_high_risk_safety(summary)


def test_b3b_multi_cycle_reconciliation_does_not_misclassify_later_dispatcher_log(
    tmp_path,
):
    calls = []
    client = FakeGitHub(
        target_comments=[
            CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW"),
            CommentRecord(id=20, body=result_comment(), author="HarryWhite-TW"),
        ]
    )

    def sleeper(seconds):
        client.inbox_comments.append(
            CommentRecord(
                id=2,
                body=inbox_marker(
                    request_id="b3b-second-20260616T080001Z",
                    target_dispatch_request_id="b3b-second-20260616T080001Z",
                ),
                author="HarryWhite-TW",
            )
        )
        client.target_comments.append(
            CommentRecord(
                id=30,
                body=dispatch_marker(request_id="dispatch-second"),
                author="HarryWhite-TW",
            )
        )

    def invoker(**kwargs):
        calls.append(kwargs)
        client.target_comments.append(
            CommentRecord(
                id=40,
                body=result_comment(request_id="b3b-second-20260616T080001Z"),
                author="HarryWhite-TW",
            )
        )
        return DispatcherInvocationResult(returncode=0, stdout="ok", stderr="")

    summary = run_bridge_operator_b3_dry_run_loop(
        repo_root=ROOT_PATH,
        state_dir=tmp_path,
        github_client=client,
        local_checker=ready(tmp_path),
        now_utc=NOW,
        sleeper=sleeper,
        mode=B3B_MODE,
        dispatcher_invoker=invoker,
        timeout_seconds=30,
        max_cycles=2,
    )

    assert summary["result"] == "success"
    assert summary["dispatcher_invocation_count"] == 1
    assert len(calls) == 1
    assert calls[0]["args"][calls[0]["args"].index("-IssueNumber") + 1] == "151"

    records = [
        json.loads(line)
        for line in (tmp_path / "processed_requests.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [record["request_id"] for record in records] == [
        "b3a-151-20260616T080000Z",
        "b3b-second-20260616T080001Z",
    ]
    assert records[0]["completion_source"] == "durable_evidence_reconciliation"
    assert records[0]["dispatcher_invoked"] is False
    assert records[1]["dispatcher_invoked"] is True
    assert records[1]["target_dispatch_request_id"] == "b3b-second-20260616T080001Z"
    assert records[1]["result_verified"] is True

    relevant_logs = [
        event
        for event in read_log_events(tmp_path / "operator.log")
        if event["event"] in {"processed", "reconciled"}
    ]
    assert [(event["event"], event["reason"]) for event in relevant_logs] == [
        ("reconciled", "durable_completion_reconciled"),
        ("processed", "verified_dispatcher_result"),
    ]
    assert relevant_logs[0]["request_id"] == "b3a-151-20260616T080000Z"
    assert relevant_logs[1]["request_id"] == "b3b-second-20260616T080001Z"
    assert relevant_logs[0]["current_delegation_outcome"] == "durable_completion_reconciled"
    assert relevant_logs[1]["current_delegation_outcome"] == "verified_dispatcher_result"
    assert not (tmp_path / "last_failure.json").exists()
    assert_high_risk_safety(summary)


def test_b3_multi_cycle_safe_wait_log_does_not_reuse_prior_delegation_outcome(
    tmp_path,
):
    calls = []
    client = FakeGitHub(
        target_comments=[
            CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW"),
        ]
    )

    def sleeper(seconds):
        client.inbox_comments = []

    def invoker(**kwargs):
        calls.append(kwargs)
        client.target_comments.append(
            CommentRecord(id=20, body=result_comment(), author="HarryWhite-TW")
        )
        return DispatcherInvocationResult(returncode=0, stdout="ok", stderr="")

    summary = run_bridge_operator_b3_dry_run_loop(
        repo_root=ROOT_PATH,
        state_dir=tmp_path,
        github_client=client,
        local_checker=ready(tmp_path),
        now_utc=NOW,
        sleeper=sleeper,
        mode=B3B_MODE,
        dispatcher_invoker=invoker,
        timeout_seconds=30,
        max_cycles=2,
    )

    assert summary["result"] == "success"
    assert summary["dispatcher_invocation_count"] == 1
    assert len(calls) == 1
    assert summary["empty_or_blocked_cycles"] == 1
    assert summary["processed_request_written"] is True
    assert summary["current_delegation_outcome"] is None

    log_events = read_log_events(tmp_path / "operator.log")
    processed_logs = [
        event for event in log_events if event["event"] == "processed"
    ]
    waiting_logs = [
        event for event in log_events if event["event"] == "waiting"
    ]

    assert len(processed_logs) == 1
    assert processed_logs[0]["current_delegation_outcome"] == "verified_dispatcher_result"
    assert waiting_logs
    final_waiting = waiting_logs[-1]
    assert final_waiting["reason"] == "no_eligible_current_request"
    assert final_waiting["current_delegation_outcome"] is None
    assert final_waiting["current_delegation_outcome"] != processed_logs[0][
        "current_delegation_outcome"
    ]
    assert not (tmp_path / "last_failure.json").exists()
    assert_high_risk_safety(summary)


def test_current_run_lifecycle_visibility_is_request_local_and_keeps_uncertainty_explicit():
    accepted = bridge_operator_b3._current_run_visibility(
        {
            "request_id": "current-request",
            "target_issue": 151,
            "selected_request_state": "CURRENT",
        }
    )
    uncertain = bridge_operator_b3._current_run_visibility(
        {
            "request_id": "current-request",
            "target_issue": 151,
            "selected_request_state": "CURRENT",
            "dispatcher_invoked": True,
            "dispatcher_execution_reach": DISPATCHER_RUNNER_MAY_HAVE_STARTED,
        }
    )
    reset = bridge_operator_b3._current_run_visibility({})

    assert accepted["request_id"] == "current-request"
    assert accepted["lifecycle"]["stage"] == "REQUEST_ACCEPTED"
    assert uncertain["lifecycle"] == {
        "stage": "RUNNER_OR_CODEX_REACH_UNCERTAIN",
        "certainty": "unknown",
        "basis": "dispatcher_runner_reach_uncertain",
    }
    assert reset["request_id"] is None
    assert reset["lifecycle"] == {
        "stage": "UNKNOWN",
        "certainty": "unknown",
        "basis": "no_current_request_evidence",
    }


def test_b3c_later_request_does_not_inherit_prior_result_visibility(tmp_path):
    client = FakeGitHub(
        target_comments=[
            CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW"),
        ]
    )
    calls = []

    def sleeper(_seconds):
        client.inbox_comments.append(
            CommentRecord(
                id=2,
                body=inbox_marker(
                    request_id="b3c-real-20260616T080001Z",
                    target_dispatch_request_id="b3c-real-20260616T080001Z",
                    action="run-reviewbundle",
                ),
                author="HarryWhite-TW",
            )
        )
        client.target_comments.append(
            CommentRecord(
                id=30,
                body=dispatch_marker(
                    request_id="dispatch-real",
                    action="run-reviewbundle",
                ),
                author="HarryWhite-TW",
            )
        )

    def invoker(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            client.target_comments.append(
                CommentRecord(
                    id=20,
                    body=result_comment(),
                    author="HarryWhite-TW",
                )
            )
            return DispatcherInvocationResult(returncode=0)
        return DispatcherInvocationResult(
            returncode=DISPATCHER_FAILED_BEFORE_RUNNER_EXIT_CODE,
            execution_reach=DISPATCHER_FAILED_BEFORE_RUNNER,
        )

    summary = run_bridge_operator_b3_dry_run_loop(
        repo_root=ROOT_PATH,
        state_dir=tmp_path,
        github_client=client,
        local_checker=ready(tmp_path),
        now_utc=NOW,
        sleeper=sleeper,
        mode=B3C_MODE,
        dispatcher_invoker=invoker,
        timeout_seconds=180,
        max_cycles=2,
    )

    assert summary["request_id"] == "b3c-real-20260616T080001Z"
    assert summary["target_dispatch_request_id"] == "b3c-real-20260616T080001Z"
    assert summary["blocked_reasons"] == ["dispatcher_pre_runner_transient_failure"]
    assert summary["processed_request_written"] is False
    assert summary["processed_request_already_seen"] is False
    assert summary["effective_dispatcher_timeout_seconds"] == 180
    assert "-RelayRequestBase64" in summary["dispatcher_invocation_args"]
    assert summary["dispatcher_result_writeback_reached"] is False
    assert summary["dispatcher_result_writeback_verified"] is False
    assert summary["target_result_verified"] is False
    assert summary["durable_completion_reconciled"] is False
    assert summary["durable_reconciliation_decision"] == "NOT_FOUND"
    assert summary["terminal_result"] is None
    assert summary["terminal_settlement"] is None
    assert summary["terminal_observed_at_utc"] is None
    assert summary["runner_reached"] is False
    assert summary["codex_reached"] is False
    assert summary["current_run"]["current_failure_recorded"] is True
    assert summary["current_run"]["current_failure_reason"] == (
        "dispatcher_pre_runner_transient_failure"
    )
    assert calls[0]["timeout_seconds"] == 120
    assert calls[1]["timeout_seconds"] == 180
    failure = read_json(tmp_path / "last_failure.json")
    assert failure["request_id"] == "b3c-real-20260616T080001Z"
    assert failure["dispatcher_result_writeback_reached"] is False
    assert failure["dispatcher_result_writeback_verified"] is False
    assert failure["durable_reconciliation_decision"] == "NOT_FOUND"
    assert failure["runner_reached"] is False
    assert failure["codex_reached"] is False


def test_b3b_reconciled_restart_uses_local_processed_state_before_provider_read(tmp_path):
    client = FakeGitHub(
        target_comments=[
            CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW"),
            CommentRecord(id=20, body=result_comment(), author="HarryWhite-TW"),
        ]
    )
    first_calls = []

    first = run_b3b(
        tmp_path,
        client,
        dispatcher_invoker=lambda **kwargs: first_calls.append(kwargs),
    )

    class CountingProvider:
        def __init__(self):
            self.calls = 0

        def read_result_comments(self, request):
            self.calls += 1
            raise AssertionError("provider must not be called")

    second_calls = []
    provider = CountingProvider()
    second = run_b3b(
        tmp_path,
        client,
        dispatcher_invoker=lambda **kwargs: second_calls.append(kwargs),
        durable_evidence_provider=provider,
    )

    assert first["result"] == "success"
    assert first["durable_completion_reconciled"] is True
    assert first_calls == []
    assert second["result"] == "success"
    assert second["processed_request_already_seen"] is True
    assert second["dispatcher_invoked"] is False
    assert second["dispatcher_invocation_count"] == 0
    assert second["current_failure_recorded"] is False
    assert provider.calls == 0
    assert second_calls == []
    processed = (tmp_path / "processed_requests.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(processed) == 1
    assert not (tmp_path / "last_failure.json").exists()
    assert_high_risk_safety(second)


def test_b3b_preexisting_terminal_failure_settles_without_dispatcher(tmp_path):
    calls = []
    client = FakeGitHub(
        target_comments=[
            CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW"),
            CommentRecord(id=20, body=result_comment(result="failure"), author="HarryWhite-TW"),
        ]
    )

    summary = run_b3b(
        tmp_path,
        client,
        dispatcher_invoker=lambda **kwargs: calls.append(kwargs),
    )

    assert summary["result"] == "blocked"
    assert summary["blocked_reasons"] == ["durable_terminal_non_success"]
    assert summary["durable_reconciliation_decision"] == "SETTLED_NON_SUCCESS"
    assert summary["durable_reconciliation_reason"] == (
        "EXACTLY_ONE_TRUSTED_NON_SUCCESS_MATCH"
    )
    assert summary["durable_reconciliation_matched_evidence_ids"] == ["20"]
    assert summary["dispatcher_invoked"] is False
    assert summary["dispatcher_invocation_count"] == 0
    assert calls == []
    processed = read_processed_request_records(tmp_path / "processed_requests.jsonl")
    assert processed["b3a-151-20260616T080000Z"]["terminal_result"] == "failure"
    assert processed["b3a-151-20260616T080000Z"]["terminal_settlement"] == (
        "settled_non_success"
    )
    failure = read_json(tmp_path / "last_failure.json")
    assert failure["reason"] == "durable_terminal_non_success"
    assert failure["dispatcher_reached"] is False
    assert failure["durable_reconciliation_reason"] == (
        "EXACTLY_ONE_TRUSTED_NON_SUCCESS_MATCH"
    )
    assert_high_risk_safety(summary)


def test_b3b_durable_provider_error_fails_before_dispatcher(tmp_path):
    calls = []
    client = FakeGitHub(target_comments=[CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW")])

    class ErrorProvider:
        def read_result_comments(self, request):
            raise RuntimeError("provider exploded")

    summary = run_b3b(
        tmp_path,
        client,
        dispatcher_invoker=lambda **kwargs: calls.append(kwargs),
        durable_evidence_provider=ErrorProvider(),
    )

    assert summary["result"] == "blocked"
    assert summary["blocked_reasons"] == ["durable_reconciliation_error"]
    assert summary["durable_reconciliation_decision"] == "ERROR"
    assert summary["durable_reconciliation_reason"] == "PROVIDER_ERROR"
    assert summary["dispatcher_invoked"] is False
    assert calls == []
    assert not (tmp_path / "processed_requests.jsonl").exists()
    assert read_json(tmp_path / "last_failure.json")["dispatcher_reached"] is False
    assert_high_risk_safety(summary)


def test_b3b_unexpected_durable_reconciliation_decision_fails_before_dispatcher(
    tmp_path, monkeypatch
):
    class Value:
        def __init__(self, value):
            self.value = value

    class UnknownDecisionResult:
        decision = Value("UNKNOWN")
        reason = Value("UNKNOWN_REASON")
        matched_evidence_ids = ("20",)
        diagnostics = ("unknown_decision_for_test",)

    monkeypatch.setattr(
        bridge_operator_b3,
        "resolve_durable_completion",
        lambda request, provider, trusted_authors: UnknownDecisionResult(),
    )
    calls = []

    summary = run_b3b(tmp_path, dispatcher_invoker=lambda **kwargs: calls.append(kwargs))

    assert summary["result"] == "blocked"
    assert summary["blocked_reasons"] == ["durable_reconciliation_unexpected_decision"]
    assert summary["durable_reconciliation_decision"] == "UNKNOWN"
    assert summary["durable_reconciliation_reason"] == "UNKNOWN_REASON"
    assert summary["dispatcher_invoked"] is False
    assert summary["dispatcher_invocation_count"] == 0
    assert summary["operator_direct_execution_performed"] is False
    assert calls == []
    assert not (tmp_path / "processed_requests.jsonl").exists()
    failure = read_json(tmp_path / "last_failure.json")
    assert failure["reason"] == "durable_reconciliation_unexpected_decision"
    assert failure["dispatcher_reached"] is False
    assert failure["current_run"]["dispatcher_invoked"] is False
    log = read_log_events(tmp_path / "operator.log")[-1]
    assert log["reason"] == "durable_reconciliation_unexpected_decision"
    assert log["dispatcher_invoked"] is False
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


def test_b3c_accepts_maybe_status_check_through_existing_dispatcher(tmp_path):
    calls = []
    client = FakeGitHub(
        target_comments=[
            CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW"),
        ]
    )

    def invoker(**kwargs):
        calls.append(kwargs)
        client.target_comments.append(
            CommentRecord(id=20, body=result_comment(), author="HarryWhite-TW")
        )
        return DispatcherInvocationResult(returncode=0, stdout="ok", stderr="")

    summary = run_b3c(
        tmp_path,
        client,
        dispatcher_invoker=invoker,
    )

    assert summary["result"] == "success"
    assert summary["blocked_reasons"] == []
    assert summary["dispatcher_invoked"] is True
    assert len(calls) == 1
    assert summary["runner_invoked"] is False
    assert summary["codex_invoked"] is False
    assert summary["approval_consumed"] is False
    assert summary["processed_request_written"] is True
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
                CommentRecord(id=1, body=inbox_marker(request_id="first", target_dispatch_request_id="first"), author="HarryWhite-TW"),
                CommentRecord(id=2, body=inbox_marker(request_id="second", target_dispatch_request_id="second"), author="HarryWhite-TW"),
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

    for index, (reason, invoker) in enumerate(cases):
        case_dir = tmp_path / f"{index}-{reason}"
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

    for index, (reason, invoker) in enumerate(cases):
        case_dir = tmp_path / f"{index}-{reason}"
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


def test_b3c_structured_pre_runner_rejection_is_settled_without_redispatch(tmp_path):
    calls = []

    def invoker(**kwargs):
        calls.append(kwargs)
        return DispatcherInvocationResult(
            returncode=DISPATCHER_REJECTED_BEFORE_RUNNER_EXIT_CODE,
            execution_reach=DISPATCHER_REJECTED_BEFORE_RUNNER,
        )

    first = run_b3c(tmp_path, dispatcher_invoker=invoker)
    second_calls = []
    second = run_b3c(
        tmp_path,
        dispatcher_invoker=lambda **kwargs: second_calls.append(kwargs),
    )

    assert first["blocked_reasons"] == ["dispatcher_rejected_before_runner"]
    assert first["dispatcher_execution_reach"] == DISPATCHER_REJECTED_BEFORE_RUNNER
    assert first["runner_reached"] is False
    assert first["codex_reached"] is False
    assert len(calls) == 1
    assert "-ExpectedDispatchRequestId" not in calls[0]["args"]
    relay_index = calls[0]["args"].index("-RelayRequestBase64")
    relay = json.loads(base64.b64decode(calls[0]["args"][relay_index + 1]).decode("utf-8"))
    assert relay["request_id"] == "b3a-151-20260616T080000Z"
    assert relay["target_dispatch_request_id"] == relay["request_id"]
    assert not (tmp_path / "in_flight.json").exists()
    record = read_processed_request_records(tmp_path / "processed_requests.jsonl")[
        "b3a-151-20260616T080000Z"
    ]
    assert record["completion_source"] == "dispatcher_outcome"
    assert record["dispatcher_execution_reach"] == DISPATCHER_REJECTED_BEFORE_RUNNER
    assert record["result_verified"] is False
    assert record["terminal_settlement"] == "settled_non_success"
    assert second["dispatcher_invoked"] is False
    assert second_calls == []


def test_b3c_notifies_immediately_after_structured_pre_runner_rejection(tmp_path):
    notifications = []

    summary = run_b3c(
        tmp_path,
        dispatcher_invoker=lambda **_: DispatcherInvocationResult(
            returncode=DISPATCHER_REJECTED_BEFORE_RUNNER_EXIT_CODE,
            execution_reach=DISPATCHER_REJECTED_BEFORE_RUNNER,
        ),
        workflow_notifications_enabled=True,
        notification_submitter=lambda title, message: notifications.append(
            (title, message)
        )
        or NotificationSubmission(SUBMITTED, "fake_api_returned", True),
    )

    assert summary["blocked_reasons"] == ["dispatcher_rejected_before_runner"]
    assert summary["workflow_notification_submitted_count"] == 1
    assert len(notifications) == 1
    assert "no Runner or Codex success is claimed" in notifications[0][1]
    assert "awaiting ChatGPT review" in notifications[0][1]


def test_b3c_transient_pre_runner_failure_allows_later_independent_retry(tmp_path):
    first_calls = []
    first = run_b3c(
        tmp_path,
        dispatcher_invoker=lambda **kwargs: first_calls.append(kwargs)
        or DispatcherInvocationResult(
            returncode=DISPATCHER_FAILED_BEFORE_RUNNER_EXIT_CODE,
            execution_reach=DISPATCHER_FAILED_BEFORE_RUNNER,
        ),
    )
    assert first["blocked_reasons"] == ["dispatcher_pre_runner_transient_failure"]
    assert first["dispatcher_execution_reach"] == DISPATCHER_FAILED_BEFORE_RUNNER
    assert first["runner_reached"] is False
    assert first["codex_reached"] is False
    assert first["processed_request_written"] is False
    assert len(first_calls) == 1
    assert not (tmp_path / "in_flight.json").exists()
    assert not (tmp_path / "processed_requests.jsonl").exists()

    second_calls = []
    second = run_b3c(
        tmp_path,
        dispatcher_invoker=lambda **kwargs: second_calls.append(kwargs)
        or DispatcherInvocationResult(returncode=0),
    )

    assert second["result"] == "success"
    assert second["processed_request_written"] is True
    assert len(second_calls) == 1


def test_b3c_uncertain_dispatcher_reach_remains_fail_closed(tmp_path):
    calls = []
    summary = run_b3c(
        tmp_path,
        dispatcher_invoker=lambda **kwargs: calls.append(kwargs)
        or DispatcherInvocationResult(
            returncode=DISPATCHER_RUNNER_REACH_UNCERTAIN_EXIT_CODE,
            execution_reach=DISPATCHER_RUNNER_MAY_HAVE_STARTED,
        ),
    )

    assert summary["blocked_reasons"] == ["dispatcher_nonzero_exit"]
    assert summary["dispatcher_execution_reach"] == DISPATCHER_RUNNER_MAY_HAVE_STARTED
    assert summary["runner_reached"] is None
    assert summary["codex_reached"] is None
    assert read_json(tmp_path / "in_flight.json")["stage"] == (
        DISPATCHED_NOT_LOCALLY_SETTLED
    )
    assert not (tmp_path / "processed_requests.jsonl").exists()
    assert len(calls) == 1


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


def test_b3b_untrusted_result_reaches_writeback_but_is_not_settled(tmp_path):
    client = FakeGitHub(
        target_comments=[
            CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW"),
        ]
    )
    summary = run_b3b(
        tmp_path,
        client,
        dispatcher_invoker=lambda **_: client.target_comments.append(
            CommentRecord(id=20, body=result_comment(), author="other-user")
        )
        or DispatcherInvocationResult(returncode=0, stdout="ok", stderr=""),
    )

    assert summary["blocked_reasons"] == ["untrusted_result_author"]
    assert summary["dispatcher_invocation_count"] == 1
    assert summary["dispatcher_result_writeback_reached"] is True
    assert summary["dispatcher_result_writeback_verified"] is False
    assert summary["target_result_verified"] is False
    failure = read_json(tmp_path / "last_failure.json")
    assert failure["dispatcher_result_writeback_reached"] is True
    assert failure["dispatcher_result_writeback_verified"] is False
    assert not (tmp_path / "processed_requests.jsonl").exists()
    assert_high_risk_safety(summary)


def test_b3b_terminal_failure_is_verified_and_settled_non_success(tmp_path):
    client = FakeGitHub(
        target_comments=[
            CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW"),
        ]
    )
    summary = run_b3b(
        tmp_path,
        client,
        dispatcher_invoker=lambda **_: client.target_comments.append(
            CommentRecord(
                id=20,
                body=result_comment(result="failure"),
                author="HarryWhite-TW",
            )
        )
        or DispatcherInvocationResult(returncode=0, stdout="ok", stderr=""),
    )

    assert summary["blocked_reasons"] == ["target_result_not_success"]
    assert summary["dispatcher_result_writeback_verified"] is True
    assert summary["target_result_verified"] is True
    assert summary["terminal_result"] == "failure"
    assert summary["terminal_settlement"] == "settled_non_success"
    assert summary["terminal_observed_at_utc"] == "2026-06-16T08:00:00Z"
    processed = read_processed_request_records(tmp_path / "processed_requests.jsonl")
    record = processed["b3a-151-20260616T080000Z"]
    assert record["terminal_result"] == "failure"
    assert record["terminal_settlement"] == "settled_non_success"
    assert record["terminal_observed_at_utc"] == "2026-06-16T08:00:00Z"
    assert not (tmp_path / "in_flight.json").exists()
    assert_high_risk_safety(summary)


def test_b3c_notifies_once_after_durable_verified_success(tmp_path):
    notifications = []

    summary = run_b3c(
        tmp_path,
        workflow_notifications_enabled=True,
        notification_submitter=lambda title, message: notifications.append(
            (title, message)
        )
        or NotificationSubmission(SUBMITTED, "fake_api_returned", True),
    )

    assert summary["result"] == "success"
    assert summary["target_result_verified"] is True
    assert summary["workflow_notification_activation_created"] is True
    assert summary["workflow_notification_submitted_count"] == 1
    assert summary["workflow_notification_ambiguous_count"] == 0
    assert len(notifications) == 1
    assert "completed successfully" in notifications[0][1]
    assert "awaiting ChatGPT review" in notifications[0][1]


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

    assert active_lock["blocked_reasons"] == [
        "legacy_lock_manual_recovery_required"
    ]
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


def test_normal_control_relay_does_not_require_target_dispatch_marker(tmp_path):
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

    assert missing["result"] == "success"
    assert duplicate["result"] == "success"
    assert missing["target_dispatch_request_id"] == missing["request_id"]
    assert duplicate["target_dispatch_request_id"] == duplicate["request_id"]
    assert missing["current_run"]["request_id"] == missing["request_id"]


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


def test_dirty_same_node_continuation_requires_matching_launcher_binding_before_dispatch(
    tmp_path, monkeypatch
):
    parent_id = "5311"
    expected_state = (
        "same_node_exact_candidate_continuation_v1:parent_comment_id=" + parent_id
    )

    def make_client():
        return FakeGitHub(
            inbox_comments=[
                CommentRecord(
                    id=1,
                    body=inbox_marker(action="run-reviewbundle", expected_state=expected_state),
                    author="HarryWhite-TW",
                )
            ],
            target_comments=[
                CommentRecord(
                    id=int(parent_id),
                    body=result_comment(
                        action="run-reviewbundle", request_id="trusted-parent-dispatch"
                    ),
                    author="HarryWhite-TW",
                ),
            ],
        )

    def binding(**overrides):
        value = {
            "protocol": "lawb.same_node_exact_candidate_continuation_launcher_binding.v1",
            "repository": DEFAULT_REPOSITORY,
            "issue": 151,
            "parent_comment_id": parent_id,
            "branch": "feature/bridge-operator-b3a",
            "head": HEAD,
            "candidate_manifest_fingerprint": "a" * 64,
            "remaining_budget_before": 1,
            "is_human_approval": False,
        }
        value.update(overrides)
        return json.dumps(value, separators=(",", ":"))

    missing_calls = []
    monkeypatch.delenv("LAWB_SAME_NODE_CONTINUATION_BINDING", raising=False)
    missing = run_b3c(
        tmp_path / "missing",
        client=make_client(),
        readiness=ready(tmp_path / "missing", clean=False, staged_clean=True),
        dispatcher_invoker=lambda **kwargs: missing_calls.append(kwargs),
    )
    assert "same_node_continuation_launcher_binding_missing" in missing["blocked_reasons"]
    assert missing_calls == []
    assert_safety(missing)

    mismatch_calls = []
    monkeypatch.setenv(
        "LAWB_SAME_NODE_CONTINUATION_BINDING", binding(head="b" * 40)
    )
    mismatch = run_b3c(
        tmp_path / "mismatch",
        client=make_client(),
        readiness=ready(tmp_path / "mismatch", clean=False, staged_clean=True),
        dispatcher_invoker=lambda **kwargs: mismatch_calls.append(kwargs),
    )
    assert "same_node_continuation_launcher_binding_mismatch" in mismatch["blocked_reasons"]
    assert mismatch_calls == []
    assert_safety(mismatch)

    client = make_client()
    admitted_calls = []

    def admitted_invoker(**kwargs):
        admitted_calls.append(kwargs)
        client.target_comments.append(
            CommentRecord(
                id=20,
                body=result_comment(action="run-reviewbundle"),
                author="HarryWhite-TW",
            )
        )
        return DispatcherInvocationResult(returncode=0, stdout="ok", stderr="")

    monkeypatch.setenv("LAWB_SAME_NODE_CONTINUATION_BINDING", binding())
    admitted = run_b3c(
        tmp_path / "admitted",
        client=client,
        readiness=ready(tmp_path / "admitted", clean=False, staged_clean=True),
        dispatcher_invoker=admitted_invoker,
    )
    assert admitted["result"] == "success"
    assert admitted["dispatcher_invocation_count"] == 1
    assert len(admitted_calls) == 1
    evidence = admitted["same_node_candidate_continuation"]
    assert evidence["launcher_binding"] == "matched"
    assert evidence["is_human_approval"] is False
    assert evidence["remaining_budget_before"] == 1


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
    limit_dir = tmp_path / "limit"
    limit_dir.mkdir()
    (limit_dir / "stop.flag").write_text("", encoding="utf-8")
    assert run(limit_dir, max_cycles=960)["stop_requested"] is True
    assert run(tmp_path / "bad-max", max_cycles=961)["blocked_reasons"] == [
        "invalid_max_cycles"
    ]
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
    assert summary["blocked_reasons"] == [
        "legacy_lock_manual_recovery_required"
    ]
    assert lock.exists()
    assert "old" in lock.read_text(encoding="utf-8")
    assert (
        read_json(tmp_path / "last_failure.json")["reason"]
        == "legacy_lock_manual_recovery_required"
    )
    assert_safety(summary)


def test_heartbeat_writes_expected_fields(tmp_path):
    summary = run(tmp_path)
    heartbeat = read_json(tmp_path / "heartbeat.json")

    assert heartbeat["protocol"] == "lawb.bridge_operator_b3_heartbeat.v1"
    assert heartbeat["mode"] == "b3a-dry-run"
    assert heartbeat["repo"] == "HarryWhite-TW/local-ai-workbench"
    assert heartbeat["inbox_issue"] == DEFAULT_INBOX_ISSUE
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


def test_processed_history_accepts_legacy_and_current_consumed_records(tmp_path):
    legacy = processed_record()
    current = processed_record(
        request_id="b3a-151-20260616T080000Z",
        lifecycle_state="CONSUMED",
        dispatcher_invoked=True,
        result_verified=True,
    )
    path = tmp_path / "processed_requests.jsonl"
    path.write_text(
        json.dumps(legacy, sort_keys=True) + "\n" + json.dumps(current, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    assert read_processed_request_ids(path) == {
        "processed-a",
        "b3a-151-20260616T080000Z",
    }


def test_processed_history_accepts_full_legacy_processed_record(tmp_path):
    request_id = "legacy-processed-151"
    path = tmp_path / "processed_requests.jsonl"
    path.write_text(
        json.dumps(
            {
                "protocol": PROCESSED_REQUEST_PROTOCOL,
                "processed_at_utc": "2026-06-16T08:00:00Z",
                "cycle": 1,
                "request_id": request_id,
                "target_issue": 151,
                "target_dispatch_request_id": "dispatch-151",
                "requested_action": "maybe-status-check",
                "expected_branch": "feature/bridge-operator-b3a",
                "expected_head": HEAD,
                "target_result_comment_id": 20,
                "target_result_author": "HarryWhite-TW",
                "dispatcher_invoked": True,
                "result_verified": True,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    assert read_processed_request_ids(path) == {request_id}


def test_processed_history_accepts_reconciled_consumed_record(tmp_path):
    request_id = "reconciled-151"
    path = tmp_path / "processed_requests.jsonl"
    path.write_text(
        json.dumps(
            {
                "protocol": PROCESSED_REQUEST_PROTOCOL,
                "processed_at_utc": "2026-06-16T08:00:00Z",
                "cycle": 1,
                "request_id": request_id,
                "target_issue": 151,
                "target_dispatch_request_id": "dispatch-151",
                "requested_action": "maybe-status-check",
                "expected_branch": "feature/bridge-operator-b3a",
                "expected_head": HEAD,
                "lifecycle_state": "CONSUMED",
                "completion_source": "durable_evidence_reconciliation",
                "dispatcher_invoked": False,
                "result_verified": True,
                "reconciliation_decision": "COMPLETED",
                "reconciliation_reason": "EXACTLY_ONE_TRUSTED_MATCH",
                "reconciliation_matched_evidence_ids": ["20"],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    records = read_processed_request_records(path)

    assert set(records) == {request_id}
    assert records[request_id]["completion_source"] == "durable_evidence_reconciliation"


def test_processed_history_rejects_identityless_minimal_legacy_record(tmp_path):
    path = tmp_path / "processed_requests.jsonl"
    path.write_text(
        json.dumps(
            {
                "protocol": PROCESSED_REQUEST_PROTOCOL,
                "request_id": "legacy-minimal-151",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        read_processed_request_ids(path)


def test_processed_history_rejects_duplicate_request_id_records(tmp_path):
    path = tmp_path / "processed_requests.jsonl"
    path.write_text(
        json.dumps(processed_record(), sort_keys=True)
        + "\n"
        + json.dumps(processed_record(target_issue=152), sort_keys=True)
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        read_processed_request_ids(path)


@pytest.mark.parametrize(
    "payload",
    [
        processed_record(protocol="wrong"),
        processed_record(request_id=None),
        processed_record(request_id=["processed-a"]),
        processed_record(request_id=123),
        processed_record(request_id=""),
        processed_record(request_id="-bad"),
        processed_record(lifecycle_state="CURRENT"),
        processed_record(dispatcher_invoked=False),
        processed_record(completion_source="unknown"),
        processed_record(
            completion_source="durable_evidence_reconciliation",
            dispatcher_invoked="yes",
            result_verified=True,
            lifecycle_state="CONSUMED",
            reconciliation_decision="COMPLETED",
            reconciliation_reason="EXACTLY_ONE_TRUSTED_MATCH",
            reconciliation_matched_evidence_ids=["20"],
        ),
        processed_record(
            completion_source="durable_evidence_reconciliation",
            dispatcher_invoked=False,
            result_verified=True,
            lifecycle_state="CONSUMED",
            reconciliation_decision="BLOCKED",
            reconciliation_reason="EXACTLY_ONE_TRUSTED_MATCH",
            reconciliation_matched_evidence_ids=["20"],
        ),
        processed_record(
            completion_source="durable_evidence_reconciliation",
            dispatcher_invoked=False,
            result_verified=True,
            lifecycle_state="CONSUMED",
            reconciliation_decision="COMPLETED",
            reconciliation_reason="NON_SUCCESS_RESULT",
            reconciliation_matched_evidence_ids=["20"],
        ),
        processed_record(
            completion_source="durable_evidence_reconciliation",
            dispatcher_invoked=False,
            result_verified=True,
            lifecycle_state="CONSUMED",
            reconciliation_decision="COMPLETED",
            reconciliation_reason="EXACTLY_ONE_TRUSTED_MATCH",
            reconciliation_matched_evidence_ids=[],
        ),
        processed_record(
            completion_source="durable_evidence_reconciliation",
            dispatcher_invoked=False,
            result_verified=True,
            lifecycle_state="CONSUMED",
            reconciliation_decision="COMPLETED",
            reconciliation_reason="EXACTLY_ONE_TRUSTED_MATCH",
            reconciliation_matched_evidence_ids=["20", "21"],
        ),
        processed_record(
            completion_source="durable_evidence_reconciliation",
            dispatcher_invoked=False,
            result_verified=True,
            lifecycle_state="CONSUMED",
            reconciliation_decision="COMPLETED",
            reconciliation_reason="EXACTLY_ONE_TRUSTED_MATCH",
            reconciliation_matched_evidence_ids=[""],
        ),
        processed_record(
            completion_source="durable_evidence_reconciliation",
            dispatcher_invoked=False,
            result_verified=True,
            lifecycle_state="CONSUMED",
            reconciliation_decision="COMPLETED",
            reconciliation_reason="EXACTLY_ONE_TRUSTED_MATCH",
            reconciliation_matched_evidence_ids=[123],
        ),
        processed_record(
            completion_source="durable_evidence_reconciliation",
            dispatcher_invoked=False,
            result_verified=True,
            lifecycle_state="CONSUMED",
            reconciliation_decision="COMPLETED",
            reconciliation_reason="EXACTLY_ONE_TRUSTED_MATCH",
            reconciliation_matched_evidence_ids="20",
        ),
        processed_record(
            completion_source="durable_evidence_reconciliation",
            dispatcher_invoked=False,
            result_verified=True,
            lifecycle_state="CONSUMED",
            reconciliation_decision="COMPLETED",
            reconciliation_reason="EXACTLY_ONE_TRUSTED_MATCH",
            reconciliation_matched_evidence_ids=None,
        ),
        processed_record(result_verified=False),
        processed_record(target_issue="151"),
        processed_record(target_issue=True),
        processed_record(target_dispatch_request_id=""),
        processed_record(requested_action=""),
        processed_record(expected_branch=""),
        processed_record(expected_head=""),
    ],
)
def test_processed_history_rejects_semantically_malformed_records(tmp_path, payload):
    path = tmp_path / "processed_requests.jsonl"
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError):
        read_processed_request_ids(path)


@pytest.mark.parametrize(
    "line",
    [
        '{"protocol":"lawb.bridge_operator_b3_processed_request.v1","request_id":"processed-a","request_id":"processed-b"}',
        "{not-json}",
    ],
)
def test_processed_history_rejects_duplicate_keys_and_malformed_json(tmp_path, line):
    path = tmp_path / "processed_requests.jsonl"
    path.write_text(line + "\n", encoding="utf-8")

    with pytest.raises(ValueError):
        read_processed_request_ids(path)


def test_processed_history_rejects_top_level_non_object_before_dispatcher(tmp_path):
    path = tmp_path / "processed_requests.jsonl"
    path.write_text("[]\n", encoding="utf-8")
    calls = []

    with pytest.raises(ValueError):
        read_processed_request_ids(path)

    summary = run_b3b(tmp_path, dispatcher_invoker=lambda **kwargs: calls.append(kwargs))

    assert summary["result"] == "blocked"
    assert summary["blocked_reasons"] == ["corrupted_state"]
    assert summary["dispatcher_invoked"] is False
    assert calls == []
    assert read_json(tmp_path / "last_failure.json")["reason"] == "corrupted_state"


def test_b3_does_not_invoke_dispatcher_after_processed_history_validation_failure(tmp_path):
    (tmp_path / "processed_requests.jsonl").write_text(
        json.dumps(processed_record(dispatcher_invoked=False), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    calls = []

    summary = run_b3b(tmp_path, dispatcher_invoker=lambda **kwargs: calls.append(kwargs))

    assert summary["result"] == "blocked"
    assert summary["blocked_reasons"] == ["corrupted_state"]
    assert summary["dispatcher_invoked"] is False
    assert calls == []
    assert read_json(tmp_path / "last_failure.json")["reason"] == "corrupted_state"


def test_b3_blocks_dispatcher_when_processed_identity_mismatches_current_request(tmp_path):
    (tmp_path / "processed_requests.jsonl").write_text(
        json.dumps(processed_record(request_id="b3a-151-20260616T080000Z", target_issue=999), sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    calls = []

    summary = run_b3b(tmp_path, dispatcher_invoker=lambda **kwargs: calls.append(kwargs))

    assert summary["result"] == "blocked"
    assert summary["blocked_reasons"] == ["processed_request_identity_mismatch"]
    assert summary["dispatcher_invoked"] is False
    assert summary["dispatcher_invocation_count"] == 0
    assert calls == []
    assert read_json(tmp_path / "last_failure.json")["reason"] == "processed_request_identity_mismatch"
    assert_high_risk_safety(summary)


def test_b3_second_read_blocks_dispatcher_when_race_writes_identity_mismatch(tmp_path):
    def racing_checker(root):
        (tmp_path / "processed_requests.jsonl").write_text(
            json.dumps(
                processed_record(
                    request_id="b3a-151-20260616T080000Z",
                    target_issue=999,
                ),
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return ready(tmp_path)(root)

    calls = []

    summary = run_b3b(
        tmp_path,
        readiness=racing_checker,
        dispatcher_invoker=lambda **kwargs: calls.append(kwargs),
    )

    assert summary["result"] == "blocked"
    assert summary["blocked_reasons"] == ["processed_request_identity_mismatch"]
    assert summary["dispatcher_invoked"] is False
    assert summary["dispatcher_invocation_count"] == 0
    assert calls == []
    assert read_json(tmp_path / "last_failure.json")["reason"] == (
        "processed_request_identity_mismatch"
    )
    assert_high_risk_safety(summary)


def test_b3_second_read_treats_matching_race_record_as_already_processed(tmp_path):
    def racing_checker(root):
        (tmp_path / "processed_requests.jsonl").write_text(
            json.dumps(
                processed_record(request_id="b3a-151-20260616T080000Z"),
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return ready(tmp_path)(root)

    calls = []

    summary = run_b3b(
        tmp_path,
        readiness=racing_checker,
        dispatcher_invoker=lambda **kwargs: calls.append(kwargs),
    )

    assert summary["result"] == "success"
    assert summary["processed_request_already_seen"] is True
    assert summary["phase"] == "already_processed"
    assert summary["dispatcher_invoked"] is False
    assert summary["dispatcher_invocation_count"] == 0
    assert summary["processed_request_written"] is False
    assert summary["current_failure_recorded"] is False
    assert not (tmp_path / "last_failure.json").exists()
    assert calls == []
    assert_high_risk_safety(summary)


@pytest.mark.parametrize(
    "content",
    [
        "{not-json}\n",
        json.dumps(processed_record(request_id="b3a-151-20260616T080000Z"), sort_keys=True)
        + "\n"
        + json.dumps(processed_record(request_id="b3a-151-20260616T080000Z"), sort_keys=True)
        + "\n",
    ],
)
def test_b3_second_read_corrupted_state_blocks_without_exception(tmp_path, content):
    def racing_checker(root):
        (tmp_path / "processed_requests.jsonl").write_text(content, encoding="utf-8")
        return ready(tmp_path)(root)

    calls = []

    summary = run_b3b(
        tmp_path,
        readiness=racing_checker,
        dispatcher_invoker=lambda **kwargs: calls.append(kwargs),
    )

    assert summary["result"] == "blocked"
    assert summary["blocked_reasons"] == ["corrupted_state"]
    assert summary["dispatcher_invoked"] is False
    assert summary["dispatcher_invocation_count"] == 0
    assert calls == []
    assert read_json(tmp_path / "last_failure.json")["reason"] == "corrupted_state"
    assert_high_risk_safety(summary)


def test_local_checker_value_error_is_not_mislabeled_as_corrupted_processed_history(tmp_path):
    existing = {
        "protocol": "lawb.bridge_operator_b3_processed_request.v1",
        "request_id": "unrelated-processed",
        "lifecycle_state": "CONSUMED",
        "target_issue": 151,
        "target_dispatch_request_id": "dispatch-151",
        "requested_action": "maybe-status-check",
        "expected_branch": "feature/bridge-operator-b3a",
        "expected_head": HEAD,
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


def test_health_probe_expiry_and_dispatch_timeout_are_bounded(tmp_path):
    calls = []
    too_long = FakeGitHub(
        inbox_comments=[
            CommentRecord(
                id=1,
                body=inbox_marker(expires="20260616T080501Z"),
                author="HarryWhite-TW",
            )
        ],
        target_comments=[
            CommentRecord(
                id=10,
                body=dispatch_marker(expires="20260616T080501Z"),
                author="HarryWhite-TW",
            )
        ],
    )

    blocked = run_b3b(
        tmp_path / "expiry",
        too_long,
        dispatcher_invoker=lambda **kwargs: calls.append(kwargs),
    )
    bounded = run_b3b(
        tmp_path / "timeout",
        timeout_seconds=600,
        dispatcher_invoker=lambda **kwargs: calls.append(kwargs)
        or DispatcherInvocationResult(returncode=0, stdout="ok", stderr=""),
    )

    assert blocked["result"] == "success"
    assert blocked["blocked_reasons"] == []
    assert blocked["nonfatal_request_rejection_count"] == 1
    assert blocked["last_nonfatal_request_rejection_reason"] == (
        "health_probe_expiry_exceeds_5_minutes"
    )
    assert blocked["dispatcher_invoked"] is False
    assert bounded["result"] == "success"
    assert bounded["health_probe_request_remaining_seconds"] == 300
    assert bounded["effective_dispatcher_timeout_seconds"] == 120
    assert calls[-1]["timeout_seconds"] == 120
    assert bounded["health_probe_to_real_task_seconds"] == 60
    assert bounded["runner_invoked"] is False
    assert bounded["codex_invoked"] is False


def test_b3c_nonfatal_probe_rejection_is_suppressed_and_later_request_runs(
    tmp_path,
):
    rejected_request_id = "probe-too-long"
    valid_request_id = "probe-valid"
    client = FakeGitHub(
        inbox_comments=[
            CommentRecord(
                id=1,
                body=inbox_marker(
                    request_id=rejected_request_id,
                    target_dispatch_request_id=rejected_request_id,
                    expires="20260616T080501Z",
                ),
                author="HarryWhite-TW",
            )
        ],
        target_comments=[
            CommentRecord(
                id=10,
                body=dispatch_marker(
                    request_id="dispatch-too-long",
                    expires="20260616T080501Z",
                ),
                author="HarryWhite-TW",
            )
        ],
    )
    sleeps = []
    calls = []

    def sleeper(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            client.inbox_comments = [
                CommentRecord(
                    id=2,
                    body=inbox_marker(
                        request_id=valid_request_id,
                        target_dispatch_request_id=valid_request_id,
                    ),
                    author="HarryWhite-TW",
                )
            ]
            client.target_comments = [
                CommentRecord(
                    id=11,
                    body=dispatch_marker(request_id="dispatch-valid"),
                    author="HarryWhite-TW",
                )
            ]

    def invoker(**kwargs):
        calls.append(kwargs)
        client.target_comments.append(
            CommentRecord(
                id=20,
                body=result_comment(request_id=valid_request_id),
                author="HarryWhite-TW",
            )
        )
        return DispatcherInvocationResult(returncode=0, stdout="ok", stderr="")

    summary = run_bridge_operator_b3_dry_run_loop(
        repo_root=ROOT_PATH,
        state_dir=tmp_path,
        github_client=client,
        local_checker=ready(tmp_path),
        now_utc=NOW,
        sleeper=sleeper,
        max_cycles=3,
        poll_interval_seconds=1,
        mode=B3C_MODE,
        dispatcher_invoker=invoker,
        timeout_seconds=30,
        operator_session_id=SESSION_A,
        process_identity=fake_process_identity(),
    )

    assert summary["result"] == "success"
    assert summary["cycles_completed"] == 3
    assert summary["nonfatal_request_rejection_count"] == 1
    assert summary["suppressed_request_rejection_cycle_count"] == 1
    assert summary["last_nonfatal_request_rejection_reason"] == (
        "health_probe_expiry_exceeds_5_minutes"
    )
    assert summary["last_nonfatal_request_rejection_request_id"] == (
        rejected_request_id
    )
    assert summary["dispatcher_invocation_count"] == 1
    assert summary["dispatcher_invoked"] is True
    assert summary["runner_invoked"] is False
    assert summary["codex_invoked"] is False
    assert len(calls) == 1
    assert sleeps == [1, 1]
    assert not (tmp_path / "in_flight.json").exists()
    assert not (tmp_path / "last_failure.json").exists()

    processed = read_processed_request_records(
        tmp_path / "processed_requests.jsonl",
        repository=DEFAULT_REPOSITORY,
    )
    assert rejected_request_id not in processed
    assert list(processed) == [valid_request_id]

    rejection_logs = [
        event
        for event in read_log_events(tmp_path / "operator.log")
        if event["event"] == "request_rejected"
    ]
    assert len(rejection_logs) == 1
    assert rejection_logs[0]["request_id"] == rejected_request_id
    assert rejection_logs[0]["reason"] == "health_probe_expiry_exceeds_5_minutes"

    heartbeat = read_json(tmp_path / "heartbeat.json")
    assert heartbeat["cycle"] == 3
    assert heartbeat["operator_session_id"] == SESSION_A


@pytest.mark.parametrize(
    ("stage", "expected_stage", "expected_dispatches", "processed"),
    [
        ("before_durable_admit", None, 0, False),
        ("after_prepared_before_dispatch", PREPARED, 0, False),
        (
            "after_dispatch_before_processed",
            DISPATCHED_NOT_LOCALLY_SETTLED,
            1,
            False,
        ),
        ("after_processed_durable", PROCESSED, 1, True),
    ],
)
def test_fault_injection_preserves_exact_ordering_stage(
    tmp_path,
    stage,
    expected_stage,
    expected_dispatches,
    processed,
):
    calls = []
    summary = run_b3b(
        tmp_path,
        dispatcher_invoker=lambda **kwargs: calls.append(kwargs)
        or DispatcherInvocationResult(returncode=0, stdout="ok", stderr=""),
        operator_session_id=SESSION_A,
        process_identity=fake_process_identity(),
        lifecycle_fault_injector=inject_at(stage),
    )

    assert summary["result"] == "blocked"
    assert summary["blocked_reasons"] == [f"fault_injected_{stage}"]
    assert len(calls) == expected_dispatches
    in_flight_path = tmp_path / "in_flight.json"
    if expected_stage is None:
        assert not in_flight_path.exists()
        assert not (tmp_path / "operator.lock").exists()
    else:
        assert read_json(in_flight_path)["stage"] == expected_stage
        assert (tmp_path / "operator.lock").exists()
    assert (tmp_path / "processed_requests.jsonl").exists() is processed


def test_prepared_restart_is_uncertain_zero_redispatch_and_no_quarantine(tmp_path):
    client = FakeGitHub()
    first_calls = []
    first = run_b3b(
        tmp_path,
        client,
        dispatcher_invoker=lambda **kwargs: first_calls.append(kwargs),
        operator_session_id=SESSION_A,
        process_identity=fake_process_identity(),
        lifecycle_fault_injector=inject_at("after_prepared_before_dispatch"),
    )
    lock_path = tmp_path / "operator.lock"
    before_lock = lock_path.read_bytes()
    second_calls = []

    second = run_b3b(
        tmp_path,
        client,
        dispatcher_invoker=lambda **kwargs: second_calls.append(kwargs),
        operator_session_id=SESSION_B,
        process_identity=fake_process_identity(
            pid=4102,
            token="windows-filetime:41020000",
        ),
        process_probe=lambda _: process_observation("dead"),
    )

    assert first["in_flight_stage"] == PREPARED
    assert first_calls == []
    assert second["blocked_reasons"] == ["prepared_in_flight_uncertain"]
    assert second["restart_reconciliation_performed"] is True
    assert second["dispatcher_invoked"] is False
    assert second_calls == []
    assert read_json(tmp_path / "in_flight.json")["stage"] == PREPARED
    assert lock_path.read_bytes() == before_lock
    assert list(tmp_path.glob("operator.lock.quarantine.*.json")) == []


def test_pre_runner_rejection_restart_settles_locally_without_redispatch(tmp_path):
    client = FakeGitHub(
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
    )
    first_calls = []
    first = run_b3c(
        tmp_path,
        client,
        dispatcher_invoker=lambda **kwargs: first_calls.append(kwargs)
        or DispatcherInvocationResult(
            returncode=DISPATCHER_REJECTED_BEFORE_RUNNER_EXIT_CODE,
            execution_reach=DISPATCHER_REJECTED_BEFORE_RUNNER,
        ),
        operator_session_id=SESSION_A,
        process_identity=fake_process_identity(),
        lifecycle_fault_injector=inject_at(
            "after_pre_runner_rejection_before_processed"
        ),
    )
    second_calls = []
    second = run_b3c(
        tmp_path,
        client,
        dispatcher_invoker=lambda **kwargs: second_calls.append(kwargs),
        operator_session_id=SESSION_B,
        process_identity=fake_process_identity(
            pid=4102,
            token="windows-filetime:41020000",
        ),
        process_probe=lambda _: process_observation("pid_reused"),
    )

    assert len(first_calls) == 1
    assert first["in_flight_stage"] == REJECTED_BEFORE_RUNNER
    assert second["blocked_reasons"] == [
        "restart_reconciled_terminal_non_success"
    ]
    assert second["restart_reconciliation_performed"] is True
    assert second["dispatcher_execution_reach"] == DISPATCHER_REJECTED_BEFORE_RUNNER
    assert second["runner_reached"] is False
    assert second["codex_reached"] is False
    assert second_calls == []
    assert not (tmp_path / "in_flight.json").exists()
    record = read_processed_request_records(tmp_path / "processed_requests.jsonl")[
        "b3a-151-20260616T080000Z"
    ]
    assert record["completion_source"] == "dispatcher_outcome"
    assert record["terminal_settlement"] == "settled_non_success"


@pytest.mark.parametrize("terminal_result", ["success", "failure", "blocked"])
def test_dispatched_restart_settles_each_unique_terminal_without_redispatch(
    tmp_path,
    terminal_result,
):
    client = FakeGitHub()
    first_calls = []

    def first_invoker(**kwargs):
        first_calls.append(kwargs)
        client.target_comments.append(
            CommentRecord(
                id=20,
                body=result_comment(result=terminal_result),
                author="HarryWhite-TW",
            )
        )
        return DispatcherInvocationResult(returncode=0, stdout="ok", stderr="")

    first = run_b3b(
        tmp_path,
        client,
        dispatcher_invoker=first_invoker,
        operator_session_id=SESSION_A,
        process_identity=fake_process_identity(),
        lifecycle_fault_injector=inject_at("after_dispatch_before_processed"),
    )
    second_calls = []
    second = run_b3b(
        tmp_path,
        client,
        dispatcher_invoker=lambda **kwargs: second_calls.append(kwargs),
        operator_session_id=SESSION_B,
        process_identity=fake_process_identity(
            pid=4102,
            token="windows-filetime:41020000",
        ),
        process_probe=lambda _: process_observation("pid_reused"),
    )

    assert first["in_flight_stage"] == DISPATCHED_NOT_LOCALLY_SETTLED
    assert len(first_calls) == 1
    assert second["restart_reconciliation_performed"] is True
    assert second["dispatcher_invoked"] is False
    assert second_calls == []
    assert not (tmp_path / "in_flight.json").exists()
    assert len(list(tmp_path.glob("operator.lock.quarantine.*.json"))) == 1
    record = read_processed_request_records(
        tmp_path / "processed_requests.jsonl"
    )["b3a-151-20260616T080000Z"]
    assert record["terminal_result"] == terminal_result
    expected_settlement = (
        "settled_success"
        if terminal_result == "success"
        else "settled_non_success"
    )
    assert record["terminal_settlement"] == expected_settlement
    if terminal_result == "success":
        assert second["result"] == "success"
    else:
        assert second["blocked_reasons"] == [
            "restart_reconciled_terminal_non_success"
        ]


@pytest.mark.parametrize(
    ("case", "expected_reason"),
    [
        ("zero", "ZERO_MATCHING_COMPLETIONS"),
        ("multiple", "MULTIPLE_MATCHING_COMPLETIONS"),
        ("untrusted", "UNTRUSTED_AUTHOR"),
        ("provider_unavailable", "PROVIDER_UNAVAILABLE"),
        ("malformed", "MALFORMED_EVIDENCE"),
        ("identity_mismatch", "HEAD_MISMATCH"),
    ],
)
def test_dispatched_restart_uncertain_evidence_never_redispatches(
    tmp_path,
    case,
    expected_reason,
):
    client = FakeGitHub()

    def first_invoker(**_):
        if case == "multiple":
            client.target_comments.extend(
                [
                    CommentRecord(id=20, body=result_comment(), author="HarryWhite-TW"),
                    CommentRecord(id=21, body=result_comment(), author="HarryWhite-TW"),
                ]
            )
        elif case == "untrusted":
            client.target_comments.append(
                CommentRecord(id=20, body=result_comment(), author="outsider")
            )
        elif case == "malformed":
            client.target_comments.append(
                CommentRecord(
                    id=20,
                    body="LAWBRUNNER-RESULT protocol=lawb.runner_result.v1\n{",
                    author="HarryWhite-TW",
                )
            )
        elif case == "identity_mismatch":
            client.target_comments.append(
                CommentRecord(
                    id=20,
                    body=result_comment(head="1" * 40),
                    author="HarryWhite-TW",
                )
            )
        return DispatcherInvocationResult(returncode=0, stdout="ok", stderr="")

    run_b3b(
        tmp_path,
        client,
        dispatcher_invoker=first_invoker,
        operator_session_id=SESSION_A,
        process_identity=fake_process_identity(),
        lifecycle_fault_injector=inject_at("after_dispatch_before_processed"),
    )
    lock_path = tmp_path / "operator.lock"
    in_flight_path = tmp_path / "in_flight.json"
    lock_before = lock_path.read_bytes()
    in_flight_before = in_flight_path.read_bytes()
    second_calls = []

    class UnavailableProvider:
        def read_result_comments(self, request):
            return EvidenceReadResult(
                status=ProviderStatus.UNAVAILABLE,
                comments=(),
                diagnostics=("test_provider_unavailable",),
            )

    second = run_b3b(
        tmp_path,
        client,
        dispatcher_invoker=lambda **kwargs: second_calls.append(kwargs),
        operator_session_id=SESSION_B,
        process_identity=fake_process_identity(
            pid=4102,
            token="windows-filetime:41020000",
        ),
        process_probe=lambda _: process_observation("dead"),
        durable_evidence_provider=(
            UnavailableProvider() if case == "provider_unavailable" else None
        ),
    )

    assert second["blocked_reasons"] == ["dispatched_in_flight_uncertain"]
    assert second["durable_reconciliation_reason"] == expected_reason
    assert second["dispatcher_invoked"] is False
    assert second_calls == []
    assert lock_path.read_bytes() == lock_before
    assert in_flight_path.read_bytes() == in_flight_before
    assert list(tmp_path.glob("operator.lock.quarantine.*.json")) == []


def test_processed_restart_skips_provider_and_dispatcher_then_quarantines(tmp_path):
    client = FakeGitHub()

    def first_invoker(**_):
        client.target_comments.append(
            CommentRecord(id=20, body=result_comment(), author="HarryWhite-TW")
        )
        return DispatcherInvocationResult(returncode=0, stdout="ok", stderr="")

    first = run_b3b(
        tmp_path,
        client,
        dispatcher_invoker=first_invoker,
        operator_session_id=SESSION_A,
        process_identity=fake_process_identity(),
        lifecycle_fault_injector=inject_at("after_processed_durable"),
    )

    class ProviderMustNotRun:
        calls = 0

        def read_result_comments(self, request):
            self.calls += 1
            raise AssertionError("provider must not run for durable processed state")

    provider = ProviderMustNotRun()
    second_calls = []
    second = run_b3b(
        tmp_path,
        client,
        dispatcher_invoker=lambda **kwargs: second_calls.append(kwargs),
        durable_evidence_provider=provider,
        operator_session_id=SESSION_B,
        process_identity=fake_process_identity(
            pid=4102,
            token="windows-filetime:41020000",
        ),
        process_probe=lambda _: process_observation("dead"),
    )

    assert first["in_flight_stage"] == PROCESSED
    assert second["result"] == "success"
    assert second["processed_request_already_seen"] is True
    assert second["dispatcher_invoked"] is False
    assert second_calls == []
    assert provider.calls == 0
    assert not (tmp_path / "in_flight.json").exists()
    assert len(list(tmp_path.glob("operator.lock.quarantine.*.json"))) == 1


def test_complete_live_lock_is_never_removed_or_quarantined(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    lock_path = tmp_path / "operator.lock"
    payload = create_lock_payload(
        operator_session_id=SESSION_A,
        process_identity=fake_process_identity(),
        created_at=NOW,
        repository=DEFAULT_REPOSITORY,
        inbox_issue=DEFAULT_INBOX_ISSUE,
        mode=B3B_MODE,
    )
    write_exclusive_json(lock_path, payload)
    before = lock_path.read_bytes()
    calls = []

    summary = run_b3b(
        tmp_path,
        dispatcher_invoker=lambda **kwargs: calls.append(kwargs),
        operator_session_id=SESSION_B,
        process_identity=fake_process_identity(
            pid=4102,
            token="windows-filetime:41020000",
        ),
        process_probe=lambda _: process_observation("live"),
    )

    assert summary["blocked_reasons"] == ["active_lock_present"]
    assert summary["lock_process_status"] == "live"
    assert calls == []
    assert lock_path.read_bytes() == before
    assert list(tmp_path.glob("operator.lock.quarantine.*.json")) == []


def test_pid_reuse_without_in_flight_quarantines_exact_lock_and_uses_new_lock(
    tmp_path,
):
    tmp_path.mkdir(exist_ok=True)
    lock_path = tmp_path / "operator.lock"
    payload = create_lock_payload(
        operator_session_id=SESSION_A,
        process_identity=fake_process_identity(),
        created_at=NOW,
        repository=DEFAULT_REPOSITORY,
        inbox_issue=DEFAULT_INBOX_ISSUE,
        mode="b3a-dry-run",
    )
    write_exclusive_json(lock_path, payload)
    before = lock_path.read_bytes()

    summary = run_bridge_operator_b3_dry_run_loop(
        repo_root=ROOT_PATH,
        state_dir=tmp_path,
        github_client=FakeGitHub(inbox_comments=[]),
        local_checker=ready(tmp_path),
        now_utc=NOW,
        sleeper=lambda seconds: None,
        operator_session_id=SESSION_B,
        process_identity=fake_process_identity(
            pid=4102,
            token="windows-filetime:41020000",
        ),
        process_probe=lambda _: process_observation("pid_reused"),
    )

    quarantined = list(tmp_path.glob("operator.lock.quarantine.*.json"))
    assert summary["result"] == "success"
    assert summary["lock_quarantined"] is True
    assert not lock_path.exists()
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == before

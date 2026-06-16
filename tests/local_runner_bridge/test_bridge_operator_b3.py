import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from local_runner_bridge.bridge_operator_b1 import CommentRecord, IssueRecord, LocalReadiness
from local_runner_bridge.bridge_operator_b3 import (
    DEFAULT_INBOX_ISSUE,
    run_bridge_operator_b3_dry_run_loop,
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


def assert_safety(summary):
    assert summary["broad_issue_scan_performed"] is False
    assert summary["latest_next_inference_performed"] is False
    assert summary["dispatcher_invoked"] is False
    assert summary["dispatcher_invocation_count"] == 0
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

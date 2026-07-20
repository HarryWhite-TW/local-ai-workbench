import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from local_runner_bridge.bridge_operator_b1 import (  # noqa: E402
    DEFAULT_REPOSITORY,
    HAG_REPOSITORY,
    CommentRecord,
    IssueRecord,
    LocalReadiness,
    run_bridge_operator_b1_dry_run,
)
from local_runner_bridge.bridge_operator_b2 import (  # noqa: E402
    DispatcherInvocationResult,
    run_bridge_operator_b2_once,
)
from local_runner_bridge.bridge_operator_b3 import (  # noqa: E402
    PROCESSED_REQUEST_PROTOCOL,
    read_processed_request_records,
)

NOW = datetime(2026, 7, 20, 8, 0, 0, tzinfo=timezone.utc)
HEAD = "8d33250cbd299fb946158f8e1295bc3ab3140e30"
CONTROL_ROOT = r"C:\control\local-ai-workbench"
TARGET_ROOT = r"C:\targets\human-approval-automation-gateway"


def inbox_marker(repository=HAG_REPOSITORY, **overrides):
    fields = {
        "protocol": "lawb.bridge_inbox_request.v1",
        "request_id": "shared-request-id",
        "repo": repository,
        "target_issue": "218",
        "target_dispatch_request_id": "hag-dispatch-218",
        "branch": "wf-hag-xr-01-single-target-routing",
        "head": HEAD,
        "expires": "20260721T080000Z",
        "action": "run-reviewbundle",
        "requested_by": "chatgpt",
    }
    fields.update(overrides)
    return "BRIDGE-INBOX-REQUEST " + " ".join(f"{key}={value}" for key, value in fields.items())


def dispatch_marker(repository=HAG_REPOSITORY, **overrides):
    fields = {
        "protocol": "lawb.dispatch.v1",
        "action": "run-reviewbundle",
        "issue": "218",
        "repo": repository,
        "branch": "wf-hag-xr-01-single-target-routing",
        "head": HEAD,
        "expires": "20260721T080000Z",
        "requested_by": "chatgpt",
        "request_id": "hag-dispatch-218",
    }
    fields.update(overrides)
    return "CHATGPT-DISPATCH " + " ".join(f"{key}={value}" for key, value in fields.items())


def result_comment(repository=HAG_REPOSITORY):
    return "LAWBRUNNER-RESULT protocol=lawb.runner_result.v1\n" + json.dumps(
        {
            "schema": "lawb.runner_result.v1",
            "repo": repository,
            "issue": 218,
            "action": "run-reviewbundle",
            "result": "success",
            "branch": "wf-hag-xr-01-single-target-routing",
            "head": HEAD,
            "request_id": "hag-dispatch-218",
        }
    )


class ControlClient:
    def __init__(self, repository=HAG_REPOSITORY):
        self.repository = repository
        self.reads = []

    def get_issue(self, issue_number):
        self.reads.append(("issue", issue_number))
        assert issue_number == 147
        return IssueRecord(number=147, state="open", body="")

    def list_issue_comments(self, issue_number):
        self.reads.append(("comments", issue_number))
        assert issue_number == 147
        return [CommentRecord(id=1, body=inbox_marker(self.repository), author="HarryWhite-TW")]


class TargetClient:
    def __init__(self, *, include_result=False):
        self.include_result = include_result
        self.comment_reads = 0
        self.reads = []

    def get_issue(self, issue_number):
        self.reads.append(("issue", issue_number))
        assert issue_number == 218
        return IssueRecord(number=218, state="open", body="")

    def list_issue_comments(self, issue_number):
        self.reads.append(("comments", issue_number))
        assert issue_number == 218
        self.comment_reads += 1
        comments = [CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW")]
        if self.include_result and self.comment_reads >= 3:
            comments.append(CommentRecord(id=20, body=result_comment(), author="HarryWhite-TW"))
        return comments


def ready(**overrides):
    values = {
        "repo_root": str(Path(TARGET_ROOT).resolve()),
        "branch": "wf-hag-xr-01-single-target-routing",
        "head": HEAD,
        "clean": True,
        "gh_available": True,
        "gh_authenticated": True,
        "gh_read_available": True,
        "errors": (),
        "origin_repository": HAG_REPOSITORY,
        "git_root_matches": True,
        "staged_clean": True,
    }
    values.update(overrides)
    return LocalReadiness(**values)


def preflight_result():
    tool = {
        "selected_path": r"C:\Tools\gh.exe",
        "suffix": ".exe",
        "selection_source": "path",
        "version_probe": {"executed": True, "exit_code": 0, "ok": True, "safe_message": "ok"},
    }
    codex = {**tool, "selected_path": r"C:\Tools\codex.cmd", "suffix": ".cmd"}
    safety = {
        "pollonce_invoked": False,
        "dispatcher_action_executed": False,
        "github_issue_read_performed": False,
        "github_write_performed": False,
        "runner_work_invoked": False,
        "codex_task_executed": False,
    }
    payload = {
        "protocol": "lawb.rv2_03_tool_resolution_preflight.v1",
        "component": "dispatcher",
        "result": "success",
        "required_action": "run-reviewbundle",
        "blocked_reasons": [],
        "tools": {"dispatcher_gh": tool},
        "nested_runner": {
            "protocol": "lawb.rv2_03_tool_resolution_preflight.v1",
            "component": "runner",
            "result": "success",
            "required_action": "run-reviewbundle",
            "blocked_reasons": [],
            "tools": {"runner_gh": tool, "codex": codex},
            "nested_runner": None,
            "safety": safety,
        },
        "safety": safety,
    }
    return DispatcherInvocationResult(0, json.dumps(payload), "")


def test_hag_b1_keeps_fixed_control_inbox_and_reads_target_with_separate_client():
    control = ControlClient()
    target = TargetClient()

    summary = run_bridge_operator_b1_dry_run(
        inbox_issue=147,
        repo_root=TARGET_ROOT,
        repository=HAG_REPOSITORY,
        github_client=control,
        target_github_client=target,
        local_checker=lambda _: ready(),
        now_utc=NOW,
    )

    assert summary["result"] == "success"
    assert summary["control_repository"] == DEFAULT_REPOSITORY
    assert summary["target_repository"] == HAG_REPOSITORY
    assert control.reads == [("issue", 147), ("comments", 147)]
    assert target.reads == [("issue", 218), ("comments", 218)]


def test_unsupported_third_repository_fails_before_any_github_read():
    control = ControlClient(repository="someone/else")
    summary = run_bridge_operator_b1_dry_run(
        inbox_issue=147,
        repo_root=TARGET_ROOT,
        repository="someone/else",
        github_client=control,
        local_checker=lambda _: ready(),
        now_utc=NOW,
    )
    assert summary["blocked_reasons"] == ["unsupported_target_repository"]
    assert control.reads == []


def test_hag_wrong_path_origin_branch_head_dirty_and_staged_fail_closed():
    cases = (
        (ready(repo_root=str(Path(CONTROL_ROOT).resolve())), "wrong_repo_root"),
        (ready(git_root_matches=False), "target_not_git_repository_root"),
        (ready(origin_repository=DEFAULT_REPOSITORY), "wrong_target_origin"),
        (ready(branch="wrong"), "wrong_branch"),
        (ready(head="f" * 40), "wrong_head"),
        (ready(clean=False), "dirty_repository"),
        (ready(staged_clean=False), "staged_files_present"),
    )
    for readiness, reason in cases:
        summary = run_bridge_operator_b1_dry_run(
            inbox_issue=147,
            repo_root=TARGET_ROOT,
            repository=HAG_REPOSITORY,
            github_client=ControlClient(),
            target_github_client=TargetClient(),
            local_checker=lambda _, value=readiness: value,
            now_utc=NOW,
        )
        assert reason in summary["blocked_reasons"]
        assert summary["dispatcher_invoked"] is False


def test_hag_b2_uses_control_dispatcher_and_target_result_surface():
    control = ControlClient()
    target = TargetClient(include_result=True)
    calls = []

    def invoke(**kwargs):
        calls.append(kwargs)
        return DispatcherInvocationResult(0, "ok", "")

    summary = run_bridge_operator_b2_once(
        repo_root=TARGET_ROOT,
        control_repo_root=CONTROL_ROOT,
        repository=HAG_REPOSITORY,
        github_client=control,
        target_github_client=target,
        local_checker=lambda _: ready(),
        preflight_invoker=lambda **_: preflight_result(),
        dispatcher_invoker=invoke,
        now_utc=NOW,
    )

    assert summary["result"] == "success"
    assert summary["target_result_verified"] is True
    assert calls[0]["cwd"] == str(Path(CONTROL_ROOT).resolve())
    args = calls[0]["args"]
    assert str(Path(CONTROL_ROOT).resolve() / "scripts" / "local_dispatcher_v1.ps1") in args
    assert args[args.index("-Repo") + 1] == HAG_REPOSITORY
    assert args[args.index("-TargetRepoRoot") + 1] == str(Path(TARGET_ROOT).resolve())
    assert all(issue != 218 for _, issue in control.reads)
    assert ("comments", 218) in target.reads


def test_processed_identity_is_repository_scoped_and_legacy_is_local_only(tmp_path):
    path = tmp_path / "processed_requests.jsonl"
    base = {
        "protocol": PROCESSED_REQUEST_PROTOCOL,
        "request_id": "same-id",
        "target_issue": 218,
        "target_dispatch_request_id": "dispatch-218",
        "requested_action": "run-reviewbundle",
        "expected_branch": "branch",
        "expected_head": HEAD,
    }
    records = [
        base,
        {**base, "target_repository": HAG_REPOSITORY},
    ]
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")

    local_records = read_processed_request_records(path, repository=DEFAULT_REPOSITORY)
    hag_records = read_processed_request_records(path, repository=HAG_REPOSITORY)

    assert set(local_records) == {"same-id"}
    assert "target_repository" not in local_records["same-id"]
    assert hag_records["same-id"]["target_repository"] == HAG_REPOSITORY

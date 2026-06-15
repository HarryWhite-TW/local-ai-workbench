import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import local_runner_bridge.bridge_operator_b1 as b1
from local_runner_bridge.bridge_operator_b1 import (
    CommentRecord,
    GitHubApiClient,
    IssueRecord,
    LocalReadiness,
    _github_get_json_with_gh,
    _run_command,
    parse_bridge_inbox_request,
    parse_chatgpt_dispatch_marker,
    run_bridge_operator_b1_dry_run,
)


NOW = datetime(2026, 6, 15, 1, 0, 0, tzinfo=timezone.utc)
HEAD = "4c46cb02738c55f06884eff989598182a6070a92"
ROOT_PATH = r"C:\Users\admin\Desktop\local-ai-workbench"


def marker(**overrides):
    fields = {
        "protocol": "lawb.bridge_inbox_request.v1",
        "request_id": "b1-137-20260615T010000Z",
        "repo": "HarryWhite-TW/local-ai-workbench",
        "target_issue": "137",
        "target_dispatch_request_id": "b1-137-dispatch",
        "branch": "feature/bridge-operator-b1",
        "head": HEAD,
        "expires": "20260616T010000Z",
        "action": "run-reviewbundle",
        "requested_by": "chatgpt",
    }
    fields.update(overrides)
    return "BRIDGE-INBOX-REQUEST " + " ".join(
        f"{key}={value}" for key, value in fields.items()
    )


def dispatch_marker(**overrides):
    fields = {
        "protocol": "lawb.dispatch.v1",
        "action": "run-reviewbundle",
        "issue": "137",
        "repo": "HarryWhite-TW/local-ai-workbench",
        "branch": "feature/bridge-operator-b1",
        "head": HEAD,
        "expires": "20260616T010000Z",
        "requested_by": "chatgpt",
        "request_id": "b1-137-dispatch",
    }
    fields.update(overrides)
    return "CHATGPT-DISPATCH " + " ".join(
        f"{key}={value}" for key, value in fields.items()
    )


class FakeGitHub:
    def __init__(
        self,
        *,
        inbox_body="",
        comments=None,
        target_comments=None,
        target_state="open",
        fail_target=False,
    ):
        self.inbox_body = inbox_body
        self.comments = comments if comments is not None else [
            CommentRecord(id=1, body=marker(), author="HarryWhite-TW")
        ]
        self.target_comments = target_comments if target_comments is not None else [
            CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW")
        ]
        self.target_state = target_state
        self.fail_target = fail_target
        self.issues_read = []
        self.comments_read = []

    def get_issue(self, issue_number):
        self.issues_read.append(issue_number)
        if self.fail_target and issue_number == 137:
            raise RuntimeError("missing")
        if issue_number == 999:
            return IssueRecord(number=999, state="open", body=self.inbox_body)
        return IssueRecord(number=issue_number, state=self.target_state, body="")

    def list_issue_comments(self, issue_number):
        self.comments_read.append(issue_number)
        if issue_number == 137:
            return self.target_comments
        return self.comments


def ready(**overrides):
    values = {
        "repo_root": str(Path(ROOT_PATH).resolve()),
        "branch": "feature/bridge-operator-b1",
        "head": HEAD,
        "clean": True,
        "gh_available": True,
        "gh_authenticated": True,
        "gh_read_available": True,
        "errors": (),
    }
    values.update(overrides)
    return LocalReadiness(**values)


def run(client, readiness=None, **kwargs):
    return run_bridge_operator_b1_dry_run(
        inbox_issue=999,
        repo_root=ROOT_PATH,
        github_client=client,
        local_checker=lambda root: readiness or ready(),
        now_utc=NOW,
        **kwargs,
    )


def assert_no_side_effects(summary):
    assert summary["broad_issue_scan_performed"] is False
    assert summary["latest_next_inference_performed"] is False
    assert summary["dispatcher_invoked"] is False
    assert summary["runner_invoked"] is False
    assert summary["codex_invoked"] is False
    assert summary["github_write_performed"] is False
    assert summary["commit_performed"] is False
    assert summary["push_performed"] is False
    assert summary["issue_closed"] is False
    assert summary["label_changed"] is False
    assert summary["pr_created"] is False
    assert summary["merge_performed"] is False
    assert summary["approval_consumed"] is False


def test_parse_valid_marker():
    parsed = parse_bridge_inbox_request(marker())

    assert parsed["result"] == "success"
    assert parsed["fields"]["target_issue"] == 137
    assert parsed["fields"]["requested_by"] == "chatgpt"


def test_positive_dry_run_reads_fixed_inbox_and_explicit_target_only():
    client = FakeGitHub()

    summary = run(client)

    assert summary["result"] == "success"
    assert summary["dry_run_result"] == "ready_without_delegation"
    assert summary["request_id"] == "b1-137-20260615T010000Z"
    assert summary["target_issue"] == 137
    assert client.issues_read == [999, 137]
    assert client.comments_read == [999, 137]
    assert summary["target_dispatch_comment_id"] == 10
    assert summary["validations"]["local_readiness"] == "passed"
    assert_no_side_effects(summary)


def test_missing_request_fails_closed():
    summary = run(FakeGitHub(comments=[]))

    assert summary["result"] == "blocked"
    assert summary["blocked_reasons"] == ["missing_request"]
    assert summary["target_issue_read_performed"] is False
    assert_no_side_effects(summary)


def test_duplicate_current_marker_ambiguity_fails_closed():
    comments = [
        CommentRecord(id=1, body=marker(request_id="one"), author="HarryWhite-TW"),
        CommentRecord(id=2, body=marker(request_id="two"), author="HarryWhite-TW"),
    ]

    summary = run(FakeGitHub(comments=comments))

    assert summary["result"] == "blocked"
    assert summary["blocked_reasons"] == ["multiple_current_requests"]
    assert_no_side_effects(summary)


def test_expired_valid_marker_plus_current_marker_succeeds():
    comments = [
        CommentRecord(
            id=1,
            body=marker(request_id="old-137", expires="20260614T010000Z"),
            author="HarryWhite-TW",
        ),
        CommentRecord(id=2, body=marker(), author="HarryWhite-TW"),
    ]

    summary = run(FakeGitHub(comments=comments))

    assert summary["result"] == "success"
    assert summary["expired_historical_request_count"] == 1
    assert summary["inbox_comment_id"] == 2
    assert_no_side_effects(summary)


def test_expired_wrong_repo_fails_closed_before_ignore():
    comments = [
        CommentRecord(
            id=1,
            body=marker(request_id="old-137", repo="other/repo", expires="20260614T010000Z"),
            author="HarryWhite-TW",
        ),
        CommentRecord(id=2, body=marker(), author="HarryWhite-TW"),
    ]

    summary = run(FakeGitHub(comments=comments))

    assert summary["result"] == "blocked"
    assert "wrong_repository" in summary["blocked_reasons"]
    assert summary["target_issue_read_performed"] is False
    assert_no_side_effects(summary)


def test_expired_unsupported_action_fails_closed_before_ignore():
    comments = [
        CommentRecord(
            id=1,
            body=marker(request_id="old-137", action="commit", expires="20260614T010000Z"),
            author="HarryWhite-TW",
        ),
        CommentRecord(id=2, body=marker(), author="HarryWhite-TW"),
    ]

    summary = run(FakeGitHub(comments=comments))

    assert summary["result"] == "blocked"
    assert "unsupported_action" in summary["blocked_reasons"]
    assert summary["target_issue_read_performed"] is False
    assert_no_side_effects(summary)


def test_expired_requested_by_mismatch_fails_closed_before_ignore():
    comments = [
        CommentRecord(
            id=1,
            body=marker(request_id="old-137", requested_by="codex", expires="20260614T010000Z"),
            author="HarryWhite-TW",
        ),
        CommentRecord(id=2, body=marker(), author="HarryWhite-TW"),
    ]

    summary = run(FakeGitHub(comments=comments))

    assert summary["result"] == "blocked"
    assert "requested_by_mismatch" in summary["blocked_reasons"]
    assert summary["target_issue_read_performed"] is False
    assert_no_side_effects(summary)


def test_duplicate_fields_fail_closed():
    duplicated = marker() + " request_id=second"

    summary = run(FakeGitHub(comments=[CommentRecord(id=1, body=duplicated, author="HarryWhite-TW")]))

    assert summary["result"] == "blocked"
    assert "malformed_marker" in summary["blocked_reasons"]
    assert summary["parse_errors"] == ["duplicate_fields"]
    assert_no_side_effects(summary)


def test_issue_body_markers_are_not_authorized():
    summary = run(FakeGitHub(inbox_body=marker(), comments=[]))

    assert summary["result"] == "blocked"
    assert summary["blocked_reasons"] == ["missing_request"]
    assert_no_side_effects(summary)


def test_multiline_marker_is_malformed_and_fails_closed():
    comments = [
        CommentRecord(id=1, body=marker() + "\nextra", author="HarryWhite-TW")
    ]

    summary = run(FakeGitHub(comments=comments))

    assert summary["result"] == "blocked"
    assert "malformed_marker" in summary["blocked_reasons"]
    assert_no_side_effects(summary)


def test_untrusted_author_fails_closed_before_target_read():
    comments = [CommentRecord(id=1, body=marker(), author="other-user")]

    summary = run(FakeGitHub(comments=comments))

    assert summary["result"] == "blocked"
    assert summary["blocked_reasons"] == ["untrusted_inbox_author"]
    assert summary["target_issue_read_performed"] is False
    assert_no_side_effects(summary)


def test_wrong_repository_fails_closed():
    summary = run(FakeGitHub(comments=[CommentRecord(id=1, body=marker(repo="other/repo"), author="HarryWhite-TW")]))

    assert summary["result"] == "blocked"
    assert "wrong_repository" in summary["blocked_reasons"]
    assert_no_side_effects(summary)


def test_target_issue_missing_or_closed_fail_closed():
    missing = run(FakeGitHub(fail_target=True))
    closed = run(FakeGitHub(target_state="closed"))

    assert missing["result"] == "blocked"
    assert "target_issue_missing" in missing["blocked_reasons"]
    assert closed["result"] == "blocked"
    assert "target_issue_closed" in closed["blocked_reasons"]
    assert_no_side_effects(missing)
    assert_no_side_effects(closed)


def test_expired_request_fails_closed():
    comments = [
        CommentRecord(id=1, body=marker(expires="20260614T010000Z"), author="HarryWhite-TW")
    ]

    summary = run(FakeGitHub(comments=comments))

    assert summary["result"] == "blocked"
    assert "missing_current_request" in summary["blocked_reasons"]
    assert_no_side_effects(summary)


def test_wrong_branch_head_dirty_repo_and_missing_gh_fail_closed():
    cases = [
        (ready(branch="main"), "wrong_branch"),
        (ready(head="0" * 40), "wrong_head"),
        (ready(clean=False), "dirty_repository"),
        (ready(gh_available=False), "missing_github_cli"),
        (ready(gh_authenticated=False), "github_read_unavailable"),
        (ready(gh_read_available=False), "github_read_unavailable"),
    ]

    for readiness, reason in cases:
        summary = run(FakeGitHub(), readiness)
        assert summary["result"] == "blocked"
        assert reason in summary["blocked_reasons"]
        assert_no_side_effects(summary)


def test_unsupported_action_and_requested_by_mismatch_fail_closed():
    unsupported = run(
        FakeGitHub(
            comments=[
                CommentRecord(id=1, body=marker(action="commit"), author="HarryWhite-TW")
            ]
        )
    )
    mismatch = run(
        FakeGitHub(
            comments=[
                CommentRecord(id=1, body=marker(requested_by="codex"), author="HarryWhite-TW")
            ]
        )
    )

    assert "unsupported_action" in unsupported["blocked_reasons"]
    assert "requested_by_mismatch" in mismatch["blocked_reasons"]
    assert_no_side_effects(unsupported)
    assert_no_side_effects(mismatch)


def test_unsupported_configured_repository_does_not_read_github():
    client = FakeGitHub()

    summary = run(client, repository="other/repo")

    assert summary["result"] == "blocked"
    assert summary["blocked_reasons"] == ["unsupported_repository"]
    assert client.issues_read == []
    assert client.comments_read == []
    assert_no_side_effects(summary)


def test_target_dispatch_request_identity_must_match_exactly_once():
    matching = run(FakeGitHub())
    missing = run(
        FakeGitHub(
            target_comments=[
                CommentRecord(
                    id=10,
                    body=dispatch_marker(request_id="other-dispatch"),
                    author="HarryWhite-TW",
                )
            ]
        )
    )
    ambiguous = run(
        FakeGitHub(
            target_comments=[
                CommentRecord(id=10, body=dispatch_marker(), author="HarryWhite-TW"),
                CommentRecord(id=11, body=dispatch_marker(), author="HarryWhite-TW"),
            ]
        )
    )

    assert matching["result"] == "success"
    assert missing["result"] == "blocked"
    assert "target_dispatch_request_not_found" in missing["blocked_reasons"]
    assert ambiguous["result"] == "blocked"
    assert "ambiguous_target_dispatch_request" in ambiguous["blocked_reasons"]
    assert_no_side_effects(matching)
    assert_no_side_effects(missing)
    assert_no_side_effects(ambiguous)


def test_target_dispatch_malformed_and_untrusted_fail_closed():
    malformed = run(
        FakeGitHub(
            target_comments=[
                CommentRecord(id=10, body=dispatch_marker() + "\nextra", author="HarryWhite-TW")
            ]
        )
    )
    untrusted = run(
        FakeGitHub(
            target_comments=[
                CommentRecord(id=10, body=dispatch_marker(), author="other-user")
            ]
        )
    )

    assert "malformed_target_dispatch_marker" in malformed["blocked_reasons"]
    assert "untrusted_target_dispatch_author" in untrusted["blocked_reasons"]
    assert_no_side_effects(malformed)
    assert_no_side_effects(untrusted)


def test_target_dispatch_marker_accepts_reason_optional_field():
    parsed = parse_chatgpt_dispatch_marker(dispatch_marker(reason="chatgpt-review"))

    assert parsed["result"] == "success"
    assert parsed["fields"]["request_id"] == "b1-137-dispatch"
    assert parsed["fields"]["reason"] == "chatgpt-review"


def test_target_dispatch_marker_accepts_mode_and_expected_state_optional_fields():
    parsed = parse_chatgpt_dispatch_marker(
        dispatch_marker(mode="foreground", expected_state="open")
    )

    assert parsed["result"] == "success"
    assert parsed["fields"]["mode"] == "foreground"
    assert parsed["fields"]["expected_state"] == "open"


def test_target_dispatch_marker_rejects_unknown_optional_field():
    parsed = parse_chatgpt_dispatch_marker(dispatch_marker(priority="high"))

    assert parsed["result"] == "blocked"
    assert parsed["errors"] == ["unexpected_fields"]
    assert parsed["extras"] == ["priority"]


def test_target_dispatch_marker_rejects_duplicate_optional_field():
    parsed = parse_chatgpt_dispatch_marker(dispatch_marker(reason="one") + " reason=two")

    assert parsed["result"] == "blocked"
    assert parsed["errors"] == ["duplicate_fields"]


def test_github_client_uses_authenticated_paginated_gh_read_path():
    calls = []

    def fake_get_json(args, token, paginate):
        calls.append((args, token, paginate))
        if "comments" in args[0]:
            return [
                [
                    {
                        "id": 1,
                        "body": "one",
                        "user": {"login": "HarryWhite-TW"},
                    }
                ],
                [
                    {
                        "id": 2,
                        "body": "two",
                        "user": {"login": "HarryWhite-TW"},
                    }
                ],
            ]
        return {"number": 137, "state": "open", "body": ""}

    client = GitHubApiClient(
        "HarryWhite-TW/local-ai-workbench",
        token="secret-token",
        get_json=fake_get_json,
    )

    issue = client.get_issue(137)
    comments = client.list_issue_comments(137)

    assert issue.number == 137
    assert [comment.id for comment in comments] == [1, 2]
    assert calls == [
        (["repos/HarryWhite-TW/local-ai-workbench/issues/137"], "secret-token", False),
        (
            [
                "repos/HarryWhite-TW/local-ai-workbench/issues/137/comments",
                "--method",
                "GET",
                "--paginate",
                "--slurp",
                "-f",
                "per_page=100",
            ],
            "secret-token",
            True,
        ),
    ]


def test_github_client_comments_read_with_per_page_injects_get_without_write_endpoint():
    calls = []

    def fake_get_json(args, token, paginate):
        calls.append((args, token, paginate))
        return []

    client = GitHubApiClient(
        "HarryWhite-TW/local-ai-workbench",
        get_json=fake_get_json,
    )

    comments = client.list_issue_comments(137)

    assert comments == []
    assert calls == [
        (
            [
                "repos/HarryWhite-TW/local-ai-workbench/issues/137/comments",
                "--method",
                "GET",
                "--paginate",
                "--slurp",
                "-f",
                "per_page=100",
            ],
            None,
            True,
        )
    ]
    args = calls[0][0]
    assert args.count("repos/HarryWhite-TW/local-ai-workbench/issues/137/comments") == 1
    assert "--method" in args
    assert args[args.index("--method") + 1] == "GET"
    assert "POST" not in args
    assert "PATCH" not in args
    assert "DELETE" not in args
    assert not any(arg.endswith("/comments/1") for arg in args)


def test_run_command_uses_explicit_utf8_replacement_decoding(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(b1.subprocess, "run", fake_run)

    result = _run_command(["git", "status", "--porcelain"], cwd=ROOT_PATH)

    assert result.returncode == 0
    assert calls == [
        (
            ["git", "status", "--porcelain"],
            {
                "cwd": ROOT_PATH,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
                "capture_output": True,
                "check": False,
                "timeout": 20,
            },
        )
    ]


def test_github_get_json_with_gh_uses_explicit_utf8_replacement_decoding(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout='{"ok": true}', stderr="")

    monkeypatch.setattr(b1, "_resolve_gh_path", lambda: "gh.exe")
    monkeypatch.setattr(b1.subprocess, "run", fake_run)

    payload = _github_get_json_with_gh(["repos/example/repo/issues/1"], "token", False)

    assert payload == {"ok": True}
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command == ["gh.exe", "api", "repos/example/repo/issues/1"]
    assert kwargs["text"] is True
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["errors"] == "replace"
    assert kwargs["capture_output"] is True
    assert kwargs["check"] is False
    assert kwargs["timeout"] == 30
    assert kwargs["env"]["GH_TOKEN"] == "token"


def test_run_command_decodes_utf8_output_not_representable_in_cp950():
    result = _run_command(
        [
            sys.executable,
            "-c",
            "import sys; sys.stdout.buffer.write(b'utf8: \\xf0\\x9f\\x9a\\x80')",
        ],
        cwd=str(ROOT),
    )

    assert result.returncode == 0
    assert result.stdout == "utf8: \U0001f680"

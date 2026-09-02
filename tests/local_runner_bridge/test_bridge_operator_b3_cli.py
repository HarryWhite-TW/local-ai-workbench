import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import local_runner_bridge.bridge_operator_b3_cli as cli


def read_json(capsys):
    output = capsys.readouterr().out
    assert output.count("{") == 1
    return json.loads(output)


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
    assert summary["pr_created"] is False


def test_cli_requires_arguments_and_prints_blocked_json(capsys):
    result = cli.main([])
    summary = read_json(capsys)

    assert result == 2
    assert summary["result"] == "blocked"
    assert summary["blocked_reasons"] == ["invalid_arguments"]
    assert_safety(summary)


def test_cli_routes_fixed_inbox_to_b3_without_printing_credentials(monkeypatch, capsys):
    calls = []

    class FakeClient:
        def __init__(self, repo, token=None):
            calls.append(("client", repo, token))

    def fake_run(**kwargs):
        calls.append(
            (
                "run",
                kwargs["inbox_issue"],
                kwargs["repository"],
                str(kwargs["repo_root"]),
                kwargs["max_cycles"],
                kwargs["poll_interval_seconds"],
                kwargs["state_dir"],
                kwargs["mode"],
                kwargs["timeout_seconds"],
                kwargs["operator_session_id"],
            )
        )
        return {
            "protocol": "lawb.bridge_operator_b3_dry_run_loop_summary.v1",
            "result": "success",
            "configured_inbox_issue": 147,
            "broad_issue_scan_performed": False,
            "latest_next_inference_performed": False,
            "dispatcher_invoked": False,
            "dispatcher_invocation_count": 0,
            "dispatcher_result_writeback_reached": False,
            "dispatcher_result_writeback_verified": False,
            "runner_invoked": False,
            "codex_invoked": False,
            "github_write_performed": False,
            "background_service_started": False,
            "commit_performed": False,
            "push_performed": False,
            "issue_closed": False,
            "label_changed": False,
            "pr_created": False,
            "merge_performed": False,
            "branch_deleted": False,
            "approval_consumed": False,
        }

    monkeypatch.setattr(cli, "GitHubApiClient", FakeClient)
    monkeypatch.setattr(cli, "run_bridge_operator_b3_dry_run_loop", fake_run)
    monkeypatch.setenv("B3_TOKEN", "ghp_TEST_SECRET_DO_NOT_LEAK")

    result = cli.main(
        [
            "--repo-root",
            "C:/repo",
            "--max-cycles",
            "2",
            "--poll-interval-seconds",
            "0.5",
            "--state-dir",
            "C:/state",
            "--github-token-env",
            "B3_TOKEN",
            "--mode",
            "b3b-maybe-status-check",
            "--timeout-seconds",
            "45",
            "--operator-session-id",
            "a" * 32,
        ]
    )
    output = capsys.readouterr().out
    summary = json.loads(output)

    assert result == 0
    assert calls == [
        ("client", "HarryWhite-TW/local-ai-workbench", "ghp_TEST_SECRET_DO_NOT_LEAK"),
        (
            "run",
                279,
            "HarryWhite-TW/local-ai-workbench",
            "C:\\repo",
            2,
            0.5,
            "C:/state",
            "b3b-maybe-status-check",
            45,
            "a" * 32,
        ),
    ]
    assert "ghp_TEST_SECRET_DO_NOT_LEAK" not in output
    assert summary["result"] == "success"
    assert_safety(summary)


def test_status_progress_reporter_writes_request_accepted_status(monkeypatch, tmp_path):
    gh = tmp_path / "gh.exe"
    gh.write_text("placeholder", encoding="utf-8")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return type("Completed", (), {"returncode": 0, "stdout": '{"id":45123}'})()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    args = cli._parser().parse_args(
        [
            "--repo-root", "C:/repo",
            "--max-cycles", "1",
            "--poll-interval-seconds", "0",
            "--mode", "b3c-run-reviewbundle",
            "--operator-session-id", "a" * 32,
            "--status-comment-id", "45123",
            "--status-gh-path", str(gh),
        ]
    )

    reporter = cli._status_progress_reporter(args)
    reporter(
        {
            "request_id": "status-request-001",
            "issue_number": 188,
            "requested_action": "run-reviewbundle",
            "lifecycle": {
                "stage": "REQUEST_ACCEPTED",
                "certainty": "verified",
                "basis": "current_request_identity",
            },
            "dispatcher_invoked": False,
        }
    )

    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[-2:] == ["--input", "-"]
    assert command[-3].endswith("issues/comments/45123")
    body = json.loads(kwargs["input"])["body"]
    payload = json.loads(body.split("```json\n", 1)[1].rsplit("\n```", 1)[0])
    assert payload["result"] == "running"
    assert payload["request_id"] == "status-request-001"
    assert payload["current_run"]["lifecycle"]["stage"] == "REQUEST_ACCEPTED"
    assert "狀態：執行中" in body
    assert "目前階段：任務已接受" in body
    assert "Codex 執行中" not in body
    assert "%" not in body
    assert "ETA" not in body


@pytest.mark.parametrize(
    ("terminal_result", "expected_result", "expected_next_action"),
    [
        ("success", "waiting_review", "chatgpt_final_review"),
        ("failure", "blocked", "review_blocked_result"),
        ("blocked", "blocked", "review_blocked_result"),
    ],
)
def test_status_progress_reporter_writes_verified_terminal_status(
    monkeypatch, tmp_path, terminal_result, expected_result, expected_next_action
):
    gh = tmp_path / "gh.exe"
    gh.write_text("placeholder", encoding="utf-8")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return type("Completed", (), {"returncode": 0, "stdout": '{"id":45123}'})()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    args = cli._parser().parse_args(
        [
            "--repo-root", "C:/repo",
            "--max-cycles", "1",
            "--poll-interval-seconds", "0",
            "--mode", "b3c-run-reviewbundle",
            "--operator-session-id", "a" * 32,
            "--status-comment-id", "45123",
            "--status-gh-path", str(gh),
        ]
    )

    reporter = cli._status_progress_reporter(args)
    reporter(
        {
            "request_id": "status-request-001",
            "issue_number": 188,
            "requested_action": "run-reviewbundle",
            "terminal_result": terminal_result,
            "lifecycle": {
                "stage": "TERMINAL_RESULT_READY",
                "certainty": "verified",
                "basis": "trusted_terminal_result",
            },
        }
    )

    assert len(calls) == 1
    body = json.loads(calls[0][1]["input"])["body"]
    payload = json.loads(body.split("```json\n", 1)[1].rsplit("\n```", 1)[0])
    assert payload["result"] == expected_result
    assert payload["next_action"] == expected_next_action
    if terminal_result == "success":
        assert "狀態：等待 ChatGPT 審核" in body
        assert "狀態：已完成" not in body
    else:
        assert "狀態：已阻塞" in body
        assert "下一步：由 ChatGPT 判讀結果" in body


def test_status_progress_reporter_keeps_uncertain_runner_or_codex_reach_explicit(
    monkeypatch, tmp_path
):
    gh = tmp_path / "gh.exe"
    gh.write_text("placeholder", encoding="utf-8")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return type("Completed", (), {"returncode": 0, "stdout": '{"id":45123}'})()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    args = cli._parser().parse_args(
        [
            "--repo-root", "C:/repo", "--max-cycles", "1",
            "--poll-interval-seconds", "0", "--status-comment-id", "45123",
            "--status-gh-path", str(gh),
        ]
    )
    reporter = cli._status_progress_reporter(args)
    reporter(
        {
            "request_id": "status-request-001", "issue_number": 188,
            "requested_action": "run-reviewbundle", "dispatcher_invoked": True,
            "lifecycle": {"stage": "RUNNER_OR_CODEX_REACH_UNCERTAIN"},
        }
    )

    body = json.loads(calls[0][1]["input"])["body"]
    assert "Runner／Codex 是否已到達尚未確認" in body
    assert "Codex 執行中" not in body


def test_status_progress_reporter_rejects_unverified_terminal_result(tmp_path):
    gh = tmp_path / "gh.exe"
    gh.write_text("placeholder", encoding="utf-8")
    args = cli._parser().parse_args(
        [
            "--repo-root", "C:/repo",
            "--max-cycles", "1",
            "--poll-interval-seconds", "0",
            "--status-comment-id", "45123",
            "--status-gh-path", str(gh),
        ]
    )

    reporter = cli._status_progress_reporter(args)
    with pytest.raises(ValueError, match="status_progress_terminal_result_invalid"):
        reporter(
            {
                "request_id": "status-request-001",
                "issue_number": 188,
                "requested_action": "run-reviewbundle",
                "terminal_result": None,
                "lifecycle": {"stage": "TERMINAL_RESULT_READY"},
            }
        )


@pytest.mark.parametrize("requested_action", ["maybe-status-check", "read-final-audit"])
def test_status_progress_reporter_does_not_publish_other_actions(
    tmp_path, requested_action
):
    gh = tmp_path / "gh.exe"
    gh.write_text("placeholder", encoding="utf-8")
    args = cli._parser().parse_args(
        [
            "--repo-root", "C:/repo",
            "--max-cycles", "1",
            "--poll-interval-seconds", "0",
            "--status-comment-id", "45123",
            "--status-gh-path", str(gh),
        ]
    )

    reporter = cli._status_progress_reporter(args)
    with pytest.raises(ValueError, match="status_progress_request_identity_invalid"):
        reporter(
            {
                "request_id": "status-request-001",
                "issue_number": 188,
                "requested_action": requested_action,
                "terminal_result": "success",
                "lifecycle": {"stage": "TERMINAL_RESULT_READY"},
            }
        )


def test_cli_accepts_b3c_run_reviewbundle_mode(monkeypatch, capsys):
    calls = []

    class FakeClient:
        def __init__(self, repo, token=None):
            calls.append(("client", repo, token))

    def fake_run(**kwargs):
        calls.append(("run", kwargs["mode"], kwargs["inbox_issue"]))
        return {
            "protocol": "lawb.bridge_operator_b3_dry_run_loop_summary.v1",
            "result": "success",
            "configured_inbox_issue": 147,
            "broad_issue_scan_performed": False,
            "latest_next_inference_performed": False,
            "dispatcher_invoked": False,
            "dispatcher_invocation_count": 0,
            "dispatcher_result_writeback_reached": False,
            "dispatcher_result_writeback_verified": False,
            "runner_invoked": False,
            "codex_invoked": False,
            "github_write_performed": False,
            "background_service_started": False,
            "commit_performed": False,
            "push_performed": False,
            "issue_closed": False,
            "label_changed": False,
            "pr_created": False,
            "merge_performed": False,
            "branch_deleted": False,
            "approval_consumed": False,
        }

    monkeypatch.setattr(cli, "GitHubApiClient", FakeClient)
    monkeypatch.setattr(cli, "run_bridge_operator_b3_dry_run_loop", fake_run)

    result = cli.main(
        [
            "--repo-root",
            "C:/repo",
            "--max-cycles",
            "1",
            "--poll-interval-seconds",
            "0",
            "--mode",
            "b3c-run-reviewbundle",
        ]
    )
    summary = read_json(capsys)

    assert result == 0
    assert calls == [
        ("client", "HarryWhite-TW/local-ai-workbench", None),
            ("run", "b3c-run-reviewbundle", 279),
    ]
    assert_safety(summary)


def test_cli_returns_one_for_blocked_summary(monkeypatch, capsys):
    class FakeClient:
        def __init__(self, repo, token=None):
            pass

    def fake_run(**kwargs):
        return {
            "protocol": "lawb.bridge_operator_b3_dry_run_loop_summary.v1",
            "result": "blocked",
            "blocked_reasons": ["active_lock_present"],
            "configured_inbox_issue": 147,
            "broad_issue_scan_performed": False,
            "latest_next_inference_performed": False,
            "dispatcher_invoked": False,
            "dispatcher_invocation_count": 0,
            "dispatcher_result_writeback_reached": False,
            "dispatcher_result_writeback_verified": False,
            "runner_invoked": False,
            "codex_invoked": False,
            "github_write_performed": False,
            "background_service_started": False,
            "commit_performed": False,
            "push_performed": False,
            "pr_created": False,
        }

    monkeypatch.setattr(cli, "GitHubApiClient", FakeClient)
    monkeypatch.setattr(cli, "run_bridge_operator_b3_dry_run_loop", fake_run)

    result = cli.main(
        ["--repo-root", "C:/repo", "--max-cycles", "1", "--poll-interval-seconds", "0"]
    )
    summary = read_json(capsys)

    assert result == 1
    assert summary["result"] == "blocked"
    assert_safety(summary)


def test_cli_requires_explicit_target_root_for_hag(capsys):
    result = cli.main(
        [
            "--repo-root",
            "C:/control",
            "--repo",
            "HarryWhite-TW/human-approval-automation-gateway",
            "--max-cycles",
            "1",
            "--poll-interval-seconds",
            "0",
        ]
    )
    summary = read_json(capsys)

    assert result == 2
    assert summary["blocked_reasons"] == ["target_repo_root_required"]


def test_cli_propagates_separate_hag_target_root(monkeypatch, capsys):
    calls = []

    class FakeClient:
        def __init__(self, repo, token=None):
            calls.append(("client", repo))

    def fake_run(**kwargs):
        calls.append(
            (
                "run",
                str(kwargs["control_repo_root"]),
                str(kwargs["repo_root"]),
                kwargs["repository"],
                kwargs["github_client"] is not kwargs["target_github_client"],
            )
        )
        return {"result": "success"}

    monkeypatch.setattr(cli, "GitHubApiClient", FakeClient)
    monkeypatch.setattr(cli, "run_bridge_operator_b3_dry_run_loop", fake_run)
    result = cli.main(
        [
            "--repo-root",
            "C:/control",
            "--target-repo-root",
            "C:/hag",
            "--repo",
            "HarryWhite-TW/human-approval-automation-gateway",
            "--max-cycles",
            "1",
            "--poll-interval-seconds",
            "0",
        ]
    )
    capsys.readouterr()

    assert result == 0
    assert calls == [
        ("client", "HarryWhite-TW/local-ai-workbench"),
        ("client", "HarryWhite-TW/human-approval-automation-gateway"),
        (
            "run",
            "C:\\control",
            "C:\\hag",
            "HarryWhite-TW/human-approval-automation-gateway",
            True,
        ),
    ]


def test_cli_propagates_separate_lawb_target_root(monkeypatch, capsys):
    calls = []

    class FakeClient:
        def __init__(self, repo, token=None):
            calls.append(("client", repo))

    def fake_run(**kwargs):
        calls.append(
            (
                "run",
                str(kwargs["control_repo_root"]),
                str(kwargs["repo_root"]),
                kwargs["repository"],
                kwargs["github_client"] is kwargs["target_github_client"],
            )
        )
        return {"result": "success"}

    monkeypatch.setattr(cli, "GitHubApiClient", FakeClient)
    monkeypatch.setattr(cli, "run_bridge_operator_b3_dry_run_loop", fake_run)
    result = cli.main(
        [
            "--repo-root",
            "C:/control",
            "--target-repo-root",
            "C:/engineering",
            "--repo",
            "HarryWhite-TW/local-ai-workbench",
            "--max-cycles",
            "1",
            "--poll-interval-seconds",
            "0",
        ]
    )
    capsys.readouterr()

    assert result == 0
    assert calls == [
        ("client", "HarryWhite-TW/local-ai-workbench"),
        (
            "run",
            "C:\\control",
            "C:\\engineering",
            "HarryWhite-TW/local-ai-workbench",
            True,
        ),
    ]


def test_cli_help_preserves_argparse_behavior(capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(["--help"])

    output = capsys.readouterr().out
    assert error.value.code == 0
    assert "usage:" in output
    assert "blocked_reasons" not in output

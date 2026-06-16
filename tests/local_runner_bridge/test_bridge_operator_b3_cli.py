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
        ]
    )
    output = capsys.readouterr().out
    summary = json.loads(output)

    assert result == 0
    assert calls == [
        ("client", "HarryWhite-TW/local-ai-workbench", "ghp_TEST_SECRET_DO_NOT_LEAK"),
        ("run", 147, "HarryWhite-TW/local-ai-workbench", "C:\\repo", 2, 0.5, "C:/state"),
    ]
    assert "ghp_TEST_SECRET_DO_NOT_LEAK" not in output
    assert summary["result"] == "success"
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


def test_cli_help_preserves_argparse_behavior(capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(["--help"])

    output = capsys.readouterr().out
    assert error.value.code == 0
    assert "usage:" in output
    assert "blocked_reasons" not in output

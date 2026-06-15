import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import local_runner_bridge.bridge_operator_b1_cli as cli


def read_json(capsys):
    output = capsys.readouterr().out
    assert output.count("{") == 1
    return json.loads(output)


def assert_no_side_effects(summary):
    assert summary["broad_issue_scan_performed"] is False
    assert summary["latest_next_inference_performed"] is False
    assert summary["dispatcher_invoked"] is False
    assert summary["runner_invoked"] is False
    assert summary["codex_invoked"] is False
    assert summary["github_write_performed"] is False
    assert summary["commit_performed"] is False
    assert summary["push_performed"] is False


def test_cli_requires_inbox_issue_and_prints_blocked_json(capsys):
    result = cli.main([])
    summary = read_json(capsys)

    assert result == 2
    assert summary["result"] == "blocked"
    assert summary["blocked_reasons"] == ["invalid_arguments"]
    assert_no_side_effects(summary)


def test_cli_routes_single_configured_inbox_to_dry_run(monkeypatch, capsys):
    calls = []

    class FakeClient:
        def __init__(self, repo, token=None):
            calls.append(("client", repo, token))

    def fake_run(**kwargs):
        calls.append(("run", kwargs["inbox_issue"], kwargs["repository"], kwargs["repo_root"]))
        return {
            "protocol": "lawb.bridge_operator_b1_dry_run_summary.v1",
            "result": "success",
            "broad_issue_scan_performed": False,
            "latest_next_inference_performed": False,
            "dispatcher_invoked": False,
            "runner_invoked": False,
            "codex_invoked": False,
            "github_write_performed": False,
            "commit_performed": False,
            "push_performed": False,
        }

    monkeypatch.setattr(cli, "GitHubApiClient", FakeClient)
    monkeypatch.setattr(cli, "run_bridge_operator_b1_dry_run", fake_run)
    monkeypatch.setenv("B1_TOKEN", "ghp_TEST_SECRET_DO_NOT_LEAK")

    result = cli.main(
        [
            "--inbox-issue",
            "999",
            "--repo-root",
            "C:/repo",
            "--github-token-env",
            "B1_TOKEN",
        ]
    )
    output = capsys.readouterr().out
    summary = json.loads(output)

    assert result == 0
    assert calls == [
        ("client", "HarryWhite-TW/local-ai-workbench", "ghp_TEST_SECRET_DO_NOT_LEAK"),
        ("run", 999, "HarryWhite-TW/local-ai-workbench", "C:/repo"),
    ]
    assert "ghp_TEST_SECRET_DO_NOT_LEAK" not in output
    assert summary["result"] == "success"
    assert_no_side_effects(summary)


def test_cli_returns_nonzero_for_blocked_result(monkeypatch, capsys):
    class FakeClient:
        def __init__(self, repo, token=None):
            pass

    def fake_run(**kwargs):
        return {
            "protocol": "lawb.bridge_operator_b1_dry_run_summary.v1",
            "result": "blocked",
            "blocked_reasons": ["missing_request"],
            "broad_issue_scan_performed": False,
            "latest_next_inference_performed": False,
            "dispatcher_invoked": False,
            "runner_invoked": False,
            "codex_invoked": False,
            "github_write_performed": False,
            "commit_performed": False,
            "push_performed": False,
        }

    monkeypatch.setattr(cli, "GitHubApiClient", FakeClient)
    monkeypatch.setattr(cli, "run_bridge_operator_b1_dry_run", fake_run)

    result = cli.main(["--inbox-issue", "999"])
    summary = read_json(capsys)

    assert result == 1
    assert summary["result"] == "blocked"
    assert_no_side_effects(summary)


def test_cli_help_preserves_argparse_behavior(capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(["--help"])

    output = capsys.readouterr().out
    assert error.value.code == 0
    assert "usage:" in output
    assert "blocked_reasons" not in output

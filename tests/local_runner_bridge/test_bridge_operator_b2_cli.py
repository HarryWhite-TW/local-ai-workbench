import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import local_runner_bridge.bridge_operator_b2_cli as cli


def read_json(capsys):
    output = capsys.readouterr().out
    assert output.count("{") == 1
    return json.loads(output)


def assert_no_side_effects(summary):
    assert summary["broad_issue_scan_performed"] is False
    assert summary["latest_next_inference_performed"] is False
    assert summary["dispatcher_invocation_count"] <= 1
    assert summary["retry_performed"] is False
    assert summary["loop_started"] is False
    assert summary["background_service_started"] is False
    assert summary["commit_performed"] is False
    assert summary["push_performed"] is False
    assert summary["pr_created"] is False


def test_cli_requires_repo_root_and_prints_blocked_json(capsys):
    result = cli.main([])
    summary = read_json(capsys)

    assert result == 2
    assert summary["result"] == "blocked"
    assert summary["blocked_reasons"] == ["invalid_arguments"]
    assert_no_side_effects(summary)


def test_cli_routes_fixed_inbox_to_b2_without_printing_credentials(monkeypatch, capsys):
    calls = []

    class FakeClient:
        def __init__(self, repo, token=None):
            calls.append(("client", repo, token))

    def fake_run(**kwargs):
        calls.append(("run", kwargs["inbox_issue"], kwargs["repository"], str(kwargs["repo_root"])))
        return {
            "protocol": "lawb.bridge_operator_b2_delegation_summary.v1",
            "result": "success",
            "configured_inbox_issue": 147,
            "broad_issue_scan_performed": False,
            "latest_next_inference_performed": False,
            "dispatcher_invoked": True,
            "dispatcher_invocation_count": 1,
            "retry_performed": False,
            "loop_started": False,
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
    monkeypatch.setattr(cli, "run_bridge_operator_b2_once", fake_run)
    monkeypatch.setenv("B2_TOKEN", "ghp_TEST_SECRET_DO_NOT_LEAK")

    result = cli.main(
        [
            "--repo-root",
            "C:/repo",
            "--github-token-env",
            "B2_TOKEN",
        ]
    )
    output = capsys.readouterr().out
    summary = json.loads(output)

    assert result == 0
    assert calls == [
        ("client", "HarryWhite-TW/local-ai-workbench", "ghp_TEST_SECRET_DO_NOT_LEAK"),
        ("run", 147, "HarryWhite-TW/local-ai-workbench", "C:\\repo"),
    ]
    assert "ghp_TEST_SECRET_DO_NOT_LEAK" not in output
    assert summary["result"] == "success"
    assert_no_side_effects(summary)


def test_cli_returns_one_for_blocked_or_failure(monkeypatch, capsys):
    class FakeClient:
        def __init__(self, repo, token=None):
            pass

    def fake_run(**kwargs):
        return {
            "protocol": "lawb.bridge_operator_b2_delegation_summary.v1",
            "result": "failure",
            "configured_inbox_issue": 147,
            "blocked_reasons": ["target_result_missing"],
            "broad_issue_scan_performed": False,
            "latest_next_inference_performed": False,
            "dispatcher_invoked": True,
            "dispatcher_invocation_count": 1,
            "retry_performed": False,
            "loop_started": False,
            "background_service_started": False,
            "commit_performed": False,
            "push_performed": False,
            "pr_created": False,
        }

    monkeypatch.setattr(cli, "GitHubApiClient", FakeClient)
    monkeypatch.setattr(cli, "run_bridge_operator_b2_once", fake_run)

    result = cli.main(["--repo-root", "C:/repo"])
    summary = read_json(capsys)

    assert result == 1
    assert summary["result"] == "failure"
    assert_no_side_effects(summary)


def test_cli_help_preserves_argparse_behavior(capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(["--help"])

    output = capsys.readouterr().out
    assert error.value.code == 0
    assert "usage:" in output
    assert "blocked_reasons" not in output


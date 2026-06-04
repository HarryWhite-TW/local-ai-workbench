import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import local_runner_bridge.explicit_task_surface_fetch_cli as cli


VALID_SURFACE = """LOCAL-RUNNER-TASK-PACKET-V1
BEGIN_TASK_PACKET
protocol: lawb.local_runner.task_packet.v1
packet_id: task-146-explicit-fetch-cli
logical_issue: 146
phase: read_only_explicit_fetch_local_smoke_entry_reviewbundle
action_type: read_only_audit
risk_level: low
repository: HarryWhite-TW/local-ai-workbench
branch: master
expected_head: ca82937c6b0a889df5d45cbff56a3fbba6a6e648
allowed_files:
  - src/local_runner_bridge/explicit_task_surface_fetch_cli.py
  - tests/local_runner_bridge/test_explicit_task_surface_fetch_cli.py
forbidden_operations:
  - commit
  - push
approval:
  required: false
payload:
  kind: none
result_target:
  github_issue: 114
  marker: REVIEWBUNDLE-AUDIT-VISIBLE
stop_condition: stop_after_local_validation
END_TASK_PACKET
"""


def success_summary(reference_type="local_text"):
    return {
        "protocol": "lawb.local_runner.explicit_task_surface_fetch_summary.v1",
        "result": "success",
        "reference_type": reference_type,
        "bounded_read_performed": True,
        "broad_issue_scan_performed": False,
        "github_write_performed": False,
        "result_packet_written": False,
        "codex_side_action_executed": False,
        "commit_triggered": False,
        "push_triggered": False,
        "pr_triggered": False,
        "issue_closed": False,
        "label_changed": False,
        "errors": [],
        "validation_summary": {"result": "success"},
    }


def assert_no_write_or_action(summary):
    assert summary["broad_issue_scan_performed"] is False
    assert summary["github_write_performed"] is False
    assert summary["result_packet_written"] is False
    assert summary["codex_side_action_executed"] is False
    assert summary["commit_triggered"] is False
    assert summary["push_triggered"] is False


def read_stdout_json(capsys):
    return json.loads(capsys.readouterr().out)


def test_local_text_file_routes_through_helper_and_prints_json(
    tmp_path,
    monkeypatch,
    capsys,
):
    surface_path = tmp_path / "surface.txt"
    surface_path.write_text(VALID_SURFACE, encoding="utf-8")
    calls = []

    def fake_fetch(reference, *, github_token=None):
        calls.append((reference, github_token))
        return success_summary()

    monkeypatch.setattr(cli, "run_explicit_task_surface_fetch", fake_fetch)

    result = cli.main(["--local-text-file", str(surface_path)])
    summary = read_stdout_json(capsys)

    assert result == 0
    assert calls == [(VALID_SURFACE, None)]
    assert summary["result"] == "success"
    assert summary["reference_type"] == "local_text"
    assert summary["validation_summary"]["result"] == "success"
    assert_no_write_or_action(summary)


def test_missing_input_fails_closed_and_prints_json(capsys):
    result = cli.main([])
    summary = read_stdout_json(capsys)

    assert result == 0
    assert summary["result"] == "blocked"
    assert summary["errors"] == ["missing_input"]
    assert summary["bounded_read_performed"] is False
    assert_no_write_or_action(summary)


def test_multiple_inputs_fail_closed_without_helper_call(monkeypatch, capsys):
    calls = []

    def fake_fetch(reference, *, github_token=None):
        calls.append((reference, github_token))
        return success_summary()

    monkeypatch.setattr(cli, "run_explicit_task_surface_fetch", fake_fetch)

    result = cli.main(
        [
            "--local-text-file",
            "surface.txt",
            "--issue-url",
            "https://github.com/HarryWhite-TW/local-ai-workbench/issues/146",
        ]
    )
    summary = read_stdout_json(capsys)

    assert result == 0
    assert calls == []
    assert summary["result"] == "blocked"
    assert summary["errors"] == ["multiple_inputs"]
    assert summary["bounded_read_performed"] is False
    assert_no_write_or_action(summary)


def test_issue_url_routes_through_helper_without_live_network(monkeypatch, capsys):
    calls = []

    def fake_fetch(reference, *, github_token=None):
        calls.append((reference, github_token))
        return success_summary(reference_type="issue_url")

    monkeypatch.setattr(cli, "run_explicit_task_surface_fetch", fake_fetch)

    result = cli.main(
        [
            "--issue-url",
            "https://github.com/HarryWhite-TW/local-ai-workbench/issues/146",
        ]
    )
    summary = read_stdout_json(capsys)

    assert result == 0
    assert calls == [
        ("https://github.com/HarryWhite-TW/local-ai-workbench/issues/146", None)
    ]
    assert summary["result"] == "success"
    assert summary["reference_type"] == "issue_url"
    assert_no_write_or_action(summary)


def test_comment_url_routes_through_helper_without_live_network(monkeypatch, capsys):
    calls = []

    def fake_fetch(reference, *, github_token=None):
        calls.append((reference, github_token))
        return success_summary(reference_type="issue_comment_url")

    monkeypatch.setattr(cli, "run_explicit_task_surface_fetch", fake_fetch)

    result = cli.main(
        [
            "--comment-url",
            "https://github.com/HarryWhite-TW/local-ai-workbench/issues/146"
            "#issuecomment-123",
        ]
    )
    summary = read_stdout_json(capsys)

    assert result == 0
    assert calls == [
        (
            "https://github.com/HarryWhite-TW/local-ai-workbench/issues/146"
            "#issuecomment-123",
            None,
        )
    ]
    assert summary["result"] == "success"
    assert summary["reference_type"] == "issue_comment_url"
    assert_no_write_or_action(summary)


def test_github_token_env_name_does_not_leak_token_to_stdout(
    monkeypatch,
    capsys,
):
    seen_tokens = []
    monkeypatch.setenv("TASK_SURFACE_TOKEN", "ghp_TEST_SECRET_DO_NOT_LEAK")

    def fake_fetch(reference, *, github_token=None):
        seen_tokens.append(github_token)
        return success_summary(reference_type="issue_url")

    monkeypatch.setattr(cli, "run_explicit_task_surface_fetch", fake_fetch)

    result = cli.main(
        [
            "--issue-url",
            "https://github.com/HarryWhite-TW/local-ai-workbench/issues/146",
            "--github-token-env",
            "TASK_SURFACE_TOKEN",
        ]
    )
    output = capsys.readouterr().out
    summary = json.loads(output)

    assert result == 0
    assert seen_tokens == ["ghp_TEST_SECRET_DO_NOT_LEAK"]
    assert "ghp_TEST_SECRET_DO_NOT_LEAK" not in output
    assert summary["result"] == "success"
    assert_no_write_or_action(summary)


def test_broad_phrase_issue_url_delegates_rejection_to_helper(monkeypatch, capsys):
    calls = []

    def fake_fetch(reference, *, github_token=None):
        calls.append((reference, github_token))
        return {
            "protocol": "lawb.local_runner.explicit_task_surface_fetch_summary.v1",
            "result": "blocked",
            "reference_type": None,
            "bounded_read_performed": False,
            "broad_issue_scan_performed": False,
            "github_write_performed": False,
            "result_packet_written": False,
            "codex_side_action_executed": False,
            "commit_triggered": False,
            "push_triggered": False,
            "pr_triggered": False,
            "issue_closed": False,
            "label_changed": False,
            "errors": ["broad_reference_rejected"],
        }

    monkeypatch.setattr(cli, "run_explicit_task_surface_fetch", fake_fetch)

    result = cli.main(["--issue-url", "latest issue"])
    summary = read_stdout_json(capsys)

    assert result == 0
    assert calls == [("latest issue", None)]
    assert summary["result"] == "blocked"
    assert summary["errors"] == ["broad_reference_rejected"]
    assert summary["bounded_read_performed"] is False
    assert_no_write_or_action(summary)

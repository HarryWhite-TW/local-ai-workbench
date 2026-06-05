import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import local_runner_bridge.explicit_fetch_result_surface_cli as cli
from local_runner_bridge.result_surface import REQUIRED_SAFETY_FLAGS


VALID_SURFACE = """LOCAL-RUNNER-TASK-PACKET-V1
BEGIN_TASK_PACKET
protocol: lawb.local_runner.task_packet.v1
packet_id: task-163-explicit-fetch-result-surface-cli
logical_issue: 163
phase: explicit_fetch_to_result_surface_cli_reviewbundle
action_type: read_only_audit
risk_level: low
repository: HarryWhite-TW/local-ai-workbench
branch: master
expected_head: 88f78c1a40aa93081d0078a3f055e5c8fe1778ed
allowed_files:
  - src/local_runner_bridge/explicit_fetch_result_surface_cli.py
  - tests/local_runner_bridge/test_explicit_fetch_result_surface_cli.py
forbidden_operations:
  - commit
  - push
approval:
  required: false
payload:
  kind: none
result_target:
  github_issue: 114
  marker: EXPLICIT-FETCH-RESULT-SURFACE-CLI-VISIBLE
stop_condition: stop_after_local_validation
END_TASK_PACKET
"""


def read_stdout_json(capsys):
    return json.loads(capsys.readouterr().out)


def test_cli_local_text_file_input_prints_valid_json(tmp_path, capsys):
    path = tmp_path / "surface.txt"
    path.write_text(VALID_SURFACE, encoding="utf-8")

    result = cli.main(["--local-text-file", str(path)])
    result_surface = read_stdout_json(capsys)

    assert result == 0
    assert result_surface["status"] == "success"
    assert result_surface["requires_user_approval"] is True


def test_cli_output_does_not_leak_token_values(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("EXPLICIT_FETCH_RESULT_SURFACE_TOKEN", "ghp_TEST_SECRET_DO_NOT_LEAK")
    path = tmp_path / "surface.txt"
    path.write_text(VALID_SURFACE, encoding="utf-8")

    result = cli.main(["--local-text-file", str(path)])
    output = capsys.readouterr().out

    assert result == 0
    assert "ghp_TEST_SECRET_DO_NOT_LEAK" not in output
    assert "EXPLICIT_FETCH_RESULT_SURFACE_TOKEN" not in output


def test_cli_does_not_write_files(tmp_path, monkeypatch, capsys):
    path = tmp_path / "surface.txt"
    path.write_text(VALID_SURFACE, encoding="utf-8")
    before = {item.name for item in tmp_path.iterdir()}
    monkeypatch.chdir(tmp_path)

    result = cli.main(["--local-text-file", str(path)])
    result_surface = read_stdout_json(capsys)
    after = {item.name for item in tmp_path.iterdir()}

    assert result == 0
    assert result_surface["safety_flags"]["github_write_performed"] is False
    assert after == before


def test_cli_does_not_call_live_github_for_issue_arg(capsys):
    result = cli.main(
        ["--issue-url", "https://github.com/HarryWhite-TW/local-ai-workbench/issues/163"]
    )
    result_surface = read_stdout_json(capsys)

    assert result == 0
    assert result_surface["status"] == "blocked"
    assert "github_token_required_for_live_fetch" in result_surface[
        "blocked_reasons"
    ]


def test_cli_does_not_execute_tasks(tmp_path, capsys):
    path = tmp_path / "surface.txt"
    path.write_text(VALID_SURFACE, encoding="utf-8")

    result = cli.main(["--local-text-file", str(path)])
    result_surface = read_stdout_json(capsys)

    assert result == 0
    flags = result_surface["safety_flags"]
    assert set(flags) == set(REQUIRED_SAFETY_FLAGS)
    assert flags["codex_side_action_executed"] is False
    assert flags["runner_invoked"] is False
    assert flags["dispatcher_invoked"] is False
    assert flags["watcher_invoked"] is False


def test_cli_rejects_ambiguous_inputs(tmp_path, capsys):
    path = tmp_path / "surface.txt"
    path.write_text(VALID_SURFACE, encoding="utf-8")

    result = cli.main(
        [
            "--local-text-file",
            str(path),
            "--comment-url",
            "https://github.com/HarryWhite-TW/local-ai-workbench/issues/163"
            "#issuecomment-123",
        ]
    )
    result_surface = read_stdout_json(capsys)

    assert result == 0
    assert result_surface["status"] == "blocked"
    assert "multiple_inputs" in result_surface["blocked_reasons"]


def test_cli_issue_url_with_github_token_env_uses_stubbed_fetch(
    monkeypatch,
    capsys,
):
    calls = []
    monkeypatch.setenv("TASK_SURFACE_TOKEN", "ghp_TEST_SECRET_DO_NOT_LEAK")

    def fake_build(**kwargs):
        calls.append(kwargs)
        return {
            "result_surface_version": "lawb.local_result_surface.v0.draft",
            "result_id": "result-cli-issue",
            "source_task_reference": {"kind": "issue_url"},
            "source_task_validation_result": {"result": "success"},
            "operation_mode": "explicit_fetch_result_surface_review",
            "status": "success",
            "summary": "stubbed",
            "files_changed": [],
            "tests_run": [],
            "safety_flags": {flag: False for flag in REQUIRED_SAFETY_FLAGS},
            "blocked_reasons": [],
            "requires_user_approval": True,
            "next_recommended_step": "chatgpt_review",
            "created_at": "2026-06-05T00:00:00Z",
        }

    monkeypatch.setattr(cli, "build_result_surface_from_explicit_reference", fake_build)

    result = cli.main(
        [
            "--issue-url",
            "https://github.com/HarryWhite-TW/local-ai-workbench/issues/163",
            "--github-token-env",
            "TASK_SURFACE_TOKEN",
        ]
    )
    output = capsys.readouterr().out
    result_surface = json.loads(output)

    assert result == 0
    assert result_surface["status"] == "success"
    assert calls[0]["github_token"] == "ghp_TEST_SECRET_DO_NOT_LEAK"
    assert "ghp_TEST_SECRET_DO_NOT_LEAK" not in output


def test_cli_comment_url_with_github_token_env_uses_stubbed_fetch(
    monkeypatch,
    capsys,
):
    calls = []
    monkeypatch.setenv("TASK_SURFACE_TOKEN", "ghp_TEST_SECRET_DO_NOT_LEAK")

    def fake_build(**kwargs):
        calls.append(kwargs)
        return {
            "result_surface_version": "lawb.local_result_surface.v0.draft",
            "result_id": "result-cli-comment",
            "source_task_reference": {"kind": "comment_url"},
            "source_task_validation_result": {"result": "success"},
            "operation_mode": "explicit_fetch_result_surface_review",
            "status": "success",
            "summary": "stubbed",
            "files_changed": [],
            "tests_run": [],
            "safety_flags": {flag: False for flag in REQUIRED_SAFETY_FLAGS},
            "blocked_reasons": [],
            "requires_user_approval": True,
            "next_recommended_step": "chatgpt_review",
            "created_at": "2026-06-05T00:00:00Z",
        }

    monkeypatch.setattr(cli, "build_result_surface_from_explicit_reference", fake_build)

    result = cli.main(
        [
            "--comment-url",
            "https://github.com/HarryWhite-TW/local-ai-workbench/issues/163"
            "#issuecomment-123",
            "--github-token-env",
            "TASK_SURFACE_TOKEN",
        ]
    )
    output = capsys.readouterr().out

    assert result == 0
    assert json.loads(output)["status"] == "success"
    assert calls[0]["github_token"] == "ghp_TEST_SECRET_DO_NOT_LEAK"
    assert "ghp_TEST_SECRET_DO_NOT_LEAK" not in output

import json
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import local_runner_bridge.approval_record_cli as cli


FORBIDDEN_ACTIONS = [
    "github_writeback_implementation",
    "github_comment_write",
    "github_issue_body_update",
    "result_packet_write_implementation",
    "codex_side_action_execution",
    "runner_behavior",
    "dispatcher_behavior",
    "watcher_behavior",
    "broad_issue_scan",
    "next_latest_issue_inference",
    "autonomous_execution",
    "automatic_commit",
    "automatic_push",
    "pr_creation",
    "merge",
    "issue_close",
    "label_change",
    "approval_chaining",
    "real_write_mode",
]


def valid_approval_record():
    return {
        "approval_record_version": "lawb.writeback_approval_record.v1.sample",
        "approval_id": "approval-183-cli",
        "source_preview_id": "preview-183-cli",
        "source_result_surface_id": "result-183-cli",
        "source_task_reference": "task-183-local-approval-record-validator",
        "writeback_target_type": "github_issue_comment",
        "writeback_target_reference": (
            "https://github.com/HarryWhite-TW/local-ai-workbench/issues/114"
            "#future-approved-comment-target"
        ),
        "chatgpt_readback_completed": True,
        "approved_by_user": True,
        "approval_timestamp": "2026-06-06T00:00:00Z",
        "approved_write_mode": "dry_run_only",
        "allowed_next_step": "bounded_writeback_planning",
        "forbidden_actions": FORBIDDEN_ACTIONS.copy(),
        "external_side_effect_allowed": False,
        "created_at": "2026-06-06T00:00:00Z",
    }


def write_approval_record(tmp_path, record=None):
    approval_record_path = tmp_path / "approval_record.json"
    approval_record_path.write_text(
        json.dumps(record or valid_approval_record()), encoding="utf-8"
    )
    return approval_record_path


def read_stdout_json(capsys):
    return json.loads(capsys.readouterr().out)


def test_cli_reads_one_local_json_file_and_prints_valid_json_summary(tmp_path, capsys):
    approval_record_path = write_approval_record(tmp_path)

    result = cli.main(["--approval-record-file", str(approval_record_path)])
    summary = read_stdout_json(capsys)

    assert result == 0
    assert summary["validation_result"] == "success"
    assert summary["approval_id"] == "approval-183-cli"
    assert summary["external_side_effect_allowed"] is False


def test_cli_does_not_write_files(tmp_path, capsys):
    approval_record_path = write_approval_record(tmp_path)
    before = sorted(path.name for path in tmp_path.iterdir())

    result = cli.main(["--approval-record-file", str(approval_record_path)])
    summary = read_stdout_json(capsys)
    after = sorted(path.name for path in tmp_path.iterdir())

    assert result == 0
    assert summary["validation_result"] == "success"
    assert before == after == ["approval_record.json"]


def test_cli_does_not_call_github(tmp_path, monkeypatch, capsys):
    approval_record_path = write_approval_record(tmp_path)

    def fail_if_network(*args, **kwargs):
        raise AssertionError("network call attempted")

    monkeypatch.setattr(socket, "create_connection", fail_if_network)

    result = cli.main(["--approval-record-file", str(approval_record_path)])
    summary = read_stdout_json(capsys)

    assert result == 0
    assert summary["validation_result"] == "success"
    assert summary["github_write_performed"] is False


def test_cli_does_not_execute_tasks(tmp_path, monkeypatch, capsys):
    approval_record_path = write_approval_record(tmp_path)

    def fail_if_subprocess(*args, **kwargs):
        raise AssertionError("task execution attempted")

    monkeypatch.setattr(subprocess, "run", fail_if_subprocess)

    result = cli.main(["--approval-record-file", str(approval_record_path)])
    summary = read_stdout_json(capsys)

    assert result == 0
    assert summary["validation_result"] == "success"
    assert summary["codex_side_action_executed"] is False
    assert summary["runner_invoked"] is False
    assert summary["dispatcher_invoked"] is False
    assert summary["watcher_invoked"] is False


def test_cli_does_not_leak_token_value_to_stdout(tmp_path, capsys):
    record = valid_approval_record()
    record["source_preview_id"] = "github_pat_TEST_SECRET_DO_NOT_LEAK"
    approval_record_path = write_approval_record(tmp_path, record)

    result = cli.main(["--approval-record-file", str(approval_record_path)])
    output = capsys.readouterr().out
    summary = json.loads(output)

    assert result == 0
    assert summary["validation_result"] == "blocked"
    assert "token_value_detected" in summary["blocked_reasons"]
    assert "github_pat_TEST_SECRET_DO_NOT_LEAK" not in output


def test_invalid_arguments_fail_closed_and_print_json(capsys):
    result = cli.main([])
    summary = read_stdout_json(capsys)

    assert result == 2
    assert summary["validation_result"] == "blocked"
    assert summary["blocked_reasons"] == ["invalid_arguments"]
    assert summary["external_side_effect_allowed"] is False

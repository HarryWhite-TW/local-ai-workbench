import json
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import local_runner_bridge.readiness_gate_cli as cli


def valid_readiness_gate():
    return {
        "readiness_gate_version": "lawb.bounded_writeback_readiness_gate.v1.sample",
        "readiness_id": "readiness-189-cli",
        "source_task_reference": "task-189-local-readiness-gate-validator",
        "source_result_surface_id": "result-189-cli",
        "writeback_target_reference": (
            "https://github.com/HarryWhite-TW/local-ai-workbench/issues/114"
            "#future-approved-comment-target"
        ),
        "target_contract_validation_result": "success",
        "dry_run_preview_result": "success",
        "chatgpt_readback_completed": True,
        "approval_record_validation_result": "success",
        "approved_write_mode": "dry_run_only",
        "external_side_effect_allowed": False,
        "real_write_mode_allowed": False,
        "readiness_result": "pass",
        "blocked_reasons": [],
        "next_recommended_step": "review_only_no_write",
        "created_at": "2026-06-06T00:00:00Z",
    }


def write_readiness_gate(tmp_path, record=None):
    readiness_path = tmp_path / "readiness_gate.json"
    readiness_path.write_text(
        json.dumps(record or valid_readiness_gate()), encoding="utf-8"
    )
    return readiness_path


def read_stdout_json(capsys):
    return json.loads(capsys.readouterr().out)


def test_cli_reads_one_local_json_file_and_prints_valid_json_summary(tmp_path, capsys):
    readiness_path = write_readiness_gate(tmp_path)

    result = cli.main(["--readiness-file", str(readiness_path)])
    summary = read_stdout_json(capsys)

    assert result == 0
    assert summary["validation_result"] == "success"
    assert summary["readiness_id"] == "readiness-189-cli"
    assert summary["external_side_effect_allowed"] is False
    assert summary["real_write_mode_allowed"] is False


def test_cli_does_not_write_files(tmp_path, capsys):
    readiness_path = write_readiness_gate(tmp_path)
    before = sorted(path.name for path in tmp_path.iterdir())

    result = cli.main(["--readiness-file", str(readiness_path)])
    summary = read_stdout_json(capsys)
    after = sorted(path.name for path in tmp_path.iterdir())

    assert result == 0
    assert summary["validation_result"] == "success"
    assert before == after == ["readiness_gate.json"]


def test_cli_does_not_call_github(tmp_path, monkeypatch, capsys):
    readiness_path = write_readiness_gate(tmp_path)

    def fail_if_network(*args, **kwargs):
        raise AssertionError("network call attempted")

    monkeypatch.setattr(socket, "create_connection", fail_if_network)

    result = cli.main(["--readiness-file", str(readiness_path)])
    summary = read_stdout_json(capsys)

    assert result == 0
    assert summary["validation_result"] == "success"
    assert summary["github_write_performed"] is False


def test_cli_does_not_execute_tasks(tmp_path, monkeypatch, capsys):
    readiness_path = write_readiness_gate(tmp_path)

    def fail_if_subprocess(*args, **kwargs):
        raise AssertionError("task execution attempted")

    monkeypatch.setattr(subprocess, "run", fail_if_subprocess)

    result = cli.main(["--readiness-file", str(readiness_path)])
    summary = read_stdout_json(capsys)

    assert result == 0
    assert summary["validation_result"] == "success"
    assert summary["codex_side_action_executed"] is False
    assert summary["runner_invoked"] is False
    assert summary["dispatcher_invoked"] is False
    assert summary["watcher_invoked"] is False


def test_cli_does_not_leak_token_value_to_stdout(tmp_path, capsys):
    record = valid_readiness_gate()
    record["source_result_surface_id"] = "github_pat_TEST_SECRET_DO_NOT_LEAK"
    readiness_path = write_readiness_gate(tmp_path, record)

    result = cli.main(["--readiness-file", str(readiness_path)])
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
    assert summary["real_write_mode_allowed"] is False

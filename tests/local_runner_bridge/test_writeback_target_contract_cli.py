import json
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import local_runner_bridge.writeback_target_contract_cli as cli


FORBIDDEN_ACTIONS = [
    "github_writeback_implementation",
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
]


def valid_contract():
    return {
        "contract_version": "lawb.writeback_target_contract.v0.sample",
        "writeback_target_type": "github_issue_comment",
        "writeback_target_reference": (
            "https://github.com/HarryWhite-TW/local-ai-workbench/issues/114"
            "#future-approved-comment-target"
        ),
        "source_result_surface_id": "result-172-local-validator-cli",
        "source_task_reference": "task-172-writeback-target-contract-validator",
        "approved_by_user": True,
        "approval_timestamp": "2026-06-06T00:00:00Z",
        "chatgpt_readback_completed": True,
        "dry_run_required": True,
        "write_mode": "dry_run_only",
        "safe_preview_required": True,
        "forbidden_actions": FORBIDDEN_ACTIONS.copy(),
        "required_safety_flags": {
            "exact_single_target_confirmed": True,
            "chatgpt_readback_completed": True,
            "explicit_user_approval_present": True,
            "safe_preview_completed": True,
            "token_value_printed": False,
            "token_value_written": False,
            "broad_issue_scan_performed": False,
            "next_latest_issue_inference_performed": False,
            "automatic_issue_close_performed": False,
            "automatic_label_change_performed": False,
            "pr_created": False,
            "merge_performed": False,
            "approval_chaining_attempted": False,
        },
        "abort_conditions": [
            "target_missing",
            "target_ambiguous",
            "multiple_targets_present",
            "chatgpt_readback_missing",
            "explicit_user_approval_missing",
            "safe_preview_missing",
            "dry_run_missing",
            "token_value_would_be_printed_or_written",
            "broad_issue_scan_required",
            "next_latest_issue_inference_required",
            "forbidden_action_requested",
        ],
        "next_recommended_step": "chatgpt_review",
    }


def write_contract(tmp_path, contract=None):
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(contract or valid_contract()), encoding="utf-8")
    return contract_path


def read_stdout_json(capsys):
    return json.loads(capsys.readouterr().out)


def test_cli_help_exits_zero_and_prints_expected_argument(capsys):
    result = cli.main(["--help"])
    output = capsys.readouterr().out

    assert result == 0
    assert "--contract-file" in output


def test_cli_reads_one_local_json_file_and_prints_valid_json_summary(tmp_path, capsys):
    contract_path = write_contract(tmp_path)

    result = cli.main(["--contract-file", str(contract_path)])
    summary = read_stdout_json(capsys)

    assert result == 0
    assert summary["validation_result"] == "success"
    assert summary["writeback_target_type"] == "github_issue_comment"
    assert summary["external_side_effect_allowed"] is False


def test_cli_does_not_write_files(tmp_path, capsys):
    contract_path = write_contract(tmp_path)
    before = sorted(path.name for path in tmp_path.iterdir())

    result = cli.main(["--contract-file", str(contract_path)])
    summary = read_stdout_json(capsys)
    after = sorted(path.name for path in tmp_path.iterdir())

    assert result == 0
    assert summary["validation_result"] == "success"
    assert before == after == ["contract.json"]


def test_cli_help_does_not_write_files(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    result = cli.main(["--help"])
    output = capsys.readouterr().out

    assert result == 0
    assert "--contract-file" in output
    assert list(tmp_path.iterdir()) == []


def test_cli_does_not_call_github(tmp_path, monkeypatch, capsys):
    contract_path = write_contract(tmp_path)

    def fail_if_network(*args, **kwargs):
        raise AssertionError("network call attempted")

    monkeypatch.setattr(socket, "create_connection", fail_if_network)

    result = cli.main(["--contract-file", str(contract_path)])
    summary = read_stdout_json(capsys)

    assert result == 0
    assert summary["validation_result"] == "success"
    assert summary["github_write_performed"] is False


def test_cli_does_not_execute_tasks(tmp_path, monkeypatch, capsys):
    contract_path = write_contract(tmp_path)

    def fail_if_subprocess(*args, **kwargs):
        raise AssertionError("task execution attempted")

    monkeypatch.setattr(subprocess, "run", fail_if_subprocess)

    result = cli.main(["--contract-file", str(contract_path)])
    summary = read_stdout_json(capsys)

    assert result == 0
    assert summary["validation_result"] == "success"
    assert summary["codex_side_action_executed"] is False
    assert summary["runner_invoked"] is False
    assert summary["dispatcher_invoked"] is False
    assert summary["watcher_invoked"] is False


def test_cli_does_not_leak_token_value_to_stdout(tmp_path, capsys):
    contract = valid_contract()
    contract["source_task_reference"] = "github_pat_TEST_SECRET_DO_NOT_LEAK"
    contract_path = write_contract(tmp_path, contract)

    result = cli.main(["--contract-file", str(contract_path)])
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

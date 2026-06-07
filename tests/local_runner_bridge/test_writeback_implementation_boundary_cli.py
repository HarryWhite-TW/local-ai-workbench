from __future__ import annotations

import json
from pathlib import Path
import socket
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from local_runner_bridge.writeback_implementation_boundary_cli import main  # noqa: E402
from local_runner_bridge.writeback_implementation_boundary import (  # noqa: E402
    REAL_WRITE_INDICATORS,
)


def valid_boundary_record() -> dict[str, object]:
    real_write_indicators = {field: False for field in REAL_WRITE_INDICATORS}
    return {
        "boundary_version": "lawb.bounded_writeback_implementation_boundary.v1.sample",
        "boundary_id": "boundary-195-local-validator",
        "future_candidate_issue": 195,
        "future_risk_lane_required": "strict",
        "first_possible_writeback_type": "github_issue_comment",
        "allowed_target_type": "explicit_single_github_issue_comment",
        "allowed_target_reference_mode": "explicit_only",
        "source_readiness_id": "readiness-195-local-validator",
        "source_preview_id": "preview-195-local-validator",
        "source_result_surface_id": "result-195-local-validator",
        "required_preconditions": {
            "explicit_user_approval_required": True,
            "explicit_single_target_required": True,
        },
        "required_runtime_gates": {
            "writeback_target_count": 1,
            "broad_issue_scan": False,
            "next_latest_issue_inference_requested": False,
        },
        "forbidden_scope": {
            "github_issue_body_update": True,
            "result_packet_write": True,
            "runner_behavior": True,
            "dispatcher_behavior": True,
            "watcher_behavior": True,
            "approval_chaining": True,
        },
        "future_audit_shape": {
            **real_write_indicators,
            "writeback_target_reference": (
                "https://github.com/HarryWhite-TW/local-ai-workbench/"
                "issues/114#future-approved-comment-target"
            ),
            "approved_write_mode": "dry_run_only",
        },
        "real_write_indicators": real_write_indicators,
        "implementation_allowed_now": False,
        "writeback_allowed_now": False,
        "result_packet_write_allowed_now": False,
        "runner_dispatcher_watcher_allowed_now": False,
        "next_recommended_step": (
            "local_writeback_implementation_boundary_validator_candidate"
        ),
        "created_at": "2026-06-06T00:00:00Z",
    }


def test_cli_reads_one_file_and_prints_json(tmp_path, capsys) -> None:
    boundary_file = tmp_path / "boundary.json"
    boundary_file.write_text(json.dumps(valid_boundary_record()), encoding="utf-8")

    exit_code = main(["--boundary-file", str(boundary_file)])

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert exit_code == 0
    assert summary["validation_result"] == "success"
    assert summary["boundary_id"] == "boundary-195-local-validator"


def test_cli_does_not_write_files(tmp_path, capsys) -> None:
    boundary_file = tmp_path / "boundary.json"
    boundary_file.write_text(json.dumps(valid_boundary_record()), encoding="utf-8")
    before = sorted(path.name for path in tmp_path.iterdir())

    exit_code = main(["--boundary-file", str(boundary_file)])

    after = sorted(path.name for path in tmp_path.iterdir())
    assert exit_code == 0
    assert before == after == ["boundary.json"]
    assert json.loads(capsys.readouterr().out)["validation_result"] == "success"


def test_cli_does_not_open_network(tmp_path, monkeypatch, capsys) -> None:
    boundary_file = tmp_path / "boundary.json"
    boundary_file.write_text(json.dumps(valid_boundary_record()), encoding="utf-8")

    def fail_network(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "create_connection", fail_network)

    assert main(["--boundary-file", str(boundary_file)]) == 0
    assert json.loads(capsys.readouterr().out)["validation_result"] == "success"


def test_cli_does_not_call_subprocess(tmp_path, monkeypatch, capsys) -> None:
    boundary_file = tmp_path / "boundary.json"
    boundary_file.write_text(json.dumps(valid_boundary_record()), encoding="utf-8")

    def fail_subprocess(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("subprocess access is forbidden")

    monkeypatch.setattr(subprocess, "run", fail_subprocess)

    assert main(["--boundary-file", str(boundary_file)]) == 0
    assert json.loads(capsys.readouterr().out)["validation_result"] == "success"


def test_cli_blocks_and_redacts_token_like_values(tmp_path, capsys) -> None:
    record = valid_boundary_record()
    record["source_preview_id"] = "ghp_SECRET_SHOULD_NOT_APPEAR"
    boundary_file = tmp_path / "boundary.json"
    boundary_file.write_text(json.dumps(record), encoding="utf-8")

    exit_code = main(["--boundary-file", str(boundary_file)])

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert exit_code == 1
    assert summary["validation_result"] == "blocked"
    assert "token_value_detected" in summary["blocked_reasons"]
    assert "ghp_SECRET_SHOULD_NOT_APPEAR" not in captured.out


def test_cli_missing_file_returns_blocked_json(capsys) -> None:
    exit_code = main(["--boundary-file", "missing-boundary.json"])

    summary = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert summary["validation_result"] == "blocked"
    assert summary["blocked_reasons"] == ["boundary_file_read_failed"]

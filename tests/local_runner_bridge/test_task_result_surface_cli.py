import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import local_runner_bridge.task_result_surface_cli as cli
from local_runner_bridge.result_surface import REQUIRED_SAFETY_FLAGS


VALID_SURFACE = """LOCAL-RUNNER-TASK-PACKET-V1
BEGIN_TASK_PACKET
protocol: lawb.local_runner.task_packet.v1
packet_id: task-162-result-surface-cli
logical_issue: 162
phase: local_task_validation_to_result_surface_adapter_cli_reviewbundle
action_type: read_only_audit
risk_level: low
repository: HarryWhite-TW/local-ai-workbench
branch: master
expected_head: babff5aa8d561bf195c3d8d18d4dc2e0b89f4706
allowed_files:
  - src/local_runner_bridge/task_result_surface_cli.py
  - tests/local_runner_bridge/test_task_result_surface_cli.py
forbidden_operations:
  - commit
  - push
approval:
  required: false
payload:
  kind: none
result_target:
  github_issue: 114
  marker: RESULT-SURFACE-CLI-VISIBLE
stop_condition: stop_after_local_validation
END_TASK_PACKET
"""


def read_stdout_json(capsys):
    return json.loads(capsys.readouterr().out)


def test_cli_local_text_input_prints_valid_json(tmp_path, capsys):
    surface_path = tmp_path / "surface.txt"
    surface_path.write_text(VALID_SURFACE, encoding="utf-8")

    result = cli.main(["--local-text-file", str(surface_path)])
    result_surface = read_stdout_json(capsys)

    assert result == 0
    assert result_surface["status"] == "success"
    assert result_surface["source_task_validation_result"]["result"] == "success"
    assert result_surface["requires_user_approval"] is True


def test_cli_does_not_write_files(tmp_path, monkeypatch, capsys):
    surface_path = tmp_path / "surface.txt"
    surface_path.write_text(VALID_SURFACE, encoding="utf-8")
    before = {path.name for path in tmp_path.iterdir()}
    monkeypatch.chdir(tmp_path)

    result = cli.main(["--local-text-file", str(surface_path)])
    result_surface = read_stdout_json(capsys)
    after = {path.name for path in tmp_path.iterdir()}

    assert result == 0
    assert result_surface["safety_flags"]["github_write_performed"] is False
    assert after == before


def test_cli_does_not_call_github_or_execute_tasks(tmp_path, capsys):
    surface_path = tmp_path / "surface.txt"
    surface_path.write_text(VALID_SURFACE, encoding="utf-8")

    result = cli.main(["--local-text-file", str(surface_path)])
    result_surface = read_stdout_json(capsys)

    assert result == 0
    flags = result_surface["safety_flags"]
    assert set(flags) == set(REQUIRED_SAFETY_FLAGS)
    assert flags["github_write_performed"] is False
    assert flags["codex_side_action_executed"] is False
    assert flags["runner_invoked"] is False
    assert flags["dispatcher_invoked"] is False
    assert flags["watcher_invoked"] is False


def test_blocked_surface_prints_blocked_review_artifact(tmp_path, capsys):
    surface_path = tmp_path / "blocked.txt"
    surface_path.write_text("LOCAL-RUNNER-TASK-PACKET-V1\n", encoding="utf-8")

    result = cli.main(["--local-text-file", str(surface_path)])
    result_surface = read_stdout_json(capsys)

    assert result == 0
    assert result_surface["status"] == "blocked"
    assert "task_packet_boundary_markers_missing" in result_surface["blocked_reasons"]


def test_no_token_value_leaks_into_stdout(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TASK_RESULT_SURFACE_TOKEN", "ghp_TEST_SECRET_DO_NOT_LEAK")
    surface_path = tmp_path / "surface.txt"
    surface_path.write_text(VALID_SURFACE, encoding="utf-8")

    result = cli.main(["--local-text-file", str(surface_path)])
    output = capsys.readouterr().out

    assert result == 0
    assert "ghp_TEST_SECRET_DO_NOT_LEAK" not in output
    assert "TASK_RESULT_SURFACE_TOKEN" not in output


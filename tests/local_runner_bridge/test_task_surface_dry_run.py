import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from local_runner_bridge.task_surface_dry_run import main, run_validation_dry_run


VALID_PACKET = """protocol: lawb.local_runner.task_packet.v1
packet_id: task-142-read-only-dry-run
logical_issue: 142
phase: minimal_read_only_validation_dry_run_entry_reviewbundle
action_type: read_only_audit
risk_level: low
repository: HarryWhite-TW/local-ai-workbench
branch: master
expected_head: 80735a115377ba115b02dac1d45ba681ea9f2893
allowed_files:
  - src/local_runner_bridge/task_surface_dry_run.py
  - tests/local_runner_bridge/test_task_surface_dry_run.py
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
"""


EXPECTED = {
    "logical_issue": 142,
    "phase": "minimal_read_only_validation_dry_run_entry_reviewbundle",
}


def surface(packet_text=VALID_PACKET):
    return (
        "LOCAL-RUNNER-TASK-PACKET-V1\n"
        "BEGIN_TASK_PACKET\n"
        f"{packet_text}"
        "END_TASK_PACKET\n"
    )


def assert_no_authority(summary):
    assert summary["codex_side_action_executed"] is False
    assert summary["result_packet_written"] is False
    assert summary["github_write_performed"] is False
    assert summary["commit_performed"] is False
    assert summary["push_performed"] is False


def test_run_validation_dry_run_valid_surface_returns_success():
    summary = run_validation_dry_run(surface(), expected=EXPECTED)

    assert summary["result"] == "success"
    assert_no_authority(summary)


def test_run_validation_dry_run_blocked_surface_returns_blocked():
    summary = run_validation_dry_run("LOCAL-RUNNER-TASK-PACKET-V1\n", expected=EXPECTED)

    assert summary["result"] == "blocked"
    assert_no_authority(summary)


def test_success_summary_does_not_authorize_execution_or_writes():
    summary = run_validation_dry_run(surface(), expected=EXPECTED)

    assert summary["result"] == "success"
    assert summary["repo_files_modified"] is False
    assert_no_authority(summary)


def test_blocked_summary_does_not_authorize_execution_or_writes():
    summary = run_validation_dry_run("missing markers", expected=EXPECTED)

    assert summary["result"] == "blocked"
    assert summary["repo_files_modified"] is False
    assert_no_authority(summary)


def test_main_reads_stdin_and_prints_json_summary(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(surface()))

    result = main()
    output = capsys.readouterr().out
    summary = json.loads(output)

    assert result == 0
    assert summary["result"] == "success"
    assert_no_authority(summary)


def test_main_returns_0_for_valid_summary(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(surface()))

    result = main()

    assert result == 0
    assert json.loads(capsys.readouterr().out)["result"] == "success"


def test_main_returns_0_for_blocked_summary(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("LOCAL-RUNNER-TASK-PACKET-V1\n"))

    result = main()

    assert result == 0
    assert json.loads(capsys.readouterr().out)["result"] == "blocked"

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from local_runner_bridge.task_surface_validation_flow import validate_task_surface


VALID_PACKET = """protocol: lawb.local_runner.task_packet.v1
packet_id: task-141-read-only-surface-flow
logical_issue: 141
phase: read_only_task_surface_validation_flow_reviewbundle
action_type: read_only_audit
risk_level: low
repository: HarryWhite-TW/local-ai-workbench
branch: master
expected_head: 9689d54d2c856a84726887aa5d9aae65262f53b0
allowed_files:
  - src/local_runner_bridge/task_surface_validation_flow.py
  - tests/local_runner_bridge/test_task_surface_validation_flow.py
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
    "logical_issue": 141,
    "phase": "read_only_task_surface_validation_flow_reviewbundle",
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


def test_valid_surface_returns_success():
    summary = validate_task_surface(surface(), expected=EXPECTED)

    assert summary["result"] == "success"
    assert summary["task_packet_protocol_valid"] is True
    assert summary["required_fields_present"] is True
    assert_no_authority(summary)


def test_invalid_embedded_boundary_marker_returns_blocked():
    text = (
        "LOCAL-RUNNER-TASK-PACKET-V1\n"
        "prefix BEGIN_TASK_PACKET suffix\n"
        f"{VALID_PACKET}"
        "END_TASK_PACKET\n"
    )

    summary = validate_task_surface(text, expected=EXPECTED)

    assert summary["result"] == "blocked"
    assert "begin_task_packet_missing" in summary["errors"]
    assert_no_authority(summary)


def test_invalid_protocol_returns_blocked():
    packet = VALID_PACKET.replace(
        "lawb.local_runner.task_packet.v1", "lawb.local_runner.task_packet.v0"
    )

    summary = validate_task_surface(surface(packet), expected=EXPECTED)

    assert summary["result"] == "blocked"
    assert "invalid_task_packet_protocol" in summary["errors"]
    assert_no_authority(summary)


def test_unknown_top_level_field_returns_blocked():
    packet = VALID_PACKET + "unexpected_authority: true\n"

    summary = validate_task_surface(surface(packet), expected=EXPECTED)

    assert summary["result"] == "blocked"
    assert "unknown_top_level_fields" in summary["errors"]
    assert summary["unknown_fields"] == ["unexpected_authority"]
    assert_no_authority(summary)


def test_scalar_allowed_files_returns_blocked():
    packet = VALID_PACKET.replace(
        "allowed_files:\n"
        "  - src/local_runner_bridge/task_surface_validation_flow.py\n"
        "  - tests/local_runner_bridge/test_task_surface_validation_flow.py\n",
        "allowed_files: src/local_runner_bridge/task_surface_validation_flow.py\n",
    )

    summary = validate_task_surface(surface(packet), expected=EXPECTED)

    assert summary["result"] == "blocked"
    assert "invalid_list_fields" in summary["errors"]
    assert summary["invalid_list_fields"] == ["allowed_files"]
    assert_no_authority(summary)


def test_expected_logical_issue_mismatch_returns_blocked():
    summary = validate_task_surface(
        surface(), expected={**EXPECTED, "logical_issue": 999}
    )

    assert summary["result"] == "blocked"
    assert "logical_issue_mismatch" in summary["errors"]
    assert_no_authority(summary)


def test_expected_phase_mismatch_returns_blocked():
    summary = validate_task_surface(surface(), expected={**EXPECTED, "phase": "wrong"})

    assert summary["result"] == "blocked"
    assert "phase_mismatch" in summary["errors"]
    assert_no_authority(summary)


def test_success_does_not_authorize_execution_commit_or_push():
    summary = validate_task_surface(surface(), expected=EXPECTED)

    assert summary["result"] == "success"
    assert summary["codex_side_action_executed"] is False
    assert summary["repo_files_modified"] is False
    assert summary["result_packet_written"] is False
    assert summary["github_write_performed"] is False
    assert summary["commit_performed"] is False
    assert summary["push_performed"] is False


def test_blocked_result_does_not_authorize_execution_commit_or_push():
    summary = validate_task_surface("LOCAL-RUNNER-TASK-PACKET-V1\n", expected=EXPECTED)

    assert summary["result"] == "blocked"
    assert summary["codex_side_action_executed"] is False
    assert summary["repo_files_modified"] is False
    assert summary["result_packet_written"] is False
    assert summary["github_write_performed"] is False
    assert summary["commit_performed"] is False
    assert summary["push_performed"] is False

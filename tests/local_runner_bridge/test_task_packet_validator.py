import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from local_runner_bridge.task_packet_validator import validate_task_packet
from local_runner_bridge.task_surface_resolver import extract_task_packet


VALID_PACKET = """protocol: lawb.local_runner.task_packet.v1
packet_id: task-138-read-only-validator
logical_issue: 138
phase: read_only_validator_implementation_slice_reviewbundle
action_type: read_only_audit
risk_level: low
repository: HarryWhite-TW/local-ai-workbench
branch: master
expected_head: 427b63c74f83e87aae0745f4ba28a83d2bf72c4d
allowed_files:
  - src/local_runner_bridge/__init__.py
forbidden_operations:
  - commit
approval:
  required: false
payload:
  kind: none
result_target:
  github_issue: 114
  marker: REVIEWBUNDLE-AUDIT-VISIBLE
stop_condition: stop_after_result_packet
"""


def surface(packet_text=VALID_PACKET):
    return (
        "LOCAL-RUNNER-TASK-PACKET-V1\n"
        "BEGIN_TASK_PACKET\n"
        f"{packet_text}"
        "END_TASK_PACKET\n"
    )


def test_valid_packet_returns_success_summary():
    extracted = extract_task_packet(surface())
    assert extracted["result"] == "success"

    summary = validate_task_packet(
        extracted["packet_text"],
        expected={
            "logical_issue": 138,
            "phase": "read_only_validator_implementation_slice_reviewbundle",
        },
    )

    assert summary["result"] == "success"
    assert summary["task_packet_protocol_valid"] is True
    assert summary["required_fields_present"] is True
    assert summary["codex_side_action_executed"] is False
    assert summary["result_packet_written"] is False
    assert summary["github_write_performed"] is False
    assert summary["commit_performed"] is False
    assert summary["push_performed"] is False


def test_embedded_boundary_marker_returns_blocked():
    text = (
        "LOCAL-RUNNER-TASK-PACKET-V1\n"
        "prefix BEGIN_TASK_PACKET suffix\n"
        f"{VALID_PACKET}"
        "END_TASK_PACKET\n"
    )

    summary = extract_task_packet(text)

    assert summary["result"] == "blocked"
    assert "begin_task_packet_missing" in summary["errors"]


def test_missing_or_non_string_surface_text_returns_blocked_summary():
    summary = extract_task_packet(None)

    assert summary["result"] == "blocked"
    assert "surface_text_not_string" in summary["errors"]
    assert summary["codex_side_action_executed"] is False


def test_missing_boundary_markers_returns_blocked():
    summary = extract_task_packet("LOCAL-RUNNER-TASK-PACKET-V1\nprotocol: x\n")

    assert summary["result"] == "blocked"
    assert "task_packet_boundary_markers_missing" in summary["errors"]


def test_multiple_active_task_packets_returns_blocked():
    text = surface() + surface()
    summary = extract_task_packet(text)

    assert summary["result"] == "blocked"
    assert summary["active_task_packet_count"] == 2
    assert "multiple_active_task_packets" in summary["errors"]


def test_valid_boundary_markers_may_be_indented_standalone_lines():
    text = (
        "  LOCAL-RUNNER-TASK-PACKET-V1\n"
        "  BEGIN_TASK_PACKET\n"
        f"{VALID_PACKET}"
        "  END_TASK_PACKET\n"
    )

    summary = extract_task_packet(text)

    assert summary["result"] == "success"
    assert summary["packet_text"] == VALID_PACKET.strip()


def test_invalid_protocol_returns_blocked():
    packet = VALID_PACKET.replace(
        "lawb.local_runner.task_packet.v1", "lawb.local_runner.task_packet.v0"
    )

    summary = validate_task_packet(packet)

    assert summary["result"] == "blocked"
    assert summary["task_packet_protocol_valid"] is False
    assert "invalid_task_packet_protocol" in summary["errors"]


def test_missing_required_fields_returns_blocked():
    packet = """protocol: lawb.local_runner.task_packet.v1
packet_id: task-138-read-only-validator
logical_issue: 138
phase: read_only_validator_implementation_slice_reviewbundle
"""

    summary = validate_task_packet(packet)

    assert summary["result"] == "blocked"
    assert summary["required_fields_present"] is False
    assert "required_fields_missing" in summary["errors"]
    assert "approval.required" in summary["missing_fields"]
    assert "result_target.github_issue" in summary["missing_fields"]


def test_unknown_top_level_field_returns_blocked():
    packet = VALID_PACKET + "unexpected_authority: true\n"

    summary = validate_task_packet(packet)

    assert summary["result"] == "blocked"
    assert "unknown_top_level_fields" in summary["errors"]
    assert summary["unknown_fields"] == ["unexpected_authority"]


def test_unknown_nested_field_does_not_count_as_unknown_top_level_field():
    packet = VALID_PACKET.replace(
        "  required: false\n", "  required: false\n  reviewer: chatgpt\n"
    )

    summary = validate_task_packet(packet)

    assert summary["result"] == "success"
    assert "unknown_top_level_fields" not in summary["errors"]


def test_scalar_allowed_files_returns_blocked():
    packet = VALID_PACKET.replace(
        "allowed_files:\n  - src/local_runner_bridge/__init__.py\n",
        "allowed_files: src/local_runner_bridge/__init__.py\n",
    )

    summary = validate_task_packet(packet)

    assert summary["result"] == "blocked"
    assert "invalid_list_fields" in summary["errors"]
    assert summary["invalid_list_fields"] == ["allowed_files"]


def test_scalar_forbidden_operations_returns_blocked():
    packet = VALID_PACKET.replace(
        "forbidden_operations:\n  - commit\n",
        "forbidden_operations: commit\n",
    )

    summary = validate_task_packet(packet)

    assert summary["result"] == "blocked"
    assert "invalid_list_fields" in summary["errors"]
    assert summary["invalid_list_fields"] == ["forbidden_operations"]


def test_empty_list_blocks_return_blocked():
    packet = VALID_PACKET.replace(
        "allowed_files:\n  - src/local_runner_bridge/__init__.py\n",
        "allowed_files:\n",
    ).replace(
        "forbidden_operations:\n  - commit\n",
        "forbidden_operations:\n",
    )

    summary = validate_task_packet(packet)

    assert summary["result"] == "blocked"
    assert "invalid_list_fields" in summary["errors"]
    assert summary["invalid_list_fields"] == [
        "allowed_files",
        "forbidden_operations",
    ]


def test_expected_logical_issue_mismatch_returns_blocked():
    summary = validate_task_packet(VALID_PACKET, expected={"logical_issue": 999})

    assert summary["result"] == "blocked"
    assert summary["logical_issue_matches_expected"] is False
    assert "logical_issue_mismatch" in summary["errors"]


def test_expected_phase_mismatch_returns_blocked():
    summary = validate_task_packet(VALID_PACKET, expected={"phase": "wrong_phase"})

    assert summary["result"] == "blocked"
    assert summary["phase_matches_expected"] is False
    assert "phase_mismatch" in summary["errors"]


def test_validation_success_does_not_authorize_execution_commit_or_push():
    summary = validate_task_packet(VALID_PACKET)

    assert summary["result"] == "success"
    assert summary["codex_side_action_executed"] is False
    assert summary["repo_files_modified"] is False
    assert summary["result_packet_written"] is False
    assert summary["github_write_performed"] is False
    assert summary["commit_performed"] is False
    assert summary["push_performed"] is False

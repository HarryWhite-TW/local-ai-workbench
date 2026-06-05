import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from local_runner_bridge.result_surface import REQUIRED_SAFETY_FLAGS
from local_runner_bridge.task_result_surface import (
    build_result_surface_from_task_surface_text,
)


VALID_PACKET = """protocol: lawb.local_runner.task_packet.v1
packet_id: task-162-result-surface-adapter
logical_issue: 162
phase: local_task_validation_to_result_surface_adapter_reviewbundle
action_type: read_only_audit
risk_level: low
repository: HarryWhite-TW/local-ai-workbench
branch: master
expected_head: babff5aa8d561bf195c3d8d18d4dc2e0b89f4706
allowed_files:
  - src/local_runner_bridge/task_result_surface.py
  - tests/local_runner_bridge/test_task_result_surface.py
forbidden_operations:
  - commit
  - push
approval:
  required: false
payload:
  kind: none
result_target:
  github_issue: 114
  marker: RESULT-SURFACE-ADAPTER-VISIBLE
stop_condition: stop_after_local_validation
"""


MINIMUM_FIELDS = {
    "result_surface_version",
    "result_id",
    "source_task_reference",
    "source_task_validation_result",
    "operation_mode",
    "status",
    "summary",
    "files_changed",
    "tests_run",
    "safety_flags",
    "blocked_reasons",
    "requires_user_approval",
    "next_recommended_step",
    "created_at",
}


def surface(packet_text=VALID_PACKET):
    return (
        "LOCAL-RUNNER-TASK-PACKET-V1\n"
        "BEGIN_TASK_PACKET\n"
        f"{packet_text}"
        "END_TASK_PACKET\n"
    )


def assert_no_write_or_action(result_surface):
    flags = result_surface["safety_flags"]
    assert set(flags) == set(REQUIRED_SAFETY_FLAGS)
    assert all(value is False for value in flags.values())


def test_valid_local_task_surface_text_produces_result_surface():
    result_surface = build_result_surface_from_task_surface_text(
        surface(),
        result_id="result-162-valid",
        created_at="2026-06-05T00:00:00Z",
    )

    assert result_surface["status"] == "success"
    assert result_surface["source_task_validation_result"]["result"] == "success"
    assert result_surface["blocked_reasons"] == []
    assert_no_write_or_action(result_surface)


def test_blocked_local_task_surface_text_still_produces_review_artifact():
    result_surface = build_result_surface_from_task_surface_text(
        "LOCAL-RUNNER-TASK-PACKET-V1\n",
        result_id="result-162-blocked",
        created_at="2026-06-05T00:00:00Z",
    )

    assert result_surface["status"] == "blocked"
    assert result_surface["source_task_validation_result"]["result"] == "blocked"
    assert "task_packet_boundary_markers_missing" in result_surface["blocked_reasons"]
    assert_no_write_or_action(result_surface)


def test_minimum_result_surface_fields_are_present():
    result_surface = build_result_surface_from_task_surface_text(surface())

    assert set(result_surface) == MINIMUM_FIELDS


def test_requires_user_approval_is_true():
    result_surface = build_result_surface_from_task_surface_text(surface())

    assert result_surface["requires_user_approval"] is True


def test_deterministic_result_id_and_created_at_can_be_injected():
    result_surface = build_result_surface_from_task_surface_text(
        surface(),
        result_id="result-deterministic",
        created_at="2026-06-05T00:00:00Z",
    )

    assert result_surface["result_id"] == "result-deterministic"
    assert result_surface["created_at"] == "2026-06-05T00:00:00Z"


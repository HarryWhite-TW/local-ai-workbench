import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from local_runner_bridge.explicit_fetch_result_surface import (
    build_result_surface_from_explicit_reference,
)
from local_runner_bridge.result_surface import REQUIRED_SAFETY_FLAGS


VALID_PACKET = """protocol: lawb.local_runner.task_packet.v1
packet_id: task-163-explicit-fetch-result-surface
logical_issue: 163
phase: explicit_fetch_to_result_surface_reviewbundle
action_type: read_only_audit
risk_level: low
repository: HarryWhite-TW/local-ai-workbench
branch: master
expected_head: 88f78c1a40aa93081d0078a3f055e5c8fe1778ed
allowed_files:
  - src/local_runner_bridge/explicit_fetch_result_surface.py
  - tests/local_runner_bridge/test_explicit_fetch_result_surface.py
forbidden_operations:
  - commit
  - push
approval:
  required: false
payload:
  kind: none
result_target:
  github_issue: 114
  marker: EXPLICIT-FETCH-RESULT-SURFACE-VISIBLE
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


def test_local_text_input_produces_result_surface_json():
    result_surface = build_result_surface_from_explicit_reference(
        local_text=surface(),
        result_id="result-163-local-text",
        created_at="2026-06-05T00:00:00Z",
    )

    assert result_surface["status"] == "success"
    assert result_surface["source_task_validation_result"]["result"] == "success"
    assert result_surface["requires_user_approval"] is True
    assert_no_write_or_action(result_surface)


def test_local_text_file_input_produces_result_surface_json(tmp_path):
    path = tmp_path / "surface.txt"
    path.write_text(surface(), encoding="utf-8")

    result_surface = build_result_surface_from_explicit_reference(
        local_text_file=str(path),
        result_id="result-163-local-file",
        created_at="2026-06-05T00:00:00Z",
    )

    assert result_surface["status"] == "success"
    assert result_surface["source_task_reference"]["kind"] == "local_text_file"
    assert_no_write_or_action(result_surface)


def test_explicit_issue_fetch_path_uses_stubbed_getter():
    calls = []

    def fake_get_json(url, token):
        calls.append((url, token))
        return {"body": surface()}

    result_surface = build_result_surface_from_explicit_reference(
        issue_url="https://github.com/HarryWhite-TW/local-ai-workbench/issues/163",
        http_get_json=fake_get_json,
        result_id="result-163-issue",
        created_at="2026-06-05T00:00:00Z",
    )

    assert result_surface["status"] == "success"
    assert calls == [
        (
            "https://api.github.com/repos/HarryWhite-TW/local-ai-workbench/issues/163",
            None,
        )
    ]
    assert_no_write_or_action(result_surface)


def test_explicit_comment_fetch_path_uses_stubbed_getter():
    calls = []

    def fake_get_json(url, token):
        calls.append((url, token))
        return {"body": surface()}

    result_surface = build_result_surface_from_explicit_reference(
        comment_url=(
            "https://github.com/HarryWhite-TW/local-ai-workbench/issues/163"
            "#issuecomment-123"
        ),
        http_get_json=fake_get_json,
    )

    assert result_surface["status"] == "success"
    assert calls == [
        (
            "https://api.github.com/repos/HarryWhite-TW/local-ai-workbench/"
            "issues/comments/123",
            None,
        )
    ]
    assert_no_write_or_action(result_surface)


def test_blocked_validation_still_produces_review_artifact():
    result_surface = build_result_surface_from_explicit_reference(
        local_text="LOCAL-RUNNER-TASK-PACKET-V1\nBEGIN_TASK_PACKET\nEND_TASK_PACKET\n"
    )

    assert result_surface["status"] == "blocked"
    assert result_surface["source_task_validation_result"]["result"] == "blocked"
    assert "validation_summary_not_success" in result_surface["blocked_reasons"]
    assert_no_write_or_action(result_surface)


def test_minimum_result_surface_fields_are_present():
    result_surface = build_result_surface_from_explicit_reference(local_text=surface())

    assert set(result_surface) == MINIMUM_FIELDS


def test_deterministic_result_id_and_created_at_can_be_injected():
    result_surface = build_result_surface_from_explicit_reference(
        local_text=surface(),
        result_id="result-deterministic",
        created_at="2026-06-05T00:00:00Z",
    )

    assert result_surface["result_id"] == "result-deterministic"
    assert result_surface["created_at"] == "2026-06-05T00:00:00Z"


def test_broad_or_ambiguous_references_are_rejected():
    broad = build_result_surface_from_explicit_reference(local_text="latest issue")
    ambiguous = build_result_surface_from_explicit_reference(
        local_text=surface(),
        issue_url="https://github.com/HarryWhite-TW/local-ai-workbench/issues/163",
    )

    assert broad["status"] == "blocked"
    assert "broad_reference_rejected" in broad["blocked_reasons"]
    assert ambiguous["status"] == "blocked"
    assert "multiple_inputs" in ambiguous["blocked_reasons"]


def test_issue_reference_without_stub_fails_closed_without_live_fetch():
    result_surface = build_result_surface_from_explicit_reference(
        issue_url="https://github.com/HarryWhite-TW/local-ai-workbench/issues/163"
    )

    assert result_surface["status"] == "blocked"
    assert "live_github_fetch_disabled_for_result_surface_adapter" in result_surface[
        "blocked_reasons"
    ]
    assert_no_write_or_action(result_surface)


import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from local_runner_bridge.readiness_gate import (
    validate_readiness_gate,
    validate_readiness_gate_json,
)


def valid_readiness_gate():
    return {
        "readiness_gate_version": "lawb.bounded_writeback_readiness_gate.v1.sample",
        "readiness_id": "readiness-189-local-validator",
        "source_task_reference": "task-189-local-readiness-gate-validator",
        "source_result_surface_id": "result-189-local-validator",
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


def assert_local_summary(summary):
    assert summary["protocol"] == (
        "lawb.writeback_readiness_gate_local_validation_summary.v1"
    )
    assert "validation_result" in summary
    assert "readiness_gate_version" in summary
    assert "readiness_id" in summary
    assert "source_task_reference" in summary
    assert "source_result_surface_id" in summary
    assert "writeback_target_reference" in summary
    assert "target_contract_validation_result" in summary
    assert "dry_run_preview_result" in summary
    assert "chatgpt_readback_completed" in summary
    assert "approval_record_validation_result" in summary
    assert "approved_write_mode" in summary
    assert "external_side_effect_allowed" in summary
    assert "real_write_mode_allowed" in summary
    assert "blocked_reasons" in summary
    assert "next_recommended_step" in summary
    assert summary["external_side_effect_allowed"] is False
    assert summary["real_write_mode_allowed"] is False
    assert summary["github_write_performed"] is False
    assert summary["result_packet_written"] is False
    assert summary["codex_side_action_executed"] is False
    assert summary["runner_invoked"] is False
    assert summary["dispatcher_invoked"] is False
    assert summary["watcher_invoked"] is False
    assert summary["commit_performed"] is False
    assert summary["push_performed"] is False


def assert_blocked(record, expected_reason):
    summary = validate_readiness_gate(record)

    assert summary["validation_result"] == "blocked"
    assert expected_reason in summary["blocked_reasons"]
    assert summary["external_side_effect_allowed"] is False
    assert summary["real_write_mode_allowed"] is False


def test_sample_dry_run_only_readiness_gate_record_returns_local_validation_summary():
    summary = validate_readiness_gate_json(json.dumps(valid_readiness_gate()))

    assert_local_summary(summary)
    assert summary["validation_result"] == "success"
    assert summary["readiness_id"] == "readiness-189-local-validator"
    assert summary["approved_write_mode"] == "dry_run_only"
    assert summary["external_side_effect_allowed"] is False
    assert summary["real_write_mode_allowed"] is False


def test_readiness_result_other_than_pass_causes_blocked_result():
    record = valid_readiness_gate()
    record["readiness_result"] = "blocked"

    assert_blocked(record, "readiness_result_not_pass")


def test_missing_source_task_reference_causes_blocked_result():
    record = valid_readiness_gate()
    del record["source_task_reference"]

    summary = validate_readiness_gate(record)

    assert summary["validation_result"] == "blocked"
    assert "required_fields_missing" in summary["blocked_reasons"]
    assert "source_task_reference_missing" in summary["blocked_reasons"]


def test_missing_source_result_surface_id_causes_blocked_result():
    record = valid_readiness_gate()
    del record["source_result_surface_id"]

    summary = validate_readiness_gate(record)

    assert summary["validation_result"] == "blocked"
    assert "required_fields_missing" in summary["blocked_reasons"]
    assert "source_result_surface_id_missing" in summary["blocked_reasons"]


def test_missing_writeback_target_reference_causes_blocked_result():
    record = valid_readiness_gate()
    del record["writeback_target_reference"]

    summary = validate_readiness_gate(record)

    assert summary["validation_result"] == "blocked"
    assert "required_fields_missing" in summary["blocked_reasons"]
    assert "writeback_target_reference_missing" in summary["blocked_reasons"]


def test_target_contract_validation_result_other_than_success_causes_blocked_result():
    record = valid_readiness_gate()
    record["target_contract_validation_result"] = "blocked"

    assert_blocked(record, "target_contract_validation_not_success")


def test_dry_run_preview_result_other_than_success_causes_blocked_result():
    record = valid_readiness_gate()
    record["dry_run_preview_result"] = "failed"

    assert_blocked(record, "dry_run_preview_not_success")


def test_approval_record_validation_result_other_than_success_causes_blocked_result():
    record = valid_readiness_gate()
    record["approval_record_validation_result"] = "blocked"

    assert_blocked(record, "approval_record_validation_not_success")


def test_chatgpt_readback_completed_false_causes_blocked_result():
    record = valid_readiness_gate()
    record["chatgpt_readback_completed"] = False

    assert_blocked(record, "chatgpt_readback_not_completed")


def test_approved_write_mode_other_than_dry_run_only_causes_blocked_result():
    record = valid_readiness_gate()
    record["approved_write_mode"] = "github_comment_write"

    assert_blocked(record, "approved_write_mode_not_allowed")


def test_external_side_effect_allowed_true_causes_blocked_result():
    record = valid_readiness_gate()
    record["external_side_effect_allowed"] = True

    assert_blocked(record, "external_side_effect_allowed_not_false")


def test_real_write_mode_allowed_true_causes_blocked_result():
    record = valid_readiness_gate()
    record["real_write_mode_allowed"] = True

    assert_blocked(record, "real_write_mode_allowed_not_false")


def test_multiple_targets_are_rejected():
    record = valid_readiness_gate()
    record["writeback_target_references"] = ["target-one", "target-two"]

    assert_blocked(record, "multiple_targets_present")


def test_inferred_target_is_rejected():
    record = valid_readiness_gate()
    record["writeback_target_reference"] = "latest issue"

    assert_blocked(record, "target_inferred_or_broad")


def test_broad_issue_scan_latest_issue_and_next_issue_inference_are_rejected():
    for requested in (
        "broad_issue_scan",
        "latest_issue",
        "next_issue",
        "next_latest_issue_inference",
    ):
        record = valid_readiness_gate()
        record["requested_actions"] = [requested]

        assert_blocked(record, "forbidden_action_requested")


def test_github_writeback_request_is_rejected():
    record = valid_readiness_gate()
    record["requested_actions"] = ["github_writeback_implementation"]

    assert_blocked(record, "forbidden_action_requested")


def test_result_packet_write_request_is_rejected():
    record = valid_readiness_gate()
    record["requested_actions"] = ["result_packet_write_implementation"]

    assert_blocked(record, "forbidden_action_requested")


def test_runner_dispatcher_watcher_requests_are_rejected():
    for requested in ("runner_behavior", "dispatcher_behavior", "watcher_behavior"):
        record = valid_readiness_gate()
        record["requested_actions"] = [requested]

        assert_blocked(record, "forbidden_action_requested")


def test_issue_close_label_change_pr_and_merge_requests_are_rejected():
    for requested in ("issue_close", "label_change", "pr_creation", "merge"):
        record = valid_readiness_gate()
        record["requested_actions"] = [requested]

        assert_blocked(record, "forbidden_action_requested")


def test_token_like_secret_values_are_blocked_and_not_leaked():
    record = valid_readiness_gate()
    record["source_task_reference"] = "github_pat_TEST_SECRET_DO_NOT_LEAK"

    summary = validate_readiness_gate(record)
    output = json.dumps(summary)

    assert summary["validation_result"] == "blocked"
    assert "token_value_detected" in summary["blocked_reasons"]
    assert "github_pat_TEST_SECRET_DO_NOT_LEAK" not in output


def test_external_side_effect_allowed_is_always_false_in_summary():
    success = validate_readiness_gate(valid_readiness_gate())
    blocked_record = valid_readiness_gate()
    blocked_record["external_side_effect_allowed"] = True
    blocked = validate_readiness_gate(blocked_record)

    assert success["external_side_effect_allowed"] is False
    assert blocked["external_side_effect_allowed"] is False


def test_real_write_mode_allowed_is_always_false_in_summary():
    success = validate_readiness_gate(valid_readiness_gate())
    blocked_record = valid_readiness_gate()
    blocked_record["real_write_mode_allowed"] = True
    blocked = validate_readiness_gate(blocked_record)

    assert success["real_write_mode_allowed"] is False
    assert blocked["real_write_mode_allowed"] is False


def test_input_readiness_gate_record_is_not_mutated():
    record = valid_readiness_gate()
    original = copy.deepcopy(record)

    validate_readiness_gate(record)

    assert record == original

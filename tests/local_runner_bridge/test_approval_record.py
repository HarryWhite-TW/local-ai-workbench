import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from local_runner_bridge.approval_record import (
    validate_approval_record,
    validate_approval_record_json,
)


FORBIDDEN_ACTIONS = [
    "github_writeback_implementation",
    "github_comment_write",
    "github_issue_body_update",
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
    "real_write_mode",
]


def valid_approval_record(target_type="github_issue_comment"):
    reference = (
        "https://github.com/HarryWhite-TW/local-ai-workbench/issues/114"
        "#future-approved-comment-target"
    )
    if target_type == "local_review_file":
        reference = ".local_review/writeback_target_preview.json"

    return {
        "approval_record_version": "lawb.writeback_approval_record.v1.sample",
        "approval_id": "approval-183-local-validator",
        "source_preview_id": "preview-183-local-validator",
        "source_result_surface_id": "result-183-local-validator",
        "source_task_reference": "task-183-local-approval-record-validator",
        "writeback_target_type": target_type,
        "writeback_target_reference": reference,
        "chatgpt_readback_completed": True,
        "approved_by_user": True,
        "approval_timestamp": "2026-06-06T00:00:00Z",
        "approved_write_mode": "dry_run_only",
        "allowed_next_step": "bounded_writeback_planning",
        "forbidden_actions": FORBIDDEN_ACTIONS.copy(),
        "external_side_effect_allowed": False,
        "created_at": "2026-06-06T00:00:00Z",
    }


def assert_local_summary(summary):
    assert summary["protocol"] == "lawb.approval_record_local_validation_summary.v1"
    assert "validation_result" in summary
    assert "approval_record_version" in summary
    assert "approval_id" in summary
    assert "source_preview_id" in summary
    assert "source_result_surface_id" in summary
    assert "source_task_reference" in summary
    assert "writeback_target_type" in summary
    assert "writeback_target_reference" in summary
    assert "chatgpt_readback_gate_satisfied" in summary
    assert "user_approval_gate_satisfied" in summary
    assert "approved_write_mode" in summary
    assert "external_side_effect_allowed" in summary
    assert "blocked_reasons" in summary
    assert "next_recommended_step" in summary
    assert summary["external_side_effect_allowed"] is False
    assert summary["github_write_performed"] is False
    assert summary["result_packet_written"] is False
    assert summary["codex_side_action_executed"] is False
    assert summary["runner_invoked"] is False
    assert summary["dispatcher_invoked"] is False
    assert summary["watcher_invoked"] is False
    assert summary["commit_performed"] is False
    assert summary["push_performed"] is False


def test_sample_dry_run_only_approval_record_returns_local_validation_summary():
    summary = validate_approval_record_json(json.dumps(valid_approval_record()))

    assert_local_summary(summary)
    assert summary["validation_result"] == "success"
    assert summary["writeback_target_type"] == "github_issue_comment"
    assert summary["chatgpt_readback_gate_satisfied"] is True
    assert summary["user_approval_gate_satisfied"] is True
    assert summary["approved_write_mode"] == "dry_run_only"


def test_sample_local_review_file_approval_record_returns_summary():
    summary = validate_approval_record(valid_approval_record(target_type="local_review_file"))

    assert_local_summary(summary)
    assert summary["validation_result"] == "success"
    assert summary["writeback_target_type"] == "local_review_file"


def test_approved_by_user_false_causes_blocked_result():
    record = valid_approval_record()
    record["approved_by_user"] = False

    summary = validate_approval_record(record)

    assert summary["validation_result"] == "blocked"
    assert summary["user_approval_gate_satisfied"] is False
    assert "user_approval_gate_not_satisfied" in summary["blocked_reasons"]


def test_chatgpt_readback_completed_false_causes_blocked_result():
    record = valid_approval_record()
    record["chatgpt_readback_completed"] = False

    summary = validate_approval_record(record)

    assert summary["validation_result"] == "blocked"
    assert summary["chatgpt_readback_gate_satisfied"] is False
    assert "chatgpt_readback_gate_not_satisfied" in summary["blocked_reasons"]


def test_missing_source_preview_id_causes_blocked_result():
    record = valid_approval_record()
    del record["source_preview_id"]

    summary = validate_approval_record(record)

    assert summary["validation_result"] == "blocked"
    assert "required_fields_missing" in summary["blocked_reasons"]
    assert "source_preview_id_missing" in summary["blocked_reasons"]


def test_missing_writeback_target_reference_causes_blocked_result():
    record = valid_approval_record()
    del record["writeback_target_reference"]

    summary = validate_approval_record(record)

    assert summary["validation_result"] == "blocked"
    assert "required_fields_missing" in summary["blocked_reasons"]
    assert "writeback_target_reference_missing" in summary["blocked_reasons"]


def test_approved_write_mode_other_than_dry_run_only_causes_blocked_result():
    record = valid_approval_record()
    record["approved_write_mode"] = "github_comment_write"

    summary = validate_approval_record(record)

    assert summary["validation_result"] == "blocked"
    assert "approved_write_mode_not_allowed" in summary["blocked_reasons"]


def test_external_side_effect_allowed_true_causes_blocked_result():
    record = valid_approval_record()
    record["external_side_effect_allowed"] = True

    summary = validate_approval_record(record)

    assert summary["validation_result"] == "blocked"
    assert "external_side_effect_allowed_not_false" in summary["blocked_reasons"]
    assert summary["external_side_effect_allowed"] is False


def test_multiple_targets_are_rejected():
    record = valid_approval_record()
    record["writeback_target_references"] = ["target-one", "target-two"]

    summary = validate_approval_record(record)

    assert summary["validation_result"] == "blocked"
    assert "multiple_targets_present" in summary["blocked_reasons"]


def test_inferred_target_is_rejected():
    record = valid_approval_record()
    record["writeback_target_reference"] = "latest issue"

    summary = validate_approval_record(record)

    assert summary["validation_result"] == "blocked"
    assert "target_inferred_or_broad" in summary["blocked_reasons"]


def test_approval_inferred_from_commit_push_validation_or_dry_run_success_is_rejected():
    for inference in (
        "previous conversation",
        "commit_success",
        "push_success",
        "validation_success",
        "dry_run_preview_success",
    ):
        record = valid_approval_record()
        record["approval_basis"] = inference

        summary = validate_approval_record(record)

        assert summary["validation_result"] == "blocked"
        assert (
            "approval_inferred_from_evidence_or_conversation"
            in summary["blocked_reasons"]
        )


def test_github_writeback_approval_request_is_rejected():
    record = valid_approval_record()
    record["requested_actions"] = ["github_writeback_implementation"]

    summary = validate_approval_record(record)

    assert summary["validation_result"] == "blocked"
    assert "forbidden_action_requested" in summary["blocked_reasons"]


def test_result_packet_write_approval_request_is_rejected():
    record = valid_approval_record()
    record["requested_actions"] = ["result_packet_write_implementation"]

    summary = validate_approval_record(record)

    assert summary["validation_result"] == "blocked"
    assert "forbidden_action_requested" in summary["blocked_reasons"]


def test_runner_dispatcher_watcher_approval_requests_are_rejected():
    for requested in ("runner_behavior", "dispatcher_behavior", "watcher_behavior"):
        record = valid_approval_record()
        record["requested_actions"] = [requested]

        summary = validate_approval_record(record)

        assert summary["validation_result"] == "blocked"
        assert "forbidden_action_requested" in summary["blocked_reasons"]


def test_issue_close_label_change_pr_and_merge_approval_requests_are_rejected():
    for requested in ("issue_close", "label_change", "pr_creation", "merge"):
        record = valid_approval_record()
        record["requested_actions"] = [requested]

        summary = validate_approval_record(record)

        assert summary["validation_result"] == "blocked"
        assert "forbidden_action_requested" in summary["blocked_reasons"]


def test_token_like_secret_values_are_blocked_and_not_leaked():
    record = valid_approval_record()
    record["source_preview_id"] = "github_pat_TEST_SECRET_DO_NOT_LEAK"

    summary = validate_approval_record(record)
    output = json.dumps(summary)

    assert summary["validation_result"] == "blocked"
    assert "token_value_detected" in summary["blocked_reasons"]
    assert "github_pat_TEST_SECRET_DO_NOT_LEAK" not in output


def test_external_side_effect_allowed_is_always_false_in_summary():
    success = validate_approval_record(valid_approval_record())
    blocked_record = valid_approval_record()
    blocked_record["external_side_effect_allowed"] = True
    blocked = validate_approval_record(blocked_record)

    assert success["external_side_effect_allowed"] is False
    assert blocked["external_side_effect_allowed"] is False


def test_input_approval_record_is_not_mutated():
    record = valid_approval_record()
    original = copy.deepcopy(record)

    validate_approval_record(record)

    assert record == original

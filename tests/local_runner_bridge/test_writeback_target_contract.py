import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from local_runner_bridge.writeback_target_contract import (
    validate_writeback_target_contract,
    validate_writeback_target_contract_json,
)


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


def valid_contract(target_type="github_issue_comment"):
    reference = (
        "https://github.com/HarryWhite-TW/local-ai-workbench/issues/114"
        "#future-approved-comment-target"
    )
    if target_type == "local_review_file":
        reference = ".local_review/writeback_target_preview.json"

    return {
        "contract_version": "lawb.writeback_target_contract.v0.sample",
        "writeback_target_type": target_type,
        "writeback_target_reference": reference,
        "source_result_surface_id": "result-172-local-validator",
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


def assert_local_summary(summary):
    assert summary["protocol"] == "lawb.writeback_target_contract_local_validation_summary.v1"
    assert "validation_result" in summary
    assert "contract_version" in summary
    assert "writeback_target_type" in summary
    assert "writeback_target_reference" in summary
    assert "required_fields_present" in summary
    assert "approval_gate_satisfied" in summary
    assert "chatgpt_readback_gate_satisfied" in summary
    assert "dry_run_required" in summary
    assert "forbidden_actions_present" in summary
    assert "blocked_reasons" in summary
    assert summary["external_side_effect_allowed"] is False
    assert summary["github_write_performed"] is False
    assert summary["result_packet_written"] is False
    assert summary["codex_side_action_executed"] is False
    assert summary["commit_performed"] is False
    assert summary["push_performed"] is False


def test_sample_dry_run_only_github_issue_comment_contract_returns_summary():
    summary = validate_writeback_target_contract_json(json.dumps(valid_contract()))

    assert_local_summary(summary)
    assert summary["validation_result"] == "success"
    assert summary["writeback_target_type"] == "github_issue_comment"
    assert summary["required_fields_present"] is True
    assert summary["approval_gate_satisfied"] is True
    assert summary["chatgpt_readback_gate_satisfied"] is True


def test_sample_local_review_file_target_contract_returns_summary():
    summary = validate_writeback_target_contract(
        valid_contract(target_type="local_review_file")
    )

    assert_local_summary(summary)
    assert summary["validation_result"] == "success"
    assert summary["writeback_target_type"] == "local_review_file"


def test_approved_by_user_false_causes_blocked_result():
    contract = valid_contract()
    contract["approved_by_user"] = False

    summary = validate_writeback_target_contract(contract)

    assert summary["validation_result"] == "blocked"
    assert summary["approval_gate_satisfied"] is False
    assert "approval_gate_not_satisfied" in summary["blocked_reasons"]


def test_chatgpt_readback_completed_false_causes_blocked_result():
    contract = valid_contract()
    contract["chatgpt_readback_completed"] = False

    summary = validate_writeback_target_contract(contract)

    assert summary["validation_result"] == "blocked"
    assert summary["chatgpt_readback_gate_satisfied"] is False
    assert "chatgpt_readback_gate_not_satisfied" in summary["blocked_reasons"]


def test_missing_required_fields_cause_blocked_result():
    contract = valid_contract()
    del contract["source_result_surface_id"]

    summary = validate_writeback_target_contract(contract)

    assert summary["validation_result"] == "blocked"
    assert summary["required_fields_present"] is False
    assert "required_fields_missing" in summary["blocked_reasons"]
    assert summary["missing_fields"] == ["source_result_surface_id"]


def test_write_mode_other_than_dry_run_only_causes_blocked_result():
    contract = valid_contract()
    contract["write_mode"] = "approved_single_write"

    summary = validate_writeback_target_contract(contract)

    assert summary["validation_result"] == "blocked"
    assert "write_mode_not_allowed" in summary["blocked_reasons"]


def test_missing_forbidden_actions_causes_blocked_result():
    contract = valid_contract()
    del contract["forbidden_actions"]

    summary = validate_writeback_target_contract(contract)

    assert summary["validation_result"] == "blocked"
    assert summary["forbidden_actions_present"] is False
    assert "required_fields_missing" in summary["blocked_reasons"]
    assert "forbidden_actions_missing" in summary["blocked_reasons"]


def test_broad_scan_target_is_rejected():
    contract = valid_contract()
    contract["writeback_target_type"] = "broad_issue_scan"

    summary = validate_writeback_target_contract(contract)

    assert summary["validation_result"] == "blocked"
    assert "writeback_target_type_not_allowed" in summary["blocked_reasons"]
    assert "disallowed_target_type" in summary["blocked_reasons"]


def test_latest_and_next_issue_inference_targets_are_rejected():
    latest = valid_contract()
    latest["writeback_target_reference"] = "latest issue"
    next_issue = valid_contract()
    next_issue["writeback_target_reference"] = "next issue"

    latest_summary = validate_writeback_target_contract(latest)
    next_summary = validate_writeback_target_contract(next_issue)

    assert latest_summary["validation_result"] == "blocked"
    assert next_summary["validation_result"] == "blocked"
    assert "target_inferred_or_broad" in latest_summary["blocked_reasons"]
    assert "target_inferred_or_broad" in next_summary["blocked_reasons"]


def test_issue_close_label_change_pr_and_merge_targets_are_rejected():
    for target_type in ("issue_close", "label_change", "pull_request", "merge"):
        contract = valid_contract()
        contract["writeback_target_type"] = target_type

        summary = validate_writeback_target_contract(contract)

        assert summary["validation_result"] == "blocked"
        assert "writeback_target_type_not_allowed" in summary["blocked_reasons"]
        assert "disallowed_target_type" in summary["blocked_reasons"]


def test_issue_close_label_change_pr_and_merge_requested_actions_are_rejected():
    for action in ("issue_close", "label_change", "pr_creation", "merge"):
        contract = valid_contract()
        contract["requested_actions"] = [action]

        summary = validate_writeback_target_contract(contract)

        assert summary["validation_result"] == "blocked"
        assert "forbidden_action_requested" in summary["blocked_reasons"]


def test_multiple_targets_are_rejected():
    contract = valid_contract()
    contract["writeback_target_references"] = [
        "https://github.com/HarryWhite-TW/local-ai-workbench/issues/114#one",
        "https://github.com/HarryWhite-TW/local-ai-workbench/issues/115#two",
    ]

    summary = validate_writeback_target_contract(contract)

    assert summary["validation_result"] == "blocked"
    assert "multiple_targets_present" in summary["blocked_reasons"]


def test_token_like_secret_values_in_contract_fields_are_blocked():
    contract = valid_contract()
    contract["source_result_surface_id"] = "ghp_TEST_SECRET_DO_NOT_LEAK"

    summary = validate_writeback_target_contract(contract)

    assert summary["validation_result"] == "blocked"
    assert "token_value_detected" in summary["blocked_reasons"]
    assert "ghp_TEST_SECRET_DO_NOT_LEAK" not in json.dumps(summary)


def test_external_side_effect_allowed_is_always_false():
    success = validate_writeback_target_contract(valid_contract())
    blocked_contract = valid_contract()
    blocked_contract["writeback_target_type"] = "latest_issue"
    blocked = validate_writeback_target_contract(blocked_contract)

    assert success["external_side_effect_allowed"] is False
    assert blocked["external_side_effect_allowed"] is False


def test_input_contract_is_not_mutated():
    contract = valid_contract()
    original = copy.deepcopy(contract)

    validate_writeback_target_contract(contract)

    assert contract == original

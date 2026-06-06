import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from local_runner_bridge.writeback_dry_run_preview import (
    build_writeback_dry_run_preview,
)
from local_runner_bridge.writeback_target_contract import (
    validate_writeback_target_contract,
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
        "source_result_surface_id": "result-177-builder",
        "source_task_reference": "task-177-writeback-dry-run-preview-builder",
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


def result_surface_summary():
    return {
        "result_surface_version": "lawb.local_result_surface.v1.sample",
        "result_id": "result-177-builder",
        "source_task_reference": "task-177-writeback-dry-run-preview-builder",
        "status": "success",
        "summary": "Local result surface summary for preview building.",
    }


def validation_summary(contract=None):
    return validate_writeback_target_contract(contract or valid_contract())


def build_preview(contract=None, summary=None, preview_content="Dry-run preview body."):
    contract = contract or valid_contract()
    summary = validation_summary(contract) if summary is None else summary
    return build_writeback_dry_run_preview(
        contract,
        summary,
        result_surface_summary(),
        preview_content,
        preview_id="preview-177-test",
        created_at="2026-06-06T00:00:00Z",
    )


def assert_no_side_effects(preview):
    assert preview["external_side_effect_allowed"] is False
    assert preview["safety_flags"]["external_side_effect_allowed"] is False
    assert preview["safety_flags"]["github_write_performed"] is False
    assert preview["safety_flags"]["result_packet_written"] is False
    assert preview["safety_flags"]["codex_side_action_executed"] is False
    assert preview["safety_flags"]["runner_invoked"] is False
    assert preview["safety_flags"]["dispatcher_invoked"] is False
    assert preview["safety_flags"]["watcher_invoked"] is False
    assert preview["safety_flags"]["pr_created"] is False
    assert preview["safety_flags"]["merge_performed"] is False
    assert preview["safety_flags"]["issue_closed"] is False
    assert preview["safety_flags"]["label_changed"] is False


def test_valid_dry_run_only_github_issue_comment_target_contract_produces_preview_json():
    preview = build_preview()

    assert preview["result"] == "success"
    assert preview["preview_version"] == "lawb.writeback_dry_run_preview.v1"
    assert preview["writeback_target_type"] == "github_issue_comment"
    assert preview["contract_validation_result"] == "success"
    assert preview["write_mode"] == "dry_run_only"
    assert preview["requires_chatgpt_readback"] is True
    assert preview["requires_user_approval"] is True
    assert preview["blocked_reasons"] == []
    assert_no_side_effects(preview)
    json.dumps(preview)


def test_valid_local_review_file_target_contract_produces_preview_json():
    contract = valid_contract(target_type="local_review_file")

    preview = build_preview(contract=contract)

    assert preview["result"] == "success"
    assert preview["writeback_target_type"] == "local_review_file"
    assert preview["writeback_target_reference"] == ".local_review/writeback_target_preview.json"
    assert_no_side_effects(preview)


def test_failed_contract_validation_produces_blocked_preview():
    contract = valid_contract()
    summary = validation_summary(contract)
    summary["validation_result"] = "blocked"

    preview = build_preview(contract=contract, summary=summary)

    assert preview["result"] == "blocked"
    assert "contract_validation_failed" in preview["blocked_reasons"]


def test_missing_contract_validation_summary_produces_blocked_preview():
    preview = build_writeback_dry_run_preview(
        valid_contract(),
        None,
        result_surface_summary(),
        "Dry-run preview body.",
        preview_id="preview-177-test",
        created_at="2026-06-06T00:00:00Z",
    )

    assert preview["result"] == "blocked"
    assert "contract_validation_summary_missing" in preview["blocked_reasons"]


def test_write_mode_other_than_dry_run_only_is_blocked():
    contract = valid_contract()
    contract["write_mode"] = "approved_single_write"

    preview = build_preview(contract=contract, summary={"validation_result": "success", "external_side_effect_allowed": False})

    assert preview["result"] == "blocked"
    assert preview["write_mode"] == "dry_run_only"
    assert "write_mode_not_allowed" in preview["blocked_reasons"]


def test_external_side_effect_allowed_is_always_false():
    success = build_preview()
    blocked = build_preview(summary=None)

    assert success["external_side_effect_allowed"] is False
    assert blocked["external_side_effect_allowed"] is False


def test_requires_chatgpt_readback_is_true():
    preview = build_preview()

    assert preview["requires_chatgpt_readback"] is True


def test_requires_user_approval_is_true():
    preview = build_preview()

    assert preview["requires_user_approval"] is True


def test_deterministic_preview_id_and_created_at_can_be_injected():
    preview = build_preview()

    assert preview["preview_id"] == "preview-177-test"
    assert preview["created_at"] == "2026-06-06T00:00:00Z"


def test_forbidden_actions_are_preserved():
    preview = build_preview()

    assert preview["forbidden_actions"] == FORBIDDEN_ACTIONS


def test_token_like_values_in_preview_input_are_blocked_and_not_leaked():
    preview = build_preview(preview_content="ghp_TEST_SECRET_DO_NOT_LEAK")
    output = json.dumps(preview)

    assert preview["result"] == "blocked"
    assert "token_value_detected" in preview["blocked_reasons"]
    assert "ghp_TEST_SECRET_DO_NOT_LEAK" not in output


def test_github_writeback_request_is_blocked():
    contract = valid_contract()
    contract["requested_actions"] = ["github_writeback_implementation"]

    preview = build_preview(contract=contract)

    assert preview["result"] == "blocked"
    assert "forbidden_action_requested" in preview["blocked_reasons"]


def test_result_packet_write_request_is_blocked():
    contract = valid_contract()
    contract["requested_actions"] = ["result_packet_write_implementation"]

    preview = build_preview(contract=contract)

    assert preview["result"] == "blocked"
    assert "forbidden_action_requested" in preview["blocked_reasons"]


def test_runner_dispatcher_watcher_requests_are_blocked():
    for requested in ("runner_behavior", "dispatcher_behavior", "watcher_behavior"):
        contract = valid_contract()
        contract["requested_actions"] = [requested]

        preview = build_preview(contract=contract)

        assert preview["result"] == "blocked"
        assert "forbidden_action_requested" in preview["blocked_reasons"]


def test_issue_close_label_change_pr_and_merge_requests_are_blocked():
    for requested in ("issue_close", "label_change", "pr_creation", "merge"):
        contract = valid_contract()
        contract["requested_actions"] = [requested]

        preview = build_preview(contract=contract)

        assert preview["result"] == "blocked"
        assert "forbidden_action_requested" in preview["blocked_reasons"]


def test_multiple_targets_are_blocked():
    contract = valid_contract()
    contract["writeback_target_references"] = ["target-one", "target-two"]

    preview = build_preview(contract=contract)

    assert preview["result"] == "blocked"
    assert "multiple_targets_present" in preview["blocked_reasons"]


def test_inferred_target_is_blocked():
    contract = valid_contract()
    contract["writeback_target_reference"] = "latest issue"

    preview = build_preview(contract=contract)

    assert preview["result"] == "blocked"
    assert "target_inferred_or_broad" in preview["blocked_reasons"]

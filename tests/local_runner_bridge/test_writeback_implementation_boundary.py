from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from local_runner_bridge.writeback_implementation_boundary import (  # noqa: E402
    REAL_WRITE_INDICATORS,
    validate_writeback_implementation_boundary,
    validate_writeback_implementation_boundary_json,
)


def valid_boundary_record() -> dict[str, object]:
    real_write_indicators = {field: False for field in REAL_WRITE_INDICATORS}
    return {
        "boundary_version": "lawb.bounded_writeback_implementation_boundary.v1.sample",
        "boundary_id": "boundary-195-local-validator",
        "future_candidate_issue": 195,
        "future_risk_lane_required": "strict",
        "first_possible_writeback_type": "github_issue_comment",
        "allowed_target_type": "explicit_single_github_issue_comment",
        "allowed_target_reference_mode": "explicit_only",
        "source_readiness_id": "readiness-195-local-validator",
        "source_preview_id": "preview-195-local-validator",
        "source_result_surface_id": "result-195-local-validator",
        "required_preconditions": {
            "explicit_user_approval_required": True,
            "explicit_single_target_required": True,
        },
        "required_runtime_gates": {
            "writeback_target_count": 1,
            "broad_issue_scan": False,
            "next_latest_issue_inference_requested": False,
        },
        "forbidden_scope": {
            "github_issue_body_update": True,
            "result_packet_write": True,
            "runner_behavior": True,
            "dispatcher_behavior": True,
            "watcher_behavior": True,
            "approval_chaining": True,
        },
        "future_audit_shape": {
            **real_write_indicators,
            "writeback_target_reference": (
                "https://github.com/HarryWhite-TW/local-ai-workbench/"
                "issues/114#future-approved-comment-target"
            ),
            "approved_write_mode": "dry_run_only",
        },
        "real_write_indicators": real_write_indicators,
        "implementation_allowed_now": False,
        "writeback_allowed_now": False,
        "result_packet_write_allowed_now": False,
        "runner_dispatcher_watcher_allowed_now": False,
        "next_recommended_step": (
            "local_writeback_implementation_boundary_validator_candidate"
        ),
        "created_at": "2026-06-06T00:00:00Z",
    }


def test_valid_boundary_json_returns_success_summary() -> None:
    summary = validate_writeback_implementation_boundary_json(
        json.dumps(valid_boundary_record())
    )

    assert summary["validation_result"] == "success"
    assert summary["boundary_id"] == "boundary-195-local-validator"
    assert summary["future_candidate_issue"] == 195
    assert summary["future_risk_lane_required"] == "strict"
    assert summary["first_possible_writeback_type"] == "github_issue_comment"
    assert summary["allowed_target_type"] == "explicit_single_github_issue_comment"
    assert summary["allowed_target_reference_mode"] == "explicit_only"
    assert summary["real_write_indicators_all_false"] is True
    assert summary["github_comment_written"] is False
    assert summary["result_packet_written"] is False
    assert summary["runner_invoked"] is False
    assert summary["dispatcher_invoked"] is False
    assert summary["watcher_invoked"] is False


def test_validation_does_not_mutate_input() -> None:
    record = valid_boundary_record()
    original = copy.deepcopy(record)

    validate_writeback_implementation_boundary(record)

    assert record == original


def test_blocks_non_strict_risk_lane() -> None:
    record = valid_boundary_record()
    record["future_risk_lane_required"] = "standard"

    summary = validate_writeback_implementation_boundary(record)

    assert summary["validation_result"] == "blocked"
    assert "future_risk_lane_required_not_strict" in summary["blocked_reasons"]


def test_blocks_invalid_first_possible_writeback_type() -> None:
    record = valid_boundary_record()
    record["first_possible_writeback_type"] = "github_issue_body_update"

    summary = validate_writeback_implementation_boundary(record)

    assert "first_possible_writeback_type_not_allowed" in summary["blocked_reasons"]


def test_blocks_invalid_target_type() -> None:
    record = valid_boundary_record()
    record["allowed_target_type"] = "latest_github_issue"

    summary = validate_writeback_implementation_boundary(record)

    assert "allowed_target_type_not_allowed" in summary["blocked_reasons"]


def test_blocks_invalid_target_reference_mode() -> None:
    record = valid_boundary_record()
    record["allowed_target_reference_mode"] = "latest_issue"

    summary = validate_writeback_implementation_boundary(record)

    assert "allowed_target_reference_mode_not_explicit_only" in summary[
        "blocked_reasons"
    ]


def test_blocks_allowed_now_flags() -> None:
    cases = [
        ("implementation_allowed_now", "implementation_allowed_now_not_false"),
        ("writeback_allowed_now", "writeback_allowed_now_not_false"),
        (
            "result_packet_write_allowed_now",
            "result_packet_write_allowed_now_not_false",
        ),
        (
            "runner_dispatcher_watcher_allowed_now",
            "runner_dispatcher_watcher_allowed_now_not_false",
        ),
    ]
    for field, reason in cases:
        record = valid_boundary_record()
        record[field] = True

        summary = validate_writeback_implementation_boundary(record)

        assert summary["validation_result"] == "blocked"
        assert reason in summary["blocked_reasons"]


def test_blocks_each_real_write_indicator_true() -> None:
    for indicator in REAL_WRITE_INDICATORS:
        record = valid_boundary_record()
        record["real_write_indicators"][indicator] = True  # type: ignore[index]

        summary = validate_writeback_implementation_boundary(record)

        assert summary["validation_result"] == "blocked"
        assert f"{indicator}_not_false" in summary["blocked_reasons"]
        assert summary["real_write_indicators_all_false"] is False


def test_blocks_missing_real_write_indicator() -> None:
    record = valid_boundary_record()
    del record["real_write_indicators"]["writeback_attempted"]  # type: ignore[index]
    del record["future_audit_shape"]["writeback_attempted"]  # type: ignore[index]

    summary = validate_writeback_implementation_boundary(record)

    assert summary["validation_result"] == "blocked"
    assert "real_write_indicators_not_all_false" in summary["blocked_reasons"]


def test_blocks_multiple_targets() -> None:
    record = valid_boundary_record()
    record["writeback_target_references"] = [
        "https://github.com/example/repo/issues/1#issuecomment-1",
        "https://github.com/example/repo/issues/1#issuecomment-2",
    ]

    summary = validate_writeback_implementation_boundary(record)

    assert "multiple_targets_present" in summary["blocked_reasons"]


def test_blocks_inferred_target_reference() -> None:
    record = valid_boundary_record()
    record["future_audit_shape"]["writeback_target_reference"] = "latest issue"  # type: ignore[index]

    summary = validate_writeback_implementation_boundary(record)

    assert "target_inferred_or_broad" in summary["blocked_reasons"]


def test_blocks_broad_scan_and_next_latest_issue_request() -> None:
    record = valid_boundary_record()
    record["requested_actions"] = [
        "perform broad issue scan",
        "infer latest issue target",
    ]

    summary = validate_writeback_implementation_boundary(record)

    assert "forbidden_action_requested" in summary["blocked_reasons"]


def test_blocks_token_like_values_and_does_not_leak_them() -> None:
    record = valid_boundary_record()
    record["source_preview_id"] = "github_pat_TEST_SECRET_DO_NOT_LEAK"

    summary = validate_writeback_implementation_boundary(record)
    serialized = json.dumps(summary, sort_keys=True)

    assert "token_value_detected" in summary["blocked_reasons"]
    assert "github_pat_TEST_SECRET_DO_NOT_LEAK" not in serialized
    assert "[REDACTED]" in serialized


def test_blocks_non_object_and_invalid_json() -> None:
    assert validate_writeback_implementation_boundary([])["validation_result"] == "blocked"
    assert validate_writeback_implementation_boundary_json("{")[
        "validation_result"
    ] == "blocked"


def test_blocks_missing_required_fields() -> None:
    record = valid_boundary_record()
    del record["boundary_id"]

    summary = validate_writeback_implementation_boundary(record)

    assert "required_fields_missing" in summary["blocked_reasons"]
    assert summary["required_fields_present"] is False

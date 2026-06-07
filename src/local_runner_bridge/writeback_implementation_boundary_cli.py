"""CLI for local-only Writeback Implementation Boundary validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .writeback_implementation_boundary import (
    SUMMARY_PROTOCOL,
    validate_writeback_implementation_boundary_json,
)


def _blocked_summary(reason: str) -> dict[str, object]:
    return {
        "protocol": SUMMARY_PROTOCOL,
        "result": "blocked",
        "validation_result": "blocked",
        "boundary_version": None,
        "boundary_id": None,
        "future_candidate_issue": None,
        "future_risk_lane_required": None,
        "first_possible_writeback_type": None,
        "allowed_target_type": None,
        "allowed_target_reference_mode": None,
        "implementation_allowed_now": None,
        "writeback_allowed_now": None,
        "result_packet_write_allowed_now": None,
        "runner_dispatcher_watcher_allowed_now": None,
        "required_fields_present": False,
        "real_write_indicators_all_false": False,
        "blocked_reasons": [reason],
        "github_write_performed": False,
        "github_comment_written": False,
        "github_issue_body_updated": False,
        "result_packet_written": False,
        "codex_side_action_executed": False,
        "runner_invoked": False,
        "dispatcher_invoked": False,
        "watcher_invoked": False,
        "broad_scan_performed": False,
        "next_latest_issue_inference_performed": False,
        "commit_performed": False,
        "push_performed": False,
        "pr_created": False,
        "merge_performed": False,
        "issue_closed": False,
        "label_changed": False,
        "next_recommended_step": "chatgpt_review",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate one local writeback implementation boundary JSON file."
    )
    parser.add_argument("--boundary-file", required=True)
    args = parser.parse_args(argv)

    try:
        boundary_json = Path(args.boundary_file).read_text(encoding="utf-8")
    except OSError:
        print(
            json.dumps(
                _blocked_summary("boundary_file_read_failed"),
                sort_keys=True,
            )
        )
        return 2

    summary = validate_writeback_implementation_boundary_json(boundary_json)
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary.get("validation_result") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())

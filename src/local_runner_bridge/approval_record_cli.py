"""Local-only CLI for bounded Writeback Approval Record validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from local_runner_bridge.approval_record import validate_approval_record_json


def _blocked_summary(reason: str) -> dict:
    return {
        "protocol": "lawb.approval_record_local_validation_summary.v1",
        "result": "blocked",
        "validation_result": "blocked",
        "approval_record_version": None,
        "approval_id": None,
        "source_preview_id": None,
        "source_result_surface_id": None,
        "source_task_reference": None,
        "writeback_target_type": None,
        "writeback_target_reference": None,
        "required_fields_present": False,
        "chatgpt_readback_gate_satisfied": False,
        "user_approval_gate_satisfied": False,
        "approved_write_mode": None,
        "forbidden_actions_present": False,
        "external_side_effect_allowed": False,
        "blocked_reasons": [reason],
        "github_write_performed": False,
        "result_packet_written": False,
        "codex_side_action_executed": False,
        "runner_invoked": False,
        "dispatcher_invoked": False,
        "watcher_invoked": False,
        "commit_performed": False,
        "push_performed": False,
        "next_recommended_step": "chatgpt_review",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--approval-record-file", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Read one local approval record file and print validation JSON."""
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        print(json.dumps(_blocked_summary("invalid_arguments"), sort_keys=True))
        return 2

    try:
        approval_record_json = Path(args.approval_record_file).read_text(encoding="utf-8")
    except OSError as error:
        summary = _blocked_summary(
            f"approval_record_file_read_failed:{type(error).__name__}"
        )
        print(json.dumps(summary, sort_keys=True))
        return 0

    summary = validate_approval_record_json(approval_record_json)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

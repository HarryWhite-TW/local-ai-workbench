"""Local-only CLI for Writeback Readiness Gate validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from local_runner_bridge.readiness_gate import validate_readiness_gate_json


def _blocked_summary(reason: str) -> dict:
    return {
        "protocol": "lawb.writeback_readiness_gate_local_validation_summary.v1",
        "result": "blocked",
        "validation_result": "blocked",
        "readiness_gate_version": None,
        "readiness_id": None,
        "source_task_reference": None,
        "source_result_surface_id": None,
        "writeback_target_reference": None,
        "target_contract_validation_result": None,
        "dry_run_preview_result": None,
        "chatgpt_readback_completed": None,
        "approval_record_validation_result": None,
        "approved_write_mode": None,
        "external_side_effect_allowed": False,
        "real_write_mode_allowed": False,
        "required_fields_present": False,
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
    parser.add_argument("--readiness-file", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Read one local readiness gate file and print validation JSON."""
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        print(json.dumps(_blocked_summary("invalid_arguments"), sort_keys=True))
        return 2

    try:
        readiness_gate_json = Path(args.readiness_file).read_text(encoding="utf-8")
    except OSError as error:
        summary = _blocked_summary(
            f"readiness_file_read_failed:{type(error).__name__}"
        )
        print(json.dumps(summary, sort_keys=True))
        return 0

    summary = validate_readiness_gate_json(readiness_gate_json)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Local-only CLI for Writeback Target Contract validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from local_runner_bridge.writeback_target_contract import (
    validate_writeback_target_contract_json,
)


def _blocked_summary(reason: str) -> dict:
    return {
        "protocol": "lawb.writeback_target_contract_local_validation_summary.v1",
        "result": "blocked",
        "validation_result": "blocked",
        "contract_version": None,
        "writeback_target_type": None,
        "writeback_target_reference": None,
        "required_fields_present": False,
        "approval_gate_satisfied": False,
        "chatgpt_readback_gate_satisfied": False,
        "dry_run_required": False,
        "forbidden_actions_present": False,
        "blocked_reasons": [reason],
        "external_side_effect_allowed": False,
        "github_write_performed": False,
        "result_packet_written": False,
        "codex_side_action_executed": False,
        "runner_invoked": False,
        "dispatcher_invoked": False,
        "watcher_invoked": False,
        "commit_performed": False,
        "push_performed": False,
        "next_recommended_action": "chatgpt_review",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--contract-file", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Read one local contract file and print a validation summary as JSON."""
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        if error.code == 0:
            return 0
        print(json.dumps(_blocked_summary("invalid_arguments"), sort_keys=True))
        return 2

    try:
        contract_json = Path(args.contract_file).read_text(encoding="utf-8")
    except OSError as error:
        summary = _blocked_summary(f"contract_file_read_failed:{type(error).__name__}")
        print(json.dumps(summary, sort_keys=True))
        return 0

    summary = validate_writeback_target_contract_json(contract_json)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

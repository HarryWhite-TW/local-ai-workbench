"""Local-only CLI for Writeback Dry-Run Preview building."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from local_runner_bridge.writeback_dry_run_preview import (
    build_writeback_dry_run_preview_from_json,
)


def _blocked_preview(reason: str) -> dict:
    return {
        "preview_version": "lawb.writeback_dry_run_preview.v1",
        "preview_id": None,
        "result": "blocked",
        "source_result_surface_id": None,
        "source_task_reference": None,
        "writeback_target_type": None,
        "writeback_target_reference": None,
        "contract_validation_result": None,
        "write_mode": "dry_run_only",
        "preview_content": "",
        "safe_preview_summary": "Local dry-run preview blocked.",
        "forbidden_actions": [],
        "safety_flags": {
            "external_side_effect_allowed": False,
            "token_value_printed": False,
            "token_value_written": False,
            "github_write_performed": False,
            "result_packet_written": False,
            "codex_side_action_executed": False,
            "runner_invoked": False,
            "dispatcher_invoked": False,
            "watcher_invoked": False,
            "pr_created": False,
            "merge_performed": False,
            "issue_closed": False,
            "label_changed": False,
            "approval_chaining_attempted": False,
        },
        "requires_chatgpt_readback": True,
        "requires_user_approval": True,
        "external_side_effect_allowed": False,
        "blocked_reasons": [reason],
        "next_recommended_step": "chatgpt_review",
        "created_at": None,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--contract-file", required=True)
    parser.add_argument("--result-surface-file", required=True)
    parser.add_argument("--preview-content")
    parser.add_argument("--preview-content-file")
    parser.add_argument("--preview-id")
    parser.add_argument("--created-at")
    return parser


def _read_text(path: str) -> tuple[str | None, str | None]:
    try:
        return Path(path).read_text(encoding="utf-8"), None
    except OSError as error:
        return None, type(error).__name__


def _load_preview_content(args: argparse.Namespace) -> tuple[str | None, str | None]:
    if args.preview_content and args.preview_content_file:
        return None, "multiple_preview_content_inputs"
    if args.preview_content:
        return args.preview_content, None
    if args.preview_content_file:
        return _read_text(args.preview_content_file)
    return None, "preview_content_missing"


def main(argv: list[str] | None = None) -> int:
    """Print one local dry-run preview as JSON."""
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        print(json.dumps(_blocked_preview("invalid_arguments"), sort_keys=True))
        return 2

    contract_json, error = _read_text(args.contract_file)
    if error:
        print(json.dumps(_blocked_preview(f"contract_file_read_failed:{error}"), sort_keys=True))
        return 0

    result_surface_json, error = _read_text(args.result_surface_file)
    if error:
        summary = _blocked_preview(f"result_surface_file_read_failed:{error}")
        print(json.dumps(summary, sort_keys=True))
        return 0

    preview_content, error = _load_preview_content(args)
    if error:
        print(json.dumps(_blocked_preview(error), sort_keys=True))
        return 0

    preview = build_writeback_dry_run_preview_from_json(
        contract_json or "",
        result_surface_json or "",
        preview_content or "",
        preview_id=args.preview_id,
        created_at=args.created_at,
    )
    print(json.dumps(preview, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

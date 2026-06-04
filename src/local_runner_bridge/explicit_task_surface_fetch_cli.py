"""Local read-only smoke entry for explicit task surface fetch."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from local_runner_bridge.explicit_task_surface_fetch import run_explicit_task_surface_fetch


def _blocked_summary(errors: list[str]) -> dict:
    return {
        "protocol": "lawb.local_runner.explicit_task_surface_fetch_summary.v1",
        "result": "blocked",
        "reference_type": None,
        "bounded_read_performed": False,
        "broad_issue_scan_performed": False,
        "github_write_performed": False,
        "result_packet_written": False,
        "codex_side_action_executed": False,
        "commit_triggered": False,
        "push_triggered": False,
        "pr_triggered": False,
        "issue_closed": False,
        "label_changed": False,
        "errors": errors,
        "next_recommended_action": "chatgpt_review",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--local-text-file")
    parser.add_argument("--issue-url")
    parser.add_argument("--comment-url")
    parser.add_argument("--github-token-env")
    return parser


def _selected_references(args: argparse.Namespace) -> list[tuple[str, str]]:
    candidates = [
        ("local_text_file", args.local_text_file),
        ("issue_url", args.issue_url),
        ("comment_url", args.comment_url),
    ]
    return [(kind, value) for kind, value in candidates if value]


def _load_reference(kind: str, value: str) -> tuple[dict | None, str | None]:
    if kind != "local_text_file":
        return None, value

    try:
        return None, Path(value).read_text(encoding="utf-8")
    except OSError as error:
        return _blocked_summary(["local_text_file_read_failed", type(error).__name__]), None


def main(argv: list[str] | None = None) -> int:
    """Print one read-only explicit fetch summary as JSON."""
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        print(json.dumps(_blocked_summary(["invalid_arguments"]), sort_keys=True))
        return 2

    selected = _selected_references(args)
    if not selected:
        print(json.dumps(_blocked_summary(["missing_input"]), sort_keys=True))
        return 0
    if len(selected) > 1:
        print(json.dumps(_blocked_summary(["multiple_inputs"]), sort_keys=True))
        return 0

    kind, value = selected[0]
    blocked, reference = _load_reference(kind, value)
    if blocked is not None:
        print(json.dumps(blocked, sort_keys=True))
        return 0

    github_token = None
    if args.github_token_env:
        github_token = os.environ.get(args.github_token_env)

    summary = run_explicit_task_surface_fetch(reference, github_token=github_token)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

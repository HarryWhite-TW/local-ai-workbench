"""Foreground CLI for Bridge Operator B3 bounded loop."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from local_runner_bridge.bridge_operator_b1 import DEFAULT_REPOSITORY, GitHubApiClient
from local_runner_bridge.bridge_operator_b2 import DEFAULT_INBOX_ISSUE
from local_runner_bridge.bridge_operator_b3 import (
    B3A_MODE,
    B3B_MODE,
    B3C_MODE,
    SUMMARY_PROTOCOL,
    run_bridge_operator_b3_dry_run_loop,
)


def _blocked_summary(errors: list[str]) -> dict:
    return {
        "protocol": SUMMARY_PROTOCOL,
        "result": "blocked",
        "phase": "blocked",
        "repository": DEFAULT_REPOSITORY,
        "configured_inbox_issue": DEFAULT_INBOX_ISSUE,
        "blocked_reasons": errors,
        "fixed_inbox_read_performed": False,
        "broad_issue_scan_performed": False,
        "latest_next_inference_performed": False,
        "dispatcher_invoked": False,
        "dispatcher_invocation_count": 0,
        "dispatcher_result_writeback_reached": False,
        "dispatcher_result_writeback_verified": False,
        "runner_invoked": False,
        "codex_invoked": False,
        "github_write_performed": False,
        "background_service_started": False,
        "commit_performed": False,
        "push_performed": False,
        "issue_closed": False,
        "label_changed": False,
        "pr_created": False,
        "merge_performed": False,
        "branch_deleted": False,
        "approval_consumed": False,
        "next_recommended_action": "chatgpt_review",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--repo", default=DEFAULT_REPOSITORY)
    parser.add_argument("--github-token-env")
    parser.add_argument("--max-cycles", type=int, required=True)
    parser.add_argument("--poll-interval-seconds", type=float, required=True)
    parser.add_argument("--state-dir")
    parser.add_argument("--mode", choices=[B3A_MODE, B3B_MODE, B3C_MODE], default=B3A_MODE)
    parser.add_argument("--timeout-seconds", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Print one parseable B3 bounded-loop summary as JSON."""
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        if error.code == 0:
            raise
        print(json.dumps(_blocked_summary(["invalid_arguments"]), sort_keys=True))
        return 2

    token = os.environ.get(args.github_token_env) if args.github_token_env else None
    client = GitHubApiClient(args.repo, token=token)
    summary = run_bridge_operator_b3_dry_run_loop(
        repo_root=Path(args.repo_root),
        repository=args.repo,
        inbox_issue=DEFAULT_INBOX_ISSUE,
        max_cycles=args.max_cycles,
        poll_interval_seconds=args.poll_interval_seconds,
        state_dir=args.state_dir,
        github_client=client,
        mode=args.mode,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary.get("result") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())

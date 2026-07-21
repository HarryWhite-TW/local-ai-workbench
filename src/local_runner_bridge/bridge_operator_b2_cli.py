"""Foreground one-shot CLI for Bridge Operator B2 delegation."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from local_runner_bridge.bridge_operator_b1 import DEFAULT_REPOSITORY, GitHubApiClient
from local_runner_bridge.bridge_operator_b2 import (
    DEFAULT_INBOX_ISSUE,
    SUMMARY_PROTOCOL,
    run_bridge_operator_b2_once,
)


def _blocked_summary(errors: list[str]) -> dict:
    return {
        "protocol": SUMMARY_PROTOCOL,
        "result": "blocked",
        "configured_inbox_issue": DEFAULT_INBOX_ISSUE,
        "blocked_reasons": errors,
        "broad_issue_scan_performed": False,
        "latest_next_inference_performed": False,
        "dispatcher_invoked": False,
        "dispatcher_invocation_count": 0,
        "retry_performed": False,
        "loop_started": False,
        "background_service_started": False,
        "github_write_performed": False,
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
    parser.add_argument("--target-repo-root")
    parser.add_argument("--github-token-env")
    parser.add_argument("--timeout-seconds", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Print one parseable B2 delegation summary as JSON."""
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        if error.code == 0:
            raise
        print(json.dumps(_blocked_summary(["invalid_arguments"]), sort_keys=True))
        return 2

    token = os.environ.get(args.github_token_env) if args.github_token_env else None
    if args.repo != DEFAULT_REPOSITORY and not args.target_repo_root:
        print(json.dumps(_blocked_summary(["target_repo_root_required"]), sort_keys=True))
        return 2
    control_client = GitHubApiClient(DEFAULT_REPOSITORY, token=token)
    target_client = (
        control_client
        if args.repo == DEFAULT_REPOSITORY
        else GitHubApiClient(args.repo, token=token)
    )
    target_root = Path(args.target_repo_root or args.repo_root)
    summary = run_bridge_operator_b2_once(
        repo_root=target_root,
        control_repo_root=Path(args.repo_root),
        repository=args.repo,
        inbox_issue=DEFAULT_INBOX_ISSUE,
        github_client=control_client,
        target_github_client=target_client,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary.get("result") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())


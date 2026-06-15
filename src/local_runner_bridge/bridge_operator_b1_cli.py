"""Foreground one-shot CLI for Bridge Operator B1 dry runs."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from local_runner_bridge.bridge_operator_b1 import (
    DEFAULT_REPOSITORY,
    GitHubApiClient,
    SUMMARY_PROTOCOL,
    run_bridge_operator_b1_dry_run,
)


def _blocked_summary(errors: list[str]) -> dict:
    return {
        "protocol": SUMMARY_PROTOCOL,
        "result": "blocked",
        "blocked_reasons": errors,
        "fixed_inbox_read_performed": False,
        "target_issue_read_performed": False,
        "broad_issue_scan_performed": False,
        "latest_next_inference_performed": False,
        "dispatcher_invoked": False,
        "runner_invoked": False,
        "codex_invoked": False,
        "github_write_performed": False,
        "commit_performed": False,
        "push_performed": False,
        "issue_closed": False,
        "label_changed": False,
        "pr_created": False,
        "merge_performed": False,
        "approval_consumed": False,
        "next_recommended_action": "chatgpt_review",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--inbox-issue", type=int, required=True)
    parser.add_argument("--repo", default=DEFAULT_REPOSITORY)
    parser.add_argument("--repo-root", default=str(Path.cwd()))
    parser.add_argument("--github-token-env")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Print one parseable B1 dry-run summary as JSON."""
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        if error.code == 0:
            raise
        print(json.dumps(_blocked_summary(["invalid_arguments"]), sort_keys=True))
        return int(error.code) if isinstance(error.code, int) else 2

    token = os.environ.get(args.github_token_env) if args.github_token_env else None
    client = GitHubApiClient(args.repo, token=token)
    summary = run_bridge_operator_b1_dry_run(
        inbox_issue=args.inbox_issue,
        repository=args.repo,
        repo_root=args.repo_root,
        github_client=client,
    )
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary.get("result") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())

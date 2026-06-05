"""Local stdout CLI for explicit fetch Result Surface review artifacts."""

from __future__ import annotations

import argparse
import json
import os

from local_runner_bridge.explicit_fetch_result_surface import (
    build_result_surface_from_explicit_reference,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--local-text-file")
    parser.add_argument("--issue-url")
    parser.add_argument("--comment-url")
    parser.add_argument("--github-token-env")
    return parser


def _selected_inputs(args: argparse.Namespace) -> list[str]:
    return [
        value
        for value in (args.local_text_file, args.issue_url, args.comment_url)
        if value
    ]


def main(argv: list[str] | None = None) -> int:
    """Print one explicit fetch Result Surface JSON artifact."""
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        result_surface = build_result_surface_from_explicit_reference(
            local_text="invalid arguments",
            result_id="explicit-fetch-result-surface-cli-blocked",
            created_at="blocked",
        )
        result_surface["status"] = "blocked"
        result_surface["blocked_reasons"] = ["invalid_arguments"]
        result_surface["source_task_validation_result"]["result"] = "blocked"
        result_surface["source_task_validation_result"]["errors"] = ["invalid_arguments"]
        print(json.dumps(result_surface, sort_keys=True))
        return 2

    selected = _selected_inputs(args)
    if len(selected) > 1:
        result_surface = build_result_surface_from_explicit_reference(
            local_text_file=args.local_text_file,
            issue_url=args.issue_url,
            comment_url=args.comment_url,
            result_id="explicit-fetch-result-surface-cli-blocked",
            created_at="blocked",
        )
    else:
        github_token = None
        if args.github_token_env:
            github_token = os.environ.get(args.github_token_env)

        result_surface = build_result_surface_from_explicit_reference(
            local_text_file=args.local_text_file,
            issue_url=args.issue_url,
            comment_url=args.comment_url,
            github_token=github_token,
        )

    print(json.dumps(result_surface, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Minimal read-only stdin/local text dry-run entry."""

from __future__ import annotations

import json
import sys

from local_runner_bridge.task_surface_validation_flow import validate_task_surface


def _blocked_exception_summary(error: Exception) -> dict:
    return {
        "protocol": "lawb.local_runner.task_surface_validation_summary.v1",
        "result": "blocked",
        "codex_side_action_executed": False,
        "repo_files_modified": False,
        "result_packet_written": False,
        "github_write_performed": False,
        "commit_performed": False,
        "push_performed": False,
        "errors": ["dry_run_exception", type(error).__name__],
        "next_recommended_action": "chatgpt_review",
    }


def run_validation_dry_run(surface_text: str, expected: dict | None = None) -> dict:
    """Return the read-only validation summary for explicit local surface text."""
    return validate_task_surface(surface_text, expected=expected)


def main(argv: list[str] | None = None) -> int:
    """Read task surface text from stdin and write a JSON validation summary."""
    _ = argv
    try:
        surface_text = sys.stdin.read()
        summary = run_validation_dry_run(surface_text)
        return_code = 0
    except Exception as error:
        summary = _blocked_exception_summary(error)
        return_code = 1

    print(json.dumps(summary, sort_keys=True))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())

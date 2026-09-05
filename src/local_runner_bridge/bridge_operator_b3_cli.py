"""Foreground CLI for Bridge Operator B3 bounded loop."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
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
        "dispatcher_execution_reach": None,
        "dispatcher_result_writeback_reached": False,
        "dispatcher_result_writeback_verified": False,
        "runner_reached": None,
        "codex_reached": None,
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
    parser.add_argument("--target-repo-root")
    parser.add_argument("--github-token-env")
    parser.add_argument("--max-cycles", type=int, required=True)
    parser.add_argument("--poll-interval-seconds", type=float, required=True)
    parser.add_argument("--state-dir")
    parser.add_argument("--mode", choices=[B3A_MODE, B3B_MODE, B3C_MODE], default=B3A_MODE)
    parser.add_argument("--timeout-seconds", type=int)
    parser.add_argument("--operator-session-id")
    parser.add_argument("--status-comment-id", type=int)
    parser.add_argument("--status-gh-path")
    return parser


def _status_progress_reporter(args: argparse.Namespace):
    if args.status_comment_id is None and args.status_gh_path is None:
        return None
    if args.status_comment_id is None or not args.status_gh_path:
        raise ValueError("status_progress_binding_incomplete")
    if args.status_comment_id <= 0:
        raise ValueError("status_progress_comment_id_invalid")

    gh_path = Path(args.status_gh_path)
    if not gh_path.is_file():
        raise ValueError("status_progress_gh_path_invalid")

    def human_view(
        lifecycle_stage: str, terminal_result: object
    ) -> str:
        """Render only lifecycle facts already established by machine evidence."""
        views = {
            "REQUEST_ACCEPTED": (
                "狀態：執行中\n"
                "目前階段：任務已接受\n"
                "現在需要你：不需要"
            ),
            "DISPATCHER_REACHED": (
                "狀態：執行中\n"
                "目前階段：已派工（Dispatcher 已到達）\n"
                "現在需要你：不需要"
            ),
            "RUNNER_OR_CODEX_REACH_UNCERTAIN": (
                "狀態：執行中\n"
                "目前階段：Runner／Codex 是否已到達尚未確認\n"
                "現在需要你：不需要"
            ),
            "BLOCKED_OR_FAILED": (
                "狀態：已阻塞\n"
                "下一步：由 ChatGPT 判讀結果"
            ),
        }
        if lifecycle_stage == "TERMINAL_RESULT_READY":
            if terminal_result == "success":
                return (
                    "狀態：等待 ChatGPT 審核\n"
                    "目前階段：執行結果已就緒\n"
                    "現在需要你：不需要\n"
                    "下一步：等待 ChatGPT 最終審核"
                )
            return (
                "狀態：已阻塞\n"
                "目前階段：執行結果已就緒\n"
                "下一步：由 ChatGPT 判讀結果"
            )
        return views[lifecycle_stage]

    def report(current_run: dict) -> None:
        lifecycle = current_run.get("lifecycle") or {}
        lifecycle_stage = lifecycle.get("stage")
        if lifecycle_stage == "REQUEST_ACCEPTED":
            result = "running"
            next_action = "review_operator_result"
        elif lifecycle_stage in {
            "DISPATCHER_REACHED",
            "RUNNER_OR_CODEX_REACH_UNCERTAIN",
        }:
            result = "running"
            next_action = "review_operator_result"
        elif lifecycle_stage == "BLOCKED_OR_FAILED":
            result = "blocked"
            next_action = "review_blocked_result"
        elif lifecycle_stage == "TERMINAL_RESULT_READY":
            terminal_result = current_run.get("terminal_result")
            if terminal_result == "success":
                result = "waiting_review"
                next_action = "chatgpt_final_review"
            elif terminal_result in {"failure", "blocked"}:
                result = "blocked"
                next_action = "review_blocked_result"
            else:
                raise ValueError("status_progress_terminal_result_invalid")
        else:
            raise ValueError("status_progress_lifecycle_invalid")
        request_id = current_run.get("request_id")
        issue_number = current_run.get("issue_number")
        if (
            not isinstance(request_id, str)
            or not request_id
            or not isinstance(issue_number, int)
            or current_run.get("requested_action") != "run-reviewbundle"
        ):
            raise ValueError("status_progress_request_identity_invalid")
        payload = {
            "protocol": "lawb.bridge_status.v1",
            "run_id": args.operator_session_id,
            "stage": "operator",
            "result": result,
            "repository": args.repo,
            "request_id": request_id,
            "target_issue": issue_number,
            "requested_action": current_run["requested_action"],
            "current_run": current_run,
            "next_action": next_action,
        }
        body = (
            "LAWBRIDGE-STATUS protocol=lawb.bridge_status.v1\n\n```json\n"
            + json.dumps(payload, separators=(",", ":"), sort_keys=True)
            + "\n```\n\n## 人類可讀狀態\n\n"
            + human_view(lifecycle_stage, terminal_result if lifecycle_stage == "TERMINAL_RESULT_READY" else None)
        )
        completed = subprocess.run(
            [
                str(gh_path),
                "api",
                "--hostname",
                "github.com",
                "--method",
                "PATCH",
                "repos/HarryWhite-TW/local-ai-workbench/issues/comments/"
                + str(args.status_comment_id),
                "--input",
                "-",
            ],
            input=json.dumps({"body": body}, separators=(",", ":")),
            text=True,
            capture_output=True,
            timeout=args.timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("status_progress_write_failed")
        try:
            response = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError("status_progress_write_unverified") from error
        if response.get("id") != args.status_comment_id:
            raise RuntimeError("status_progress_write_unverified")

    return report


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

    try:
        status_progress_reporter = _status_progress_reporter(args)
    except ValueError as error:
        print(json.dumps(_blocked_summary([str(error)]), sort_keys=True))
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
    summary = run_bridge_operator_b3_dry_run_loop(
        repo_root=target_root,
        control_repo_root=Path(args.repo_root),
        repository=args.repo,
        inbox_issue=DEFAULT_INBOX_ISSUE,
        max_cycles=args.max_cycles,
        poll_interval_seconds=args.poll_interval_seconds,
        state_dir=args.state_dir,
        github_client=control_client,
        target_github_client=target_client,
        mode=args.mode,
        timeout_seconds=args.timeout_seconds,
        operator_session_id=args.operator_session_id,
        status_progress_reporter=status_progress_reporter,
    )
    print(json.dumps(summary, sort_keys=True))
    if summary.get("result") == "success":
        return 0
    if summary.get("result") == "unresolved":
        return 3
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

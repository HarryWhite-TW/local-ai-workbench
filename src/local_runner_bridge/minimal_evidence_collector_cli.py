"""CLI for the local-only OPT-02 minimal evidence collector."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .minimal_evidence_collector import (
    CollectorError,
    begin_session,
    compact_review_summary,
    finalize_session,
    run_command,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect local command evidence.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    begin = subparsers.add_parser("begin")
    begin.add_argument("--repo-root", required=True)
    begin.add_argument("--evidence-root", required=True)
    begin.add_argument("--profile", required=True)
    begin.add_argument("--label", required=False)

    run = subparsers.add_parser("run")
    run.add_argument("--session", required=True)
    run.add_argument("--id", required=True)
    run.add_argument("argv", nargs=argparse.REMAINDER)

    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--session", required=True)

    return parser


def _blocked(reason: str) -> dict[str, object]:
    return {
        "schema_version": "lawb.minimal_evidence_collector.blocked.v0.1",
        "result": "collector_error",
        "blocked_reason": reason,
        "github_write_performed": False,
        "git_write_performed": False,
        "issue_write_performed": False,
        "bridge_invoked": False,
        "dispatcher_invoked": False,
        "runner_invoked": False,
        "codex_invoked": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "begin":
            session_path = begin_session(
                repo_root=Path(args.repo_root),
                evidence_root=Path(args.evidence_root),
                profile=args.profile,
                label=args.label,
            )
            print(json.dumps({"session_path": str(session_path)}, sort_keys=True))
            return 0

        if args.command == "run":
            command_argv = list(args.argv)
            if command_argv and command_argv[0] == "--":
                command_argv = command_argv[1:]
            result = run_command(
                session_path=Path(args.session),
                command_id=args.id,
                argv=command_argv,
            )
            print(json.dumps(result, sort_keys=True))
            return 0 if result["exit_code"] == 0 else 1

        if args.command == "finalize":
            review_packet_path = finalize_session(session_path=Path(args.session))
            print(json.dumps(compact_review_summary(review_packet_path), sort_keys=True))
            return 0
    except CollectorError as exc:
        print(json.dumps(_blocked(str(exc)), sort_keys=True))
        return 2

    print(json.dumps(_blocked("unknown_command"), sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

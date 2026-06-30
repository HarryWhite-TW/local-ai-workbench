"""CLI for RV2-03 A3 read-only publication preflight."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from local_runner_bridge.rv2_03_publication_preflight import PROTOCOL, run_publication_preflight


class _ArgumentError(Exception):
    pass


class _DuplicateJsonKey(ValueError):
    pass


class _StructuredArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _ArgumentError(message)


def _parser() -> argparse.ArgumentParser:
    parser = _StructuredArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--state-dir")
    parser.add_argument("--pretty", action="store_true")
    return parser


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise _DuplicateJsonKey(key)
        value[key] = item
    return value


def _print(payload: dict[str, Any], pretty: bool) -> None:
    print(json.dumps(payload, indent=2 if pretty else None, sort_keys=True))


def _cli_error_result(code: str, message: str) -> dict[str, Any]:
    return {
        "protocol": PROTOCOL,
        "result": "blocked",
        "publication_safe": False,
        "blocked_reasons": [code],
        "approval_a": None,
        "next_required_action": "stop_and_review",
        "safety": {
            "github_write_performed": False,
            "b2_invoked": False,
            "b3_loop_invoked": False,
            "dispatcher_invoked": False,
            "runner_invoked": False,
            "codex_invoked": False,
            "stage_performed": False,
            "commit_performed": False,
            "push_performed": False,
        },
        "errors": [{"code": code, "field": "$", "message": message}],
    }


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except _ArgumentError:
        payload = _cli_error_result("invalid_cli_arguments", "CLI arguments are invalid.")
        _print(payload, False)
        return 2

    try:
        text = Path(args.manifest).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        payload = _cli_error_result("manifest_read_failed", "Manifest could not be read.")
        _print(payload, args.pretty)
        return 2

    try:
        manifest = json.loads(text, object_pairs_hook=_strict_object)
    except _DuplicateJsonKey:
        payload = _cli_error_result(
            "duplicate_json_key",
            "Manifest contains a duplicate JSON object key.",
        )
        _print(payload, args.pretty)
        return 2
    except json.JSONDecodeError:
        payload = _cli_error_result("malformed_json", "Manifest is not valid JSON.")
        _print(payload, args.pretty)
        return 2

    try:
        payload = run_publication_preflight(
            manifest,
            repo_root=args.repo_root,
            state_dir=args.state_dir,
        )
    except Exception:
        payload = _cli_error_result(
            "internal_preflight_failure",
            "Unexpected internal preflight failure.",
        )
        _print(payload, args.pretty)
        return 1

    _print(payload, args.pretty)
    return 0 if payload.get("publication_safe") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())

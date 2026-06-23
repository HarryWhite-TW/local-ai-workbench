"""CLI for local-only B4-D smoke manifest validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from local_runner_bridge.b4d_smoke_manifest import (
    malformed_input_result,
    validate_manifest,
)


class _ArgumentError(Exception):
    pass


class _DuplicateJsonKey(ValueError):
    def __init__(self, key: str):
        super().__init__(key)
        self.key = key


class _StructuredArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _ArgumentError(message)


def _parser() -> argparse.ArgumentParser:
    parser = _StructuredArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--pretty", action="store_true")
    return parser


def _print(payload: dict[str, Any], pretty: bool) -> None:
    print(json.dumps(payload, indent=2 if pretty else None, sort_keys=True))


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise _DuplicateJsonKey(key)
        value[key] = item
    return value


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except _ArgumentError:
        payload = malformed_input_result("invalid_cli_arguments", "CLI arguments are invalid.")
        _print(payload, False)
        return 2
    try:
        text = Path(args.manifest).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        payload = malformed_input_result("manifest_read_failed", f"Manifest could not be read: {type(error).__name__}.")
        _print(payload, args.pretty)
        return 2

    try:
        manifest = json.loads(text, object_pairs_hook=_strict_object)
    except _DuplicateJsonKey:
        payload = malformed_input_result("duplicate_json_key", "Manifest contains a duplicate JSON object key.")
        _print(payload, args.pretty)
        return 2
    except json.JSONDecodeError:
        payload = malformed_input_result("malformed_json", "Manifest is not valid JSON.")
        _print(payload, args.pretty)
        return 2

    try:
        payload = validate_manifest(manifest)
    except Exception:
        payload = malformed_input_result("internal_validation_failure", "Unexpected internal validation failure.")
        _print(payload, args.pretty)
        return 1

    _print(payload, args.pretty)
    return 0 if payload["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

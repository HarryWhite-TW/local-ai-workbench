"""Local-only Task Surface to Result Surface stdout CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from local_runner_bridge.result_surface import build_result_surface
from local_runner_bridge.task_result_surface import (
    build_result_surface_from_task_surface_text,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--local-text-file")
    return parser


def _blocked_result_surface(errors: list[str]) -> dict:
    return build_result_surface(
        result_id="task-result-surface-cli-blocked",
        source_task_reference={
            "kind": "local_text_file",
            "description": "Task Result Surface CLI blocked summary",
        },
        source_task_validation_result={"result": "blocked", "errors": errors},
        operation_mode="local_task_surface_validation_review",
        status="blocked",
        summary="Task Result Surface CLI did not receive a readable local text file.",
        blocked_reasons=errors,
        created_at="blocked",
    )


def main(argv: list[str] | None = None) -> int:
    """Print a local-only Result Surface for one local Task Surface text file."""
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        print(json.dumps(_blocked_result_surface(["invalid_arguments"]), sort_keys=True))
        return 2

    if not args.local_text_file:
        print(json.dumps(_blocked_result_surface(["missing_local_text_file"]), sort_keys=True))
        return 0

    try:
        surface_text = Path(args.local_text_file).read_text(encoding="utf-8")
    except OSError as error:
        print(
            json.dumps(
                _blocked_result_surface(["local_text_file_read_failed", type(error).__name__]),
                sort_keys=True,
            )
        )
        return 0

    result_surface = build_result_surface_from_task_surface_text(
        surface_text,
        source_task_reference={
            "kind": "local_text_file",
            "path": str(args.local_text_file),
        },
    )
    print(json.dumps(result_surface, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


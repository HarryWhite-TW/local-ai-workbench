"""Local-only Result Surface stdout CLI."""

from __future__ import annotations

import argparse
import json

from local_runner_bridge.result_surface import build_result_surface


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--sample", action="store_true")
    return parser


def _blocked_summary(errors: list[str]) -> dict:
    return build_result_surface(
        result_id="result-surface-cli-blocked",
        source_task_reference={
            "kind": "local_result_surface_cli",
            "description": "Local Result Surface CLI blocked summary",
        },
        source_task_validation_result={"result": "blocked"},
        status="blocked",
        summary="Local Result Surface CLI did not receive a valid sample request.",
        blocked_reasons=errors,
        created_at="blocked",
    )


def sample_result_surface() -> dict:
    """Return the safe sample Result Surface used by the CLI."""
    return build_result_surface(
        result_id="result-160-local-stdout-smoke",
        source_task_reference={
            "kind": "local_stdout_smoke",
            "issue_number": 160,
            "description": "Local-only Result Surface stdout smoke evidence",
        },
        source_task_validation_result={
            "result": "success",
            "validation_dry_run_reached": True,
            "task_packet_protocol_valid": True,
            "required_fields_present": True,
        },
        summary=(
            "Sample local-only Result Surface emitted to stdout for ChatGPT "
            "readback review. No code changes or external writes were performed."
        ),
        tests_run=[
            {
                "command": "not_run",
                "result": "not_run",
                "reason": "local stdout smoke only; no code or tests changed",
            }
        ],
        next_recommended_step="chatgpt_review_then_user_decides_161_boundary",
        created_at="2026-06-05T00:00:00Z",
    )


def main(argv: list[str] | None = None) -> int:
    """Print one local-only Result Surface JSON object."""
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        print(json.dumps(_blocked_summary(["invalid_arguments"]), sort_keys=True))
        return 2

    if not args.sample:
        print(json.dumps(_blocked_summary(["missing_sample_flag"]), sort_keys=True))
        return 0

    print(json.dumps(sample_result_surface(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


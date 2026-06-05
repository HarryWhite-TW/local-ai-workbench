"""Adapt local Task Surface validation summaries into Result Surfaces."""

from __future__ import annotations

from local_runner_bridge.result_surface import build_result_surface
from local_runner_bridge.task_surface_dry_run import run_validation_dry_run


def _blocked_reasons(validation_summary: dict) -> list[str]:
    errors = validation_summary.get("errors")
    if isinstance(errors, list):
        return [str(error) for error in errors]
    return []


def build_result_surface_from_task_surface_text(
    surface_text: str,
    *,
    expected: dict | None = None,
    result_id: str | None = None,
    created_at: str | None = None,
    source_task_reference: dict | None = None,
) -> dict:
    """Validate local Task Surface text and return a local-only Result Surface."""
    validation_summary = run_validation_dry_run(surface_text, expected=expected)
    status = validation_summary.get("result", "blocked")
    blocked_reasons = [] if status == "success" else _blocked_reasons(validation_summary)

    return build_result_surface(
        result_id=result_id,
        source_task_reference=source_task_reference
        or {
            "kind": "local_task_surface_text",
            "description": "Local Task Surface validation dry-run input",
        },
        source_task_validation_result=validation_summary,
        operation_mode="local_task_surface_validation_review",
        status=status,
        summary=(
            "Local Task Surface validation dry-run converted to Result Surface "
            "review evidence. No tasks were executed and no external writes were "
            "performed."
        ),
        files_changed=[],
        tests_run=[
            {
                "command": "local_runner_bridge.task_surface_dry_run.run_validation_dry_run",
                "result": status,
                "reason": "local validation dry-run only",
            }
        ],
        blocked_reasons=blocked_reasons,
        requires_user_approval=True,
        next_recommended_step="chatgpt_review_then_user_decides_next_boundary",
        created_at=created_at,
    )


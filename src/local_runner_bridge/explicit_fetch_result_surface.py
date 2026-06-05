"""Adapt explicit Task Surface fetch summaries into Result Surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from local_runner_bridge.explicit_task_surface_fetch import (
    run_explicit_task_surface_fetch,
)
from local_runner_bridge.result_surface import build_result_surface, default_safety_flags


def _selected_inputs(inputs: dict[str, str | None]) -> list[tuple[str, str]]:
    return [(kind, value) for kind, value in inputs.items() if value]


def _blocked_result_surface(
    *,
    errors: list[str],
    result_id: str | None,
    created_at: str | None,
    source_task_reference: dict | None = None,
) -> dict:
    summary = {
        "protocol": "lawb.local_runner.explicit_task_surface_fetch_summary.v1",
        "result": "blocked",
        "errors": errors,
        "bounded_read_performed": False,
        "broad_issue_scan_performed": False,
        "github_write_performed": False,
        "result_packet_written": False,
        "codex_side_action_executed": False,
        "commit_triggered": False,
        "push_triggered": False,
        "pr_triggered": False,
        "issue_closed": False,
        "label_changed": False,
    }
    return _result_surface_from_fetch_summary(
        summary,
        result_id=result_id,
        created_at=created_at,
        source_task_reference=source_task_reference
        or {
            "kind": "explicit_task_surface_reference",
            "description": "Blocked explicit Task Surface Result Surface request",
        },
    )


def _safety_flags_from_fetch_summary(fetch_summary: dict) -> dict[str, bool]:
    flags = default_safety_flags()
    flags.update(
        {
            "github_write_performed": bool(fetch_summary.get("github_write_performed")),
            "result_packet_written": bool(fetch_summary.get("result_packet_written")),
            "codex_side_action_executed": bool(
                fetch_summary.get("codex_side_action_executed")
            ),
            "broad_scan_performed": bool(
                fetch_summary.get("broad_issue_scan_performed")
            ),
            "commit_performed": bool(fetch_summary.get("commit_triggered")),
            "push_performed": bool(fetch_summary.get("push_triggered")),
            "pr_created": bool(fetch_summary.get("pr_triggered")),
            "issue_closed": bool(fetch_summary.get("issue_closed")),
            "label_changed": bool(fetch_summary.get("label_changed")),
        }
    )
    return flags


def _blocked_reasons(fetch_summary: dict) -> list[str]:
    errors = fetch_summary.get("errors")
    if isinstance(errors, list):
        return [str(error) for error in errors]
    return []


def _result_surface_from_fetch_summary(
    fetch_summary: dict,
    *,
    result_id: str | None,
    created_at: str | None,
    source_task_reference: dict,
) -> dict:
    status = fetch_summary.get("result", "blocked")
    return build_result_surface(
        result_id=result_id,
        source_task_reference=source_task_reference,
        source_task_validation_result=fetch_summary,
        operation_mode="explicit_fetch_result_surface_review",
        status=status,
        summary=(
            "Explicit Task Surface fetch/validation summary converted to Result "
            "Surface review evidence. No tasks were executed and no external "
            "writes were performed."
        ),
        files_changed=[],
        tests_run=[
            {
                "command": "local_runner_bridge.explicit_task_surface_fetch.run_explicit_task_surface_fetch",
                "result": status,
                "reason": "explicit fetch/validation summary only",
            }
        ],
        safety_flags=_safety_flags_from_fetch_summary(fetch_summary),
        blocked_reasons=[] if status == "success" else _blocked_reasons(fetch_summary),
        requires_user_approval=True,
        next_recommended_step="chatgpt_review_then_user_decides_next_boundary",
        created_at=created_at,
    )


def build_result_surface_from_explicit_reference(
    *,
    local_text: str | None = None,
    local_text_file: str | None = None,
    issue_url: str | None = None,
    comment_url: str | None = None,
    expected: dict | None = None,
    result_id: str | None = None,
    created_at: str | None = None,
    github_token: str | None = None,
    http_get_json: Callable[[str, str | None], dict[str, Any]] | None = None,
) -> dict:
    """Return a Result Surface for exactly one explicit local or stubbed reference."""
    selected = _selected_inputs(
        {
            "local_text": local_text,
            "local_text_file": local_text_file,
            "issue_url": issue_url,
            "comment_url": comment_url,
        }
    )
    if not selected:
        return _blocked_result_surface(
            errors=["missing_input"],
            result_id=result_id,
            created_at=created_at,
        )
    if len(selected) > 1:
        return _blocked_result_surface(
            errors=["multiple_inputs"],
            result_id=result_id,
            created_at=created_at,
        )

    kind, value = selected[0]
    reference = value
    if kind == "local_text_file":
        try:
            reference = Path(value).read_text(encoding="utf-8")
        except OSError as error:
            return _blocked_result_surface(
                errors=["local_text_file_read_failed", type(error).__name__],
                result_id=result_id,
                created_at=created_at,
                source_task_reference={"kind": kind, "path": value},
            )

    if kind in {"issue_url", "comment_url"} and not github_token:
        return _blocked_result_surface(
            errors=["github_token_required_for_live_fetch"],
            result_id=result_id,
            created_at=created_at,
            source_task_reference={"kind": kind, "reference": value},
        )

    fetch_summary = run_explicit_task_surface_fetch(
        reference,
        expected=expected,
        github_token=github_token,
        http_get_json=http_get_json,
    )
    return _result_surface_from_fetch_summary(
        fetch_summary,
        result_id=result_id,
        created_at=created_at,
        source_task_reference=(
            {"kind": kind, "path": value}
            if kind == "local_text_file"
            else {"kind": kind, "reference": value}
        ),
    )

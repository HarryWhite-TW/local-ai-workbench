"""Local-only Result Surface review artifact builder."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

RESULT_SURFACE_VERSION = "lawb.local_result_surface.v0.draft"

REQUIRED_SAFETY_FLAGS = (
    "github_write_performed",
    "result_packet_written",
    "codex_side_action_executed",
    "runner_invoked",
    "dispatcher_invoked",
    "watcher_invoked",
    "broad_scan_performed",
    "commit_performed",
    "push_performed",
    "pr_created",
    "merge_performed",
    "issue_closed",
    "label_changed",
)


def default_safety_flags() -> dict[str, bool]:
    """Return the local-only no-write/no-action safety flags."""
    return {flag: False for flag in REQUIRED_SAFETY_FLAGS}


def _default_result_id() -> str:
    return f"result-{uuid4().hex}"


def _default_created_at() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_result_surface(
    *,
    result_id: str | None = None,
    source_task_reference: dict | None = None,
    source_task_validation_result: dict | None = None,
    operation_mode: str = "local_read_only_review",
    status: str = "success",
    summary: str = (
        "Local-only Result Surface review artifact. "
        "No code changes or external writes were performed."
    ),
    files_changed: list | None = None,
    tests_run: list | None = None,
    safety_flags: dict | None = None,
    blocked_reasons: list | None = None,
    requires_user_approval: bool = True,
    next_recommended_step: str = "chatgpt_review_then_user_decides_next_boundary",
    created_at: str | None = None,
) -> dict:
    """Build a local-only Result Surface without executing or writing anything."""
    flags = default_safety_flags()
    if safety_flags:
        flags.update(safety_flags)

    return {
        "result_surface_version": RESULT_SURFACE_VERSION,
        "result_id": result_id or _default_result_id(),
        "source_task_reference": source_task_reference
        or {
            "kind": "local_sample",
            "description": "Local-only Result Surface review artifact",
        },
        "source_task_validation_result": source_task_validation_result
        or {
            "result": "success",
            "validation_dry_run_reached": True,
        },
        "operation_mode": operation_mode,
        "status": status,
        "summary": summary,
        "files_changed": files_changed or [],
        "tests_run": tests_run or [],
        "safety_flags": flags,
        "blocked_reasons": blocked_reasons or [],
        "requires_user_approval": requires_user_approval,
        "next_recommended_step": next_recommended_step,
        "created_at": created_at or _default_created_at(),
    }


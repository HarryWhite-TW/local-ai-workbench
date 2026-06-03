"""Extract one Task Packet v1 from an explicit task surface text."""

from __future__ import annotations

PROTOCOL_MARKER = "LOCAL-RUNNER-TASK-PACKET-V1"
BEGIN_MARKER = "BEGIN_TASK_PACKET"
END_MARKER = "END_TASK_PACKET"
SLICE_NAME = "read_only_task_surface_resolver_and_packet_validator"


def _summary(
    *,
    result: str,
    errors: list[str],
    active_task_packet_count: int = 0,
    packet_text: str | None = None,
    boundary_markers_valid: bool = False,
) -> dict:
    summary = {
        "protocol": "lawb.local_runner.task_surface_validation_summary.v1",
        "result": result,
        "slice_name": SLICE_NAME,
        "task_surface_reference_checked": True,
        "active_task_packet_count": active_task_packet_count,
        "task_packet_boundary_markers_valid": boundary_markers_valid,
        "task_packet_protocol_valid": False,
        "logical_issue_matches_expected": False,
        "phase_matches_expected": False,
        "required_fields_present": False,
        "codex_side_action_executed": False,
        "repo_files_modified": False,
        "result_packet_written": False,
        "github_write_performed": False,
        "commit_performed": False,
        "push_performed": False,
        "errors": errors,
        "next_recommended_action": "chatgpt_review",
    }
    if packet_text is not None:
        summary["packet_text"] = packet_text
    return summary


def extract_task_packet(surface_text: str) -> dict:
    """Return a local summary containing exactly one packet body, or fail closed."""
    if not isinstance(surface_text, str):
        return _summary(result="blocked", errors=["surface_text_not_string"])

    lines = surface_text.splitlines()
    protocol_lines = [
        index for index, line in enumerate(lines) if line.strip() == PROTOCOL_MARKER
    ]
    if not protocol_lines:
        return _summary(result="blocked", errors=["protocol_marker_missing"])

    begin_lines = [
        index for index, line in enumerate(lines) if line.strip() == BEGIN_MARKER
    ]
    end_lines = [
        index for index, line in enumerate(lines) if line.strip() == END_MARKER
    ]
    begin_count = len(begin_lines)
    end_count = len(end_lines)
    if begin_count == 0 and end_count == 0:
        return _summary(result="blocked", errors=["task_packet_boundary_markers_missing"])
    if begin_count == 0:
        return _summary(result="blocked", errors=["begin_task_packet_missing"])
    if end_count == 0:
        return _summary(result="blocked", errors=["end_task_packet_missing"])
    if begin_count != end_count:
        return _summary(
            result="blocked",
            errors=["task_packet_boundary_markers_mismatched"],
            active_task_packet_count=min(begin_count, end_count),
        )
    if begin_count > 1:
        return _summary(
            result="blocked",
            errors=["multiple_active_task_packets"],
            active_task_packet_count=begin_count,
        )

    begin_index = begin_lines[0]
    end_index = end_lines[0]
    if end_index <= begin_index:
        return _summary(
            result="blocked",
            errors=["task_packet_boundary_markers_malformed"],
            active_task_packet_count=1,
        )

    packet_text = "\n".join(lines[begin_index + 1 : end_index]).strip()
    if not packet_text:
        return _summary(
            result="blocked",
            errors=["task_packet_empty"],
            active_task_packet_count=1,
        )

    return _summary(
        result="success",
        errors=[],
        active_task_packet_count=1,
        packet_text=packet_text,
        boundary_markers_valid=True,
    )


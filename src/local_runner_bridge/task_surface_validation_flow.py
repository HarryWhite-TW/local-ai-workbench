"""Read-only flow connecting task surface extraction and packet validation."""

from __future__ import annotations

from local_runner_bridge.task_packet_validator import validate_task_packet
from local_runner_bridge.task_surface_resolver import extract_task_packet


def validate_task_surface(surface_text: str, expected: dict | None = None) -> dict:
    """Validate one explicit task surface without executing or writing anything."""
    extracted = extract_task_packet(surface_text)
    if extracted["result"] != "success":
        return extracted

    return validate_task_packet(extracted["packet_text"], expected=expected)

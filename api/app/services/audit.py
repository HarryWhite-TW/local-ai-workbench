from __future__ import annotations

import json
import sqlite3
from typing import Any


def create_audit_event(
    connection: sqlite3.Connection,
    *,
    action_id: str | None,
    event_type: str,
    event_payload: dict[str, Any],
    created_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO audit_events (action_id, event_type, event_payload, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (action_id, event_type, json.dumps(event_payload), created_at),
    )


def list_audit_events(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT id, action_id, event_type, event_payload, created_at
        FROM audit_events
        ORDER BY created_at DESC, id DESC
        """
    ).fetchall()

    return [
        {
            "id": row["id"],
            "action_id": row["action_id"],
            "event_type": row["event_type"],
            "event_payload": json.loads(row["event_payload"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


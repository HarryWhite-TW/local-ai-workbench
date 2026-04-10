from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from api.app.services.audit import create_audit_event


class ActionNotFoundError(Exception):
    """Raised when an action cannot be found."""


class ActionStateError(Exception):
    """Raised when an action is not in the expected state."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def serialize_action(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "action_type": row["action_type"],
        "title": row["title"],
        "status": row["status"],
        "preview_payload": json.loads(row["preview_payload"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "approved_at": row["approved_at"],
    }


def list_actions(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT id, action_type, title, preview_payload, status, created_at, updated_at, approved_at
        FROM actions
        ORDER BY created_at DESC, id DESC
        """
    ).fetchall()
    return [serialize_action(row) for row in rows]


def create_preview_action(
    connection: sqlite3.Connection,
    *,
    action_type: str,
    title: str,
    preview_payload: dict[str, Any],
) -> dict[str, Any]:
    action_id = f"act_{uuid4().hex[:12]}"
    timestamp = utc_now()

    connection.execute(
        """
        INSERT INTO actions (
            id, action_type, title, preview_payload, status, created_at, updated_at, approved_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            action_id,
            action_type,
            title,
            json.dumps(preview_payload),
            "preview",
            timestamp,
            timestamp,
            None,
        ),
    )
    create_audit_event(
        connection,
        action_id=action_id,
        event_type="action_created",
        event_payload={"title": title, "action_type": action_type},
        created_at=timestamp,
    )
    row = connection.execute(
        """
        SELECT id, action_type, title, preview_payload, status, created_at, updated_at, approved_at
        FROM actions
        WHERE id = ?
        """,
        (action_id,),
    ).fetchone()
    return serialize_action(row)


def approve_action(connection: sqlite3.Connection, action_id: str) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT id, action_type, title, preview_payload, status, created_at, updated_at, approved_at
        FROM actions
        WHERE id = ?
        """,
        (action_id,),
    ).fetchone()

    if row is None:
        raise ActionNotFoundError(action_id)

    if row["status"] != "preview":
        raise ActionStateError(f"Action {action_id} is not in preview state.")

    timestamp = utc_now()
    connection.execute(
        """
        UPDATE actions
        SET status = ?, updated_at = ?, approved_at = ?
        WHERE id = ?
        """,
        ("approved", timestamp, timestamp, action_id),
    )
    create_audit_event(
        connection,
        action_id=action_id,
        event_type="action_approved",
        event_payload={"title": row["title"], "action_type": row["action_type"]},
        created_at=timestamp,
    )
    updated_row = connection.execute(
        """
        SELECT id, action_type, title, preview_payload, status, created_at, updated_at, approved_at
        FROM actions
        WHERE id = ?
        """,
        (action_id,),
    ).fetchone()
    return serialize_action(updated_row)


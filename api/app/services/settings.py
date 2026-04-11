from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from api.app.db import ROOT_FOLDER_SETTING_KEY
from api.app.services.audit import create_audit_event


class InvalidRootFolderError(Exception):
    """Raised when the requested root folder is invalid."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_root_folder_setting(connection: sqlite3.Connection) -> dict[str, str | None]:
    row = connection.execute(
        """
        SELECT value, updated_at
        FROM app_settings
        WHERE key = ?
        """,
        (ROOT_FOLDER_SETTING_KEY,),
    ).fetchone()

    if row is None:
        return {"root_folder": None, "updated_at": None}

    return {"root_folder": row["value"], "updated_at": row["updated_at"]}


def validate_root_folder(raw_path: str) -> str:
    candidate = raw_path.strip()
    if not candidate:
        raise InvalidRootFolderError("Root folder must not be empty.", 400)

    path = Path(candidate)
    if not path.is_absolute():
        raise InvalidRootFolderError("Root folder must be an absolute path.", 400)

    if not path.exists():
        raise InvalidRootFolderError("Root folder does not exist.", 404)

    if not path.is_dir():
        raise InvalidRootFolderError("Root folder must be a directory.", 400)

    return str(path.resolve())


def set_root_folder_setting(connection: sqlite3.Connection, raw_path: str) -> dict[str, str]:
    normalized_path = validate_root_folder(raw_path)
    timestamp = utc_now()

    connection.execute(
        """
        INSERT INTO app_settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        """,
        (ROOT_FOLDER_SETTING_KEY, normalized_path, timestamp),
    )
    create_audit_event(
        connection,
        action_id=None,
        event_type="root_folder_updated",
        event_payload={"root_folder": normalized_path},
        created_at=timestamp,
    )
    return {"root_folder": normalized_path, "updated_at": timestamp}


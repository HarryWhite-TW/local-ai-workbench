from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from api.app.services.audit import create_audit_event
from api.app.services.settings import InvalidRootFolderError, get_root_folder_setting, utc_now, validate_root_folder

SUPPORTED_SUFFIXES = {".md": "md", ".txt": "txt"}


class RootFolderNotConfiguredError(Exception):
    """Raised when a root folder has not been configured."""


class DocumentNotFoundError(Exception):
    """Raised when a document cannot be found."""


def get_configured_root_folder(connection: sqlite3.Connection) -> str:
    setting = get_root_folder_setting(connection)
    root_folder = setting["root_folder"]
    if root_folder is None:
        raise RootFolderNotConfiguredError("Root folder has not been configured.")

    return validate_root_folder(root_folder)


def build_document_id(relative_path: str) -> str:
    digest = hashlib.sha1(relative_path.encode("utf-8")).hexdigest()[:16]
    return f"doc_{digest}"


def normalize_relative_path(root_folder: Path, file_path: Path) -> str:
    return file_path.relative_to(root_folder).as_posix()


def _stat_to_iso_utc(timestamp: float) -> str:
    from datetime import datetime, timezone

    return (
        datetime.fromtimestamp(timestamp, tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def scan_documents(connection: sqlite3.Connection) -> dict[str, object]:
    root_folder = Path(get_configured_root_folder(connection))
    scanned_at = utc_now()
    supported_documents: list[dict[str, object]] = []
    skipped = 0

    for file_path in sorted((path for path in root_folder.rglob("*") if path.is_file()), key=lambda p: p.as_posix()):
        suffix = file_path.suffix.lower()
        file_type = SUPPORTED_SUFFIXES.get(suffix)
        if file_type is None:
            skipped += 1
            continue

        relative_path = normalize_relative_path(root_folder, file_path)
        stat = file_path.stat()
        content_bytes = file_path.read_bytes()
        content = content_bytes.decode("utf-8", errors="replace")
        supported_documents.append(
            {
                "id": build_document_id(relative_path),
                "relative_path": relative_path,
                "file_type": file_type,
                "title": file_path.stem,
                "size_bytes": stat.st_size,
                "modified_at": _stat_to_iso_utc(stat.st_mtime),
                "content_hash": hashlib.sha1(content_bytes).hexdigest(),
                "content": content,
                "scanned_at": scanned_at,
            }
        )

    connection.execute("DELETE FROM documents")
    connection.executemany(
        """
        INSERT INTO documents (
            id, relative_path, file_type, title, size_bytes,
            modified_at, content_hash, content, scanned_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                document["id"],
                document["relative_path"],
                document["file_type"],
                document["title"],
                document["size_bytes"],
                document["modified_at"],
                document["content_hash"],
                document["content"],
                document["scanned_at"],
            )
            for document in supported_documents
        ],
    )
    create_audit_event(
        connection,
        action_id=None,
        event_type="documents_scanned",
        event_payload={
            "root_folder": str(root_folder),
            "found": len(supported_documents),
            "created": len(supported_documents),
            "skipped": skipped,
        },
        created_at=scanned_at,
    )
    return {
        "root_folder": str(root_folder),
        "found": len(supported_documents),
        "created": len(supported_documents),
        "skipped": skipped,
        "scanned_at": scanned_at,
    }


def list_documents(connection: sqlite3.Connection) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT id, relative_path, file_type, title, modified_at, scanned_at
        FROM documents
        ORDER BY relative_path ASC
        """
    ).fetchall()
    return [
        {
            "id": row["id"],
            "relative_path": row["relative_path"],
            "file_type": row["file_type"],
            "title": row["title"],
            "modified_at": row["modified_at"],
            "scanned_at": row["scanned_at"],
        }
        for row in rows
    ]


def get_document(connection: sqlite3.Connection, document_id: str) -> dict[str, object]:
    row = connection.execute(
        """
        SELECT id, relative_path, file_type, title, size_bytes, modified_at,
               content_hash, content, scanned_at
        FROM documents
        WHERE id = ?
        """,
        (document_id,),
    ).fetchone()

    if row is None:
        raise DocumentNotFoundError(document_id)

    return {
        "id": row["id"],
        "relative_path": row["relative_path"],
        "file_type": row["file_type"],
        "title": row["title"],
        "size_bytes": row["size_bytes"],
        "modified_at": row["modified_at"],
        "content_hash": row["content_hash"],
        "content": row["content"],
        "scanned_at": row["scanned_at"],
    }

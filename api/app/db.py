from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ALLOWED_ACTION_TYPES = (
    "stub_email_draft",
    "stub_calendar_event",
    "stub_export",
)
ALLOWED_STATUSES = ("preview", "approved")
ROOT_FOLDER_SETTING_KEY = "root_folder"
DOCUMENT_FILE_TYPES = ("md", "txt", "pdf", "docx")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "app.db"


def get_db_path() -> Path:
    raw_path = os.environ.get("APP_DB_PATH")
    return Path(raw_path) if raw_path else DEFAULT_DB_PATH


def documents_table_sql(table_name: str) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        id TEXT PRIMARY KEY,
        relative_path TEXT NOT NULL UNIQUE,
        file_type TEXT NOT NULL
            CHECK (file_type IN {DOCUMENT_FILE_TYPES}),
        title TEXT NOT NULL,
        size_bytes INTEGER NOT NULL,
        modified_at TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        content TEXT NOT NULL,
        scanned_at TEXT NOT NULL
    )
    """


def ensure_documents_table_schema(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table' AND name = 'documents'
        """
    ).fetchone()

    if row is None:
        connection.execute(documents_table_sql("documents"))
        return

    existing_sql = row[0] or ""
    if "'pdf'" in existing_sql and "'docx'" in existing_sql:
        return

    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute("DROP TABLE IF EXISTS documents_rebuild")
    connection.execute(documents_table_sql("documents_rebuild"))
    connection.execute(
        """
        INSERT INTO documents_rebuild (
            id, relative_path, file_type, title, size_bytes,
            modified_at, content_hash, content, scanned_at
        )
        SELECT id, relative_path, file_type, title, size_bytes,
               modified_at, content_hash, content, scanned_at
        FROM documents
        """
    )
    connection.execute("DROP TABLE documents")
    connection.execute("ALTER TABLE documents_rebuild RENAME TO documents")
    connection.execute("PRAGMA foreign_keys = ON")


def init_db() -> None:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS actions (
                id TEXT PRIMARY KEY,
                action_type TEXT NOT NULL
                    CHECK (action_type IN {ALLOWED_ACTION_TYPES}),
                title TEXT NOT NULL,
                preview_payload TEXT NOT NULL,
                status TEXT NOT NULL
                    CHECK (status IN {ALLOWED_STATUSES}),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                approved_at TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_id TEXT,
                event_type TEXT NOT NULL,
                event_payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (action_id) REFERENCES actions(id)
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_events_created_desc
            ON audit_events (created_at DESC, id DESC)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        ensure_documents_table_schema(connection)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS summary_artifacts (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                method TEXT NOT NULL
                    CHECK (method = 'extractive_v1'),
                source_content_hash TEXT NOT NULL,
                summary_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (document_id) REFERENCES documents(id)
            )
            """
        )
        connection.commit()


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(get_db_path())
    connection.row_factory = sqlite3.Row

    try:
        yield connection
        connection.commit()
    finally:
        connection.close()

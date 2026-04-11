from __future__ import annotations

import sqlite3
from pathlib import Path


def test_init_db_creates_block_a_tables(client, db_path: Path):
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            AND name IN ('app_settings', 'documents', 'summary_artifacts')
            ORDER BY name
            """
        ).fetchall()

    assert [row[0] for row in rows] == ["app_settings", "documents", "summary_artifacts"]


def test_get_root_folder_returns_null_when_not_configured(client):
    response = client.get("/settings/root-folder")

    assert response.status_code == 200
    assert response.json() == {"root_folder": None, "updated_at": None}


def test_put_root_folder_persists_setting_and_writes_audit_event(client, tmp_path: Path):
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()

    put_response = client.put("/settings/root-folder", json={"root_folder": str(notes_dir)})

    assert put_response.status_code == 200
    body = put_response.json()
    assert body["root_folder"] == str(notes_dir.resolve())
    assert body["updated_at"] is not None

    get_response = client.get("/settings/root-folder")
    assert get_response.status_code == 200
    assert get_response.json() == body

    audit_response = client.get("/audit")
    assert audit_response.status_code == 200
    audit_events = audit_response.json()
    assert audit_events[0]["event_type"] == "root_folder_updated"
    assert audit_events[0]["event_payload"] == {"root_folder": str(notes_dir.resolve())}


def test_put_root_folder_rejects_relative_path(client):
    response = client.put("/settings/root-folder", json={"root_folder": "notes"})

    assert response.status_code == 400
    assert response.json() == {"detail": "Root folder must be an absolute path."}


def test_put_root_folder_rejects_missing_directory(client, tmp_path: Path):
    missing_dir = tmp_path / "missing"

    response = client.put("/settings/root-folder", json={"root_folder": str(missing_dir)})

    assert response.status_code == 404
    assert response.json() == {"detail": "Root folder does not exist."}


def test_put_root_folder_rejects_file_path(client, tmp_path: Path):
    file_path = tmp_path / "notes.txt"
    file_path.write_text("hello", encoding="utf-8")

    response = client.put("/settings/root-folder", json={"root_folder": str(file_path)})

    assert response.status_code == 400
    assert response.json() == {"detail": "Root folder must be a directory."}

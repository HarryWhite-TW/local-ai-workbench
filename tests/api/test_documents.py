from __future__ import annotations

import hashlib
import shutil
import sqlite3
from pathlib import Path

from api.app.db import init_db
from tests.api.document_factories import write_blank_pdf, write_simple_docx, write_text_pdf

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "documents"


def copy_documents_fixture(tmp_path: Path) -> Path:
    destination = tmp_path / "documents"
    shutil.copytree(FIXTURES_DIR, destination)
    return destination


def test_scan_requires_root_folder_configuration(client):
    response = client.post("/documents/scan")

    assert response.status_code == 409
    assert response.json() == {"detail": "Root folder has not been configured."}


def test_scan_builds_documents_index_and_audit_event(client, tmp_path: Path):
    fixture_root = copy_documents_fixture(tmp_path)
    set_root_response = client.put("/settings/root-folder", json={"root_folder": str(fixture_root)})
    assert set_root_response.status_code == 200

    scan_response = client.post("/documents/scan")

    assert scan_response.status_code == 200
    body = scan_response.json()
    assert body["root_folder"] == str(fixture_root.resolve())
    assert body["found"] == 2
    assert body["created"] == 2
    assert body["skipped"] == 1
    assert body["scanned_at"] is not None

    documents_response = client.get("/documents")
    assert documents_response.status_code == 200
    documents = documents_response.json()
    assert [document["relative_path"] for document in documents] == ["sample_log.txt", "sample_note.md"]
    assert [document["file_type"] for document in documents] == ["txt", "md"]

    expected_ids = [
        f"doc_{hashlib.sha1(path.encode('utf-8')).hexdigest()[:16]}"
        for path in ["sample_log.txt", "sample_note.md"]
    ]
    assert [document["id"] for document in documents] == expected_ids

    audit_response = client.get("/audit")
    assert audit_response.status_code == 200
    audit_events = audit_response.json()
    assert audit_events[0]["event_type"] == "documents_scanned"
    assert audit_events[0]["event_payload"] == {
        "root_folder": str(fixture_root.resolve()),
        "found": 2,
        "created": 2,
        "skipped": 1,
    }


def test_get_document_returns_full_content(client, tmp_path: Path):
    fixture_root = copy_documents_fixture(tmp_path)
    client.put("/settings/root-folder", json={"root_folder": str(fixture_root)})
    client.post("/documents/scan")

    documents = client.get("/documents").json()
    document_id = next(document["id"] for document in documents if document["relative_path"] == "sample_note.md")

    response = client.get(f"/documents/{document_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["relative_path"] == "sample_note.md"
    assert body["file_type"] == "md"
    assert body["title"] == "sample_note"
    assert "# Sample Note" in body["content"]
    assert "This is a markdown fixture file for Block B." in body["content"]


def test_get_document_returns_404_for_unknown_id(client):
    response = client.get("/documents/doc_missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found."}


def test_init_db_rebuilds_legacy_documents_schema_for_pdf_docx(db_path: Path, monkeypatch):
    monkeypatch.setenv("APP_DB_PATH", str(db_path))

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE documents (
                id TEXT PRIMARY KEY,
                relative_path TEXT NOT NULL UNIQUE,
                file_type TEXT NOT NULL
                    CHECK (file_type IN ('md', 'txt')),
                title TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                modified_at TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                content TEXT NOT NULL,
                scanned_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO documents (
                id, relative_path, file_type, title, size_bytes,
                modified_at, content_hash, content, scanned_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "doc_legacy",
                "legacy.md",
                "md",
                "legacy",
                10,
                "2026-04-12T00:00:00Z",
                "hash",
                "legacy content",
                "2026-04-12T00:00:00Z",
            ),
        )
        connection.commit()

    init_db()

    with sqlite3.connect(db_path) as connection:
        schema_row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='documents'"
        ).fetchone()
        data_row = connection.execute("SELECT id, relative_path, file_type FROM documents").fetchone()

    assert schema_row is not None
    assert "'pdf'" in schema_row[0]
    assert "'docx'" in schema_row[0]
    assert data_row == ("doc_legacy", "legacy.md", "md")


def test_scan_indexes_pdf_and_docx_and_skips_empty_extracts(client, tmp_path: Path):
    root = tmp_path / "documents"
    root.mkdir()
    write_text_pdf(root / "report.pdf", "Quarterly PDF update with LaunchWindow milestone.")
    write_simple_docx(
        root / "brief.docx",
        ["Project brief paragraph one.", "Paragraph two mentions orchard planning."],
    )
    write_blank_pdf(root / "blank.pdf")

    client.put("/settings/root-folder", json={"root_folder": str(root)})
    scan_response = client.post("/documents/scan")

    assert scan_response.status_code == 200
    body = scan_response.json()
    assert body["found"] == 2
    assert body["created"] == 2
    assert body["skipped"] == 1

    documents = client.get("/documents").json()
    assert [document["relative_path"] for document in documents] == ["brief.docx", "report.pdf"]
    assert [document["file_type"] for document in documents] == ["docx", "pdf"]

    report_id = next(document["id"] for document in documents if document["relative_path"] == "report.pdf")
    brief_id = next(document["id"] for document in documents if document["relative_path"] == "brief.docx")

    report = client.get(f"/documents/{report_id}").json()
    brief = client.get(f"/documents/{brief_id}").json()

    assert "Quarterly PDF update with LaunchWindow milestone." in report["content"]
    assert "Project brief paragraph one." in brief["content"]
    assert "Paragraph two mentions orchard planning." in brief["content"]

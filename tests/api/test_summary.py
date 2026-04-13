from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from tests.api.document_factories import write_simple_docx


def prepare_scanned_root(client, tmp_path: Path, filename: str, content: str) -> str:
    root = tmp_path / "documents"
    root.mkdir()
    (root / filename).write_text(content, encoding="utf-8")
    put_response = client.put("/settings/root-folder", json={"root_folder": str(root)})
    assert put_response.status_code == 200
    scan_response = client.post("/documents/scan")
    assert scan_response.status_code == 200
    documents = client.get("/documents").json()
    return documents[0]["id"]


def test_post_summary_creates_artifact_and_audit_entry(client, tmp_path: Path, db_path: Path):
    document_id = prepare_scanned_root(
        client,
        tmp_path,
        "summary.md",
        "# Intro\n\n```python\nprint('ignore this block')\n```\n\nThis paragraph should be summarized. It is the first meaningful paragraph. It has a third sentence.",
    )

    response = client.post(f"/documents/{document_id}/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["id"].startswith("sum_")
    assert body["document_id"] == document_id
    assert body["method"] == "extractive_v1"
    assert "ignore this block" not in body["summary_text"]
    assert "\n" not in body["summary_text"]
    assert len(re.findall(r"[.!?。！？]", body["summary_text"])) <= 3

    audit_response = client.get("/audit")
    audit_events = audit_response.json()
    assert audit_events[0]["event_type"] == "summary_generated"
    assert audit_events[0]["event_payload"]["document_id"] == document_id
    assert audit_events[0]["event_payload"]["artifact_id"] == body["id"]

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT method, source_content_hash, summary_text
            FROM summary_artifacts
            WHERE id = ?
            """,
            (body["id"],),
        ).fetchone()
    assert row[0] == "extractive_v1"
    assert row[1] == body["source_content_hash"]
    assert row[2] == body["summary_text"]


def test_get_summary_returns_latest_artifact_for_document(client, tmp_path: Path):
    document_id = prepare_scanned_root(
        client,
        tmp_path,
        "latest.txt",
        "First sentence. Second sentence. Third sentence. Fourth sentence.",
    )

    first_response = client.post(f"/documents/{document_id}/summary")
    second_response = client.post(f"/documents/{document_id}/summary")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["id"] != second_response.json()["id"]

    get_response = client.get(f"/documents/{document_id}/summary")

    assert get_response.status_code == 200
    assert get_response.json()["id"] == second_response.json()["id"]


def test_get_summary_returns_404_when_document_exists_but_summary_missing(client, tmp_path: Path):
    document_id = prepare_scanned_root(client, tmp_path, "plain.txt", "Just one paragraph for testing.")

    response = client.get(f"/documents/{document_id}/summary")

    assert response.status_code == 404
    assert response.json() == {"detail": "Summary artifact not found."}


def test_summary_endpoints_return_404_when_document_is_missing(client):
    post_response = client.post("/documents/doc_missing/summary")
    get_response = client.get("/documents/doc_missing/summary")

    assert post_response.status_code == 404
    assert post_response.json() == {"detail": "Document not found."}
    assert get_response.status_code == 404
    assert get_response.json() == {"detail": "Document not found."}


def test_summary_can_be_generated_from_docx_extracted_content(client, tmp_path: Path):
    root = tmp_path / "documents"
    root.mkdir()
    write_simple_docx(
        root / "docx-summary.docx",
        [
            "This DOCX paragraph should be summarized.",
            "It includes a second sentence for extractive output.",
            "A third sentence keeps the artifact deterministic.",
        ],
    )
    client.put("/settings/root-folder", json={"root_folder": str(root)})
    client.post("/documents/scan")
    document_id = client.get("/documents").json()[0]["id"]

    response = client.post(f"/documents/{document_id}/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["method"] == "extractive_v1"
    assert "DOCX paragraph should be summarized." in body["summary_text"]


def test_summary_uses_normalized_ingested_docx_content(client, tmp_path: Path, monkeypatch):
    root = tmp_path / "documents"
    root.mkdir()
    write_simple_docx(root / "noisy-summary.docx", ["placeholder"])

    monkeypatch.setattr(
        "api.app.services.documents.extract_docx_text",
        lambda _path: "\x00 First sentence.\tSecond sentence.\r\nThird sentence.\x07",
    )

    client.put("/settings/root-folder", json={"root_folder": str(root)})
    scan_response = client.post("/documents/scan")
    assert scan_response.status_code == 200

    documents = client.get("/documents").json()
    document_id = documents[0]["id"]
    detail_response = client.get(f"/documents/{document_id}")

    assert detail_response.status_code == 200
    assert detail_response.json()["content"] == "First sentence. Second sentence.\nThird sentence."

    summary_response = client.post(f"/documents/{document_id}/summary")

    assert summary_response.status_code == 200
    assert summary_response.json()["summary_text"] == "First sentence. Second sentence. Third sentence."

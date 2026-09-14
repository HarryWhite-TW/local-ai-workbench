from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from api.app.services.decisions import ALGORITHM_REVISION, build_explicit_decisions


def prepare_scanned_document(client, tmp_path: Path, filename: str, content: str) -> tuple[str, Path]:
    root = tmp_path / "documents"
    root.mkdir()
    source_path = root / filename
    source_path.write_text(content, encoding="utf-8")
    assert client.put("/settings/root-folder", json={"root_folder": str(root)}).status_code == 200
    assert client.post("/documents/scan").status_code == 200
    return client.get("/documents").json()[0]["id"], source_path


def test_build_explicit_decisions_is_deterministic_and_source_linked():
    content = (
        "# Architecture\n"
        "\n"
        "Decision: Use SQLite for local persistence.\n"
        "We decided to keep source hashes with every artifact.\n"
        "Proposed decision: add a cloud database later.\n"
        "\n"
        "## Decisions\n"
        "- Export reviewed Markdown only.\n"
        "1. Keep original source documents unchanged.\n"
        "\n"
        "## Alternatives\n"
        "- Host the database remotely.\n"
    )

    first = build_explicit_decisions(content)
    second = build_explicit_decisions(content)

    assert first == second
    assert first == [
        {
            "decision_text": "Use SQLite for local persistence.",
            "evidence_quote": "Decision: Use SQLite for local persistence.",
            "source_line_start": 3,
            "source_line_end": 3,
        },
        {
            "decision_text": "keep source hashes with every artifact.",
            "evidence_quote": "We decided to keep source hashes with every artifact.",
            "source_line_start": 4,
            "source_line_end": 4,
        },
        {
            "decision_text": "Export reviewed Markdown only.",
            "evidence_quote": "- Export reviewed Markdown only.",
            "source_line_start": 8,
            "source_line_end": 8,
        },
        {
            "decision_text": "Keep original source documents unchanged.",
            "evidence_quote": "1. Keep original source documents unchanged.",
            "source_line_start": 9,
            "source_line_end": 9,
        },
    ]


def test_build_explicit_decisions_supports_chinese_and_excludes_non_decisions_and_code():
    content = (
        "決定：採用本機 SQLite。\n"
        "尚未決定：是否新增外部服務。\n"
        "Recommendation: use a remote queue.\n"
        "```text\n"
        "Decision: This example is not source evidence.\n"
        "```\n"
    )

    assert build_explicit_decisions(content) == [
        {
            "decision_text": "採用本機 SQLite。",
            "evidence_quote": "決定：採用本機 SQLite。",
            "source_line_start": 1,
            "source_line_end": 1,
        }
    ]


def test_decision_endpoints_persist_latest_artifact_and_audit_provenance(client, tmp_path: Path, db_path: Path):
    document_id, source_path = prepare_scanned_document(
        client,
        tmp_path,
        "architecture.md",
        "# Architecture\n\nDecision: Keep the workbench local-first.\n",
    )
    source_before = source_path.read_bytes()
    document = client.get(f"/documents/{document_id}").json()

    first_response = client.post(f"/documents/{document_id}/decisions")
    second_response = client.post(f"/documents/{document_id}/decisions")
    latest_response = client.get(f"/documents/{document_id}/decisions")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert latest_response.status_code == 200
    first = first_response.json()
    second = second_response.json()
    assert first["id"].startswith("dec_")
    assert second["id"] != first["id"]
    assert latest_response.json() == second
    assert first["method"] == "explicit_decision_v1"
    assert first["source_content_hash"] == document["content_hash"]
    assert first["decisions"] == second["decisions"]
    assert first["decisions"][0]["source_line_start"] == 3
    assert source_path.read_bytes() == source_before

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT method, source_content_hash, decisions_json FROM decision_artifacts WHERE id = ?",
            (second["id"],),
        ).fetchone()
    assert row is not None
    assert row[0] == "explicit_decision_v1"
    assert row[1] == document["content_hash"]
    assert json.loads(row[2]) == second["decisions"]

    event = client.get("/audit").json()[0]
    assert event["event_type"] == "decisions_extracted"
    assert event["event_payload"] == {
        "document_id": document_id,
        "artifact_id": second["id"],
        "method": "explicit_decision_v1",
        "algorithm_revision": ALGORITHM_REVISION,
        "source_content_hash": document["content_hash"],
        "decision_count": 1,
    }


def test_decision_endpoint_stores_reviewable_empty_result(client, tmp_path: Path):
    document_id, _ = prepare_scanned_document(
        client,
        tmp_path,
        "notes.txt",
        "This note describes an option but records no explicit outcome.",
    )

    response = client.post(f"/documents/{document_id}/decisions")

    assert response.status_code == 200
    assert response.json()["decisions"] == []


def test_decision_endpoints_distinguish_missing_artifact_and_missing_document(client, tmp_path: Path):
    document_id, _ = prepare_scanned_document(client, tmp_path, "notes.txt", "No decision is recorded here.")

    missing_artifact = client.get(f"/documents/{document_id}/decisions")
    missing_document_get = client.get("/documents/doc_missing/decisions")
    missing_document_post = client.post("/documents/doc_missing/decisions")

    assert missing_artifact.status_code == 404
    assert missing_artifact.json() == {"detail": "Decision artifact not found."}
    assert missing_document_get.status_code == 404
    assert missing_document_get.json() == {"detail": "Document not found."}
    assert missing_document_post.status_code == 404
    assert missing_document_post.json() == {"detail": "Document not found."}

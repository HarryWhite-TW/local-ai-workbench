from __future__ import annotations

from pathlib import Path

from api.app.services.obsidian_export import build_obsidian_document_summary_markdown


def sample_document() -> dict[str, object]:
    return {
        "id": "doc_123",
        "relative_path": "notes/demo_note.md",
        "file_type": "md",
        "title": "Demo Note",
        "size_bytes": 128,
        "modified_at": "2026-06-08T10:00:00Z",
        "content_hash": "hash_abc",
        "content": "Original source content should not be exported by default.",
        "scanned_at": "2026-06-08T10:01:00Z",
    }


def sample_summary() -> dict[str, object]:
    return {
        "id": "sum_123",
        "document_id": "doc_123",
        "method": "extractive_v1",
        "source_content_hash": "hash_abc",
        "summary_text": "This is the deterministic summary.",
        "created_at": "2026-06-08T10:02:00Z",
    }


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


def test_build_obsidian_markdown_contains_frontmatter_and_summary():
    markdown = build_obsidian_document_summary_markdown(
        sample_document(),
        sample_summary(),
        exported_at="2026-06-08T10:03:00Z",
    )

    assert markdown.startswith("---\n")
    assert 'source: "local-ai-workbench"' in markdown
    assert 'type: "document_summary"' in markdown
    assert 'document_id: "doc_123"' in markdown
    assert 'relative_path: "notes/demo_note.md"' in markdown
    assert 'summary_id: "sum_123"' in markdown
    assert "# Demo Note" in markdown
    assert "## Summary" in markdown
    assert "This is the deterministic summary." in markdown


def test_build_obsidian_markdown_does_not_export_full_source_content_by_default():
    markdown = build_obsidian_document_summary_markdown(
        sample_document(),
        sample_summary(),
        exported_at="2026-06-08T10:03:00Z",
    )

    assert "Original source content should not be exported by default." not in markdown
    assert "It does not modify the original source document." in markdown


def test_build_obsidian_markdown_includes_audit_context():
    markdown = build_obsidian_document_summary_markdown(
        sample_document(),
        sample_summary(),
        audit_events=[
            {
                "event_type": "root_folder_updated",
                "created_at": "2026-06-08T09:59:00Z",
            },
            {
                "event_type": "summary_generated",
                "created_at": "2026-06-08T10:02:00Z",
            },
        ],
        exported_at="2026-06-08T10:03:00Z",
    )

    assert "- `2026-06-08T09:59:00Z` — `root_folder_updated`" in markdown
    assert "- `2026-06-08T10:02:00Z` — `summary_generated`" in markdown


def test_build_obsidian_markdown_handles_missing_summary():
    markdown = build_obsidian_document_summary_markdown(
        sample_document(),
        None,
        exported_at="2026-06-08T10:03:00Z",
    )

    assert 'summary_id: ""' in markdown
    assert "No summary artifact provided." in markdown
    assert "- Method: `not_available`" in markdown


def test_build_obsidian_markdown_quotes_frontmatter_values():
    document = sample_document()
    document["title"] = 'Demo "Quoted" Note'

    markdown = build_obsidian_document_summary_markdown(
        document,
        sample_summary(),
        exported_at="2026-06-08T10:03:00Z",
    )

    assert 'title: "Demo \\"Quoted\\" Note"' in markdown
    assert '# Demo "Quoted" Note' in markdown


def test_get_obsidian_preview_returns_markdown_for_document_with_summary(client, tmp_path: Path):
    document_id = prepare_scanned_root(
        client,
        tmp_path,
        "demo.md",
        "This document should be summarized. It has useful local knowledge.",
    )
    summary_response = client.post(f"/documents/{document_id}/summary")
    assert summary_response.status_code == 200

    response = client.get(f"/documents/{document_id}/obsidian-preview")

    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == document_id
    assert body["has_summary"] is True
    assert "# demo" in body["markdown"]
    assert "This document should be summarized." in body["markdown"]
    assert "summary_generated" in body["markdown"]


def test_get_obsidian_preview_returns_markdown_without_summary(client, tmp_path: Path):
    document_id = prepare_scanned_root(
        client,
        tmp_path,
        "no-summary.txt",
        "This document has no generated summary yet.",
    )

    response = client.get(f"/documents/{document_id}/obsidian-preview")

    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == document_id
    assert body["has_summary"] is False
    assert "No summary artifact provided." in body["markdown"]


def test_get_obsidian_preview_returns_404_when_document_is_missing(client):
    response = client.get("/documents/doc_missing/obsidian-preview")

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found."}

def test_post_obsidian_export_requires_explicit_approval(client, tmp_path: Path):
    document_id = prepare_scanned_root(
        client,
        tmp_path,
        "approval-required.md",
        "This document should not be exported without explicit approval.",
    )
    export_folder = tmp_path / "obsidian"
    export_folder.mkdir()

    response = client.post(
        f"/documents/{document_id}/obsidian-export",
        json={"export_folder": str(export_folder), "approved": False},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Obsidian export requires approved=true after preview."}
    assert list(export_folder.iterdir()) == []


def test_post_obsidian_export_writes_markdown_file_after_approval(client, tmp_path: Path):
    document_id = prepare_scanned_root(
        client,
        tmp_path,
        "export-me.md",
        "This document should be exported. It has useful local knowledge.",
    )
    summary_response = client.post(f"/documents/{document_id}/summary")
    assert summary_response.status_code == 200
    export_folder = tmp_path / "obsidian"
    export_folder.mkdir()

    response = client.post(
        f"/documents/{document_id}/obsidian-export",
        json={"export_folder": str(export_folder), "approved": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == document_id
    assert body["has_summary"] is True
    assert body["filename"].endswith(f"{document_id}.md")
    assert body["bytes_written"] > 0

    export_path = Path(body["export_path"])
    assert export_path.exists()
    assert export_path.parent == export_folder.resolve()

    exported_text = export_path.read_text(encoding="utf-8")
    assert 'source: "local-ai-workbench"' in exported_text
    assert "This document should be exported." in exported_text
    assert "It does not modify the original source document." in exported_text

    audit_events = client.get("/audit").json()
    assert audit_events[0]["event_type"] == "obsidian_export_written"
    assert audit_events[0]["event_payload"]["document_id"] == document_id
    assert audit_events[0]["event_payload"]["export_path"] == str(export_path)


def test_post_obsidian_export_rejects_missing_export_folder(client, tmp_path: Path):
    document_id = prepare_scanned_root(
        client,
        tmp_path,
        "missing-folder.md",
        "This document should not be exported to a missing folder.",
    )

    response = client.post(
        f"/documents/{document_id}/obsidian-export",
        json={"export_folder": str(tmp_path / "missing"), "approved": True},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Export folder does not exist."}


def test_post_obsidian_export_refuses_to_overwrite_existing_file(client, tmp_path: Path):
    document_id = prepare_scanned_root(
        client,
        tmp_path,
        "no-overwrite.md",
        "This document should only be exported once.",
    )
    export_folder = tmp_path / "obsidian"
    export_folder.mkdir()

    first_response = client.post(
        f"/documents/{document_id}/obsidian-export",
        json={"export_folder": str(export_folder), "approved": True},
    )
    second_response = client.post(
        f"/documents/{document_id}/obsidian-export",
        json={"export_folder": str(export_folder), "approved": True},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    assert second_response.json() == {"detail": "Export file already exists."}


def test_post_obsidian_export_returns_404_when_document_is_missing(client, tmp_path: Path):
    export_folder = tmp_path / "obsidian"
    export_folder.mkdir()

    response = client.post(
        "/documents/doc_missing/obsidian-export",
        json={"export_folder": str(export_folder), "approved": True},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found."}

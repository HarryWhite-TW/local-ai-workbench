from __future__ import annotations

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

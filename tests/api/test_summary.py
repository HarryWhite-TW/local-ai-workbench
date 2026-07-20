from __future__ import annotations

import sqlite3
from pathlib import Path

from api.app.services.summary import (
    ALGORITHM_REVISION,
    KEY_POINT_MAX_LENGTH,
    ROLE_EVIDENCE_MAX_LENGTH,
    SUMMARY_MAX_LENGTH,
    TITLE_MAX_LENGTH,
    build_extractive_summary,
)
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


def prepare_scanned_docx_root(client, tmp_path: Path, filename: str, paragraphs: list[str]) -> str:
    root = tmp_path / "documents"
    root.mkdir()
    write_simple_docx(root / filename, paragraphs)
    put_response = client.put("/settings/root-folder", json={"root_folder": str(root)})
    assert put_response.status_code == 200
    scan_response = client.post("/documents/scan")
    assert scan_response.status_code == 200
    documents = client.get("/documents").json()
    return documents[0]["id"]


def test_post_summary_creates_structured_artifact_and_revisioned_audit_entry(client, tmp_path: Path, db_path: Path):
    document_id = prepare_scanned_root(
        client,
        tmp_path,
        "summary.md",
        (
            "# Intro\n\n"
            "This guide explains the bounded local summary workflow.\n\n"
            "- Preserve source provenance.\n"
            "- Keep original source documents unchanged.\n"
            "```python\nprint('ignore this block')\n```\n"
        ),
    )
    document = client.get(f"/documents/{document_id}").json()

    response = client.post(f"/documents/{document_id}/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["id"].startswith("sum_")
    assert body["document_id"] == document_id
    assert body["method"] == "extractive_v1"
    assert body["source_content_hash"] == document["content_hash"]
    assert body["summary_text"] == (
        "Title: Intro\n\n"
        "Role / purpose evidence:\n"
        "This guide explains the bounded local summary workflow.\n\n"
        "Key points:\n"
        "- Preserve source provenance.\n"
        "- Keep original source documents unchanged."
    )
    assert "ignore this block" not in body["summary_text"]

    audit_events = client.get("/audit").json()
    summary_event = audit_events[0]
    assert summary_event["event_type"] == "summary_generated"
    assert summary_event["event_payload"] == {
        "document_id": document_id,
        "artifact_id": body["id"],
        "method": "extractive_v1",
        "algorithm_revision": ALGORITHM_REVISION,
        "source_content_hash": document["content_hash"],
    }
    assert summary_event["event_payload"]["algorithm_revision"] != body["method"]

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT method, source_content_hash, summary_text FROM summary_artifacts WHERE id = ?",
            (body["id"],),
        ).fetchone()
    assert row == ("extractive_v1", document["content_hash"], body["summary_text"])


def test_get_summary_returns_latest_artifact_with_stable_text(client, tmp_path: Path):
    document_id = prepare_scanned_root(
        client,
        tmp_path,
        "latest.txt",
        "First sentence explains the source. Second sentence records a fact. Third sentence records another fact.",
    )

    first = client.post(f"/documents/{document_id}/summary").json()
    second = client.post(f"/documents/{document_id}/summary").json()
    latest = client.get(f"/documents/{document_id}/summary")

    assert latest.status_code == 200
    assert first["id"] != second["id"]
    assert first["created_at"] != second["created_at"]
    assert first["summary_text"].encode("utf-8") == second["summary_text"].encode("utf-8")
    assert latest.json()["id"] == second["id"]


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


def test_summary_uses_heading_prose_and_source_ordered_bullets():
    content = (
        "# Approval Gateway\n\n"
        "This gateway keeps local writes behind explicit review.\n\n"
        "- Preview the proposed change.\n"
        "- Bind approval to the exact request.\n"
        "- Reconcile durable evidence before another attempt."
    )

    summary = build_extractive_summary(content, file_type="md", scanned_title="ignored-filename")

    assert summary == (
        "Title: Approval Gateway\n\n"
        "Role / purpose evidence:\n"
        "This gateway keeps local writes behind explicit review.\n\n"
        "Key points:\n"
        "- Preview the proposed change.\n"
        "- Bind approval to the exact request.\n"
        "- Reconcile durable evidence before another attempt."
    )


def test_heading_followed_only_by_bullets_reports_role_insufficiency():
    summary = build_extractive_summary(
        "# Checklist\n\n- Validate the source identity.\n- Preserve the source hash.",
        file_type="md",
        scanned_title="checklist",
    )

    assert "Title: Checklist" in summary
    assert "Role / purpose evidence:\nInsufficient source content to identify role or purpose." in summary
    assert "- Validate the source identity." in summary
    assert "- Preserve the source hash." in summary


def test_multiple_headings_are_not_promoted_to_key_points():
    summary = build_extractive_summary(
        "# Main Title\n\nThis document records safe execution evidence.\n\n## Later Section\n\n- Keep one bounded attempt.",
        file_type="md",
        scanned_title="fallback",
    )

    assert summary.startswith("Title: Main Title")
    assert "Later Section" not in summary
    assert "- Keep one bounded attempt." in summary


def test_duplicate_sentences_and_list_items_are_removed_without_rewording():
    summary = build_extractive_summary(
        (
            "# Duplicate Test\n\n"
            "This document preserves exact source wording.\n\n"
            "- This document preserves exact source wording.\n"
            "- Record one durable result.\n"
            "- record one durable result!\n"
            "- Keep the original source unchanged."
        ),
        file_type="md",
        scanned_title="duplicate-test",
    )

    assert summary.count("This document preserves exact source wording.") == 1
    assert summary.casefold().count("record one durable result") == 1
    assert "- Keep the original source unchanged." in summary


def test_identical_long_source_units_render_only_one_key_point():
    long_unit = " ".join(f"duplicate-token-{index:03d}" for index in range(50))
    content = (
        "# Long Duplicate Test\n\n"
        "This document explains the long duplicate regression.\n\n"
        f"- {long_unit}\n"
        f"- {long_unit}\n"
        "- Preserve this later unique source point."
    )

    first = build_extractive_summary(content, file_type="md", scanned_title="long-duplicate")
    second = build_extractive_summary(content, file_type="md", scanned_title="long-duplicate")
    rendered_points = [line.removeprefix("- ") for line in first.splitlines() if line.startswith("- ")]

    assert len(rendered_points) == 2
    assert len(rendered_points) == len(set(rendered_points))
    assert rendered_points[0].startswith("duplicate-token-000")
    assert rendered_points[1] == "Preserve this later unique source point."
    assert all(len(point) <= KEY_POINT_MAX_LENGTH for point in rendered_points)
    assert len(first) <= SUMMARY_MAX_LENGTH
    assert first.encode("utf-8") == second.encode("utf-8")


def test_distinct_long_source_units_with_identical_truncation_render_once():
    shared_prefix = "shared-render-prefix-" + ("x" * (KEY_POINT_MAX_LENGTH + 40))
    first_long_unit = shared_prefix + ("a" * 360)
    second_long_unit = shared_prefix + ("b" * 360)
    content = (
        "# Rendered Duplicate Test\n\n"
        "This document explains the rendered duplicate regression.\n\n"
        f"- {first_long_unit}\n"
        f"- {second_long_unit}\n"
        "- Retain this final unique source point."
    )

    first = build_extractive_summary(content, file_type="md", scanned_title="rendered-duplicate")
    second = build_extractive_summary(content, file_type="md", scanned_title="rendered-duplicate")
    rendered_points = [line.removeprefix("- ") for line in first.splitlines() if line.startswith("- ")]

    assert len(rendered_points) == 2
    assert len(rendered_points) == len(set(rendered_points))
    assert rendered_points[0].startswith("shared-render-prefix-")
    assert rendered_points[1] == "Retain this final unique source point."
    assert all(len(point) <= KEY_POINT_MAX_LENGTH for point in rendered_points)
    assert len(first) <= SUMMARY_MAX_LENGTH
    assert first.encode("utf-8") == second.encode("utf-8")


def test_heading_only_and_extremely_short_sources_are_honest_about_insufficiency():
    heading_only = build_extractive_summary("# Only A Heading", file_type="md", scanned_title="fallback")
    extremely_short = build_extractive_summary("OK", file_type="txt", scanned_title="tiny-source")

    for summary in (heading_only, extremely_short):
        assert "Insufficient source content to identify role or purpose." in summary
        assert "- Insufficient source content to extract key points." in summary
    assert heading_only.startswith("Title: Only A Heading")
    assert extremely_short.startswith("Title: tiny-source")


def test_sparse_malformed_markdown_and_ordinary_txt_remain_supported():
    sparse = build_extractive_summary(
        "#Bad\n\n-\n\nUseful prose explains the recovery procedure.",
        file_type="md",
        scanned_title="sparse-note",
    )
    plain = build_extractive_summary(
        "Release notes explain the local correction. The source hash remains stable. No retry is automatic.",
        file_type="txt",
        scanned_title="release-notes",
    )

    assert sparse.startswith("Title: sparse-note")
    assert "Useful prose explains the recovery procedure." in sparse
    assert plain.startswith("Title: release-notes")
    assert "Role / purpose evidence:\nRelease notes explain the local correction." in plain
    assert "- The source hash remains stable." in plain
    assert "- No retry is automatic." in plain


def test_one_leading_bom_is_removed_but_interior_unicode_is_preserved():
    summary = build_extractive_summary(
        "\ufeff# Unicode Guide\n\nThis prose keeps an interior \ufeff marker and valid 雪 characters.\n\n- Preserve café text exactly.",
        file_type="md",
        scanned_title="fallback",
    )

    assert summary.startswith("Title: Unicode Guide")
    assert "interior \ufeff marker" in summary
    assert "valid 雪 characters" in summary
    assert "Preserve café text exactly." in summary


def test_closed_and_unclosed_fenced_code_are_excluded():
    closed = build_extractive_summary(
        "# Closed\n\nUseful prose explains the document.\n\n```python\nsecret_call()\n```\n\n- Keep this source point.",
        file_type="md",
        scanned_title="closed",
    )
    unclosed = build_extractive_summary(
        "# Unclosed\n\nUseful prose explains the document.\n\n- Keep the point before code.\n\n~~~text\nignored forever",
        file_type="md",
        scanned_title="unclosed",
    )

    assert "secret_call" not in closed
    assert "- Keep this source point." in closed
    assert "ignored forever" not in unclosed
    assert "- Keep the point before code." in unclosed


def test_process_arrow_block_is_a_source_grounded_key_point():
    summary = build_extractive_summary(
        "# Flow\n\nThis flow describes the bounded review path.\n\npreview -> approve -> export",
        file_type="md",
        scanned_title="flow",
    )

    assert "- preview -> approve -> export" in summary


def test_long_fields_and_complete_summary_respect_all_limits():
    title = "T" * 220
    role = "R" * 320
    points = "\n".join(f"- {str(index)} " + (chr(65 + index) * 340) for index in range(7))
    summary = build_extractive_summary(
        f"# {title}\n\n{role}\n\n{points}",
        file_type="md",
        scanned_title="fallback",
    )
    lines = summary.splitlines()
    rendered_title = lines[0].removeprefix("Title: ")
    rendered_role = lines[3]
    rendered_points = [line.removeprefix("- ") for line in lines[6:]]

    assert len(rendered_title) <= TITLE_MAX_LENGTH
    assert len(rendered_role) <= ROLE_EVIDENCE_MAX_LENGTH
    assert len(rendered_points) == 4
    assert all(len(point) <= KEY_POINT_MAX_LENGTH for point in rendered_points)
    assert len(summary) <= SUMMARY_MAX_LENGTH
    assert rendered_title.endswith("…")
    assert rendered_role.endswith("…")
    assert all(point.endswith("…") for point in rendered_points)


def test_coverage_strategy_is_deterministic_and_preserves_source_order():
    content = "# Coverage\n\nThis document provides broad source coverage.\n\n" + "\n".join(
        f"- Source point {index} contains distinct useful evidence." for index in range(1, 8)
    )

    first = build_extractive_summary(content, file_type="md", scanned_title="coverage")
    second = build_extractive_summary(content, file_type="md", scanned_title="coverage")

    assert first.encode("utf-8") == second.encode("utf-8")
    assert [line for line in first.splitlines() if line.startswith("- ")] == [
        "- Source point 1 contains distinct useful evidence.",
        "- Source point 3 contains distinct useful evidence.",
        "- Source point 5 contains distinct useful evidence.",
        "- Source point 7 contains distinct useful evidence.",
    ]


def test_summary_can_be_generated_from_docx_extracted_content(client, tmp_path: Path):
    document_id = prepare_scanned_docx_root(
        client,
        tmp_path,
        "docx-summary.docx",
        [
            "This DOCX paragraph explains the document purpose.",
            "It includes a second sentence for extractive output.",
            "A third sentence keeps the artifact deterministic.",
        ],
    )

    body = client.post(f"/documents/{document_id}/summary").json()

    assert body["method"] == "extractive_v1"
    assert body["summary_text"].startswith("Title: docx-summary")
    assert "Role / purpose evidence:\nThis DOCX paragraph explains the document purpose." in body["summary_text"]
    assert "- It includes a second sentence for extractive output." in body["summary_text"]


def test_summary_preserves_supported_opening_behavior_for_large_structured_docx(client, tmp_path: Path):
    document_id = prepare_scanned_docx_root(
        client,
        tmp_path,
        "structured-summary.docx",
        [
            "Reverb 職涯系統藍圖（終版）",
            (
                "本藍圖匯整了回音系統的工程實作計畫、人格系統設計草案，以及未來的職涯學習路線圖。"
                "內容以工程規格文件風格撰寫，確保每個部分可落地、可實作、可量化。"
            ),
            "1. 工程規格書（Project Specification）",
            "系統概述與目標",
            "這一段是後續正文，但不應該覆蓋前面第一段合格正文。",
        ],
    )

    summary = client.post(f"/documents/{document_id}/summary").json()["summary_text"]

    assert summary.startswith("Title: Reverb 職涯系統藍圖（終版）")
    assert "Role / purpose evidence:\n本藍圖匯整了回音系統的工程實作計畫" in summary


def test_summary_skips_header_like_docx_cluster_and_uses_supported_body(client, tmp_path: Path):
    document_id = prepare_scanned_docx_root(
        client,
        tmp_path,
        "header-heavy-summary.docx",
        [
            "📘《崩壞3・愛莉希雅人格系統 v3 技術規格書》",
            "🪪 檔案標籤區（File Header）",
            "[卷名]：崩壞3・愛莉希雅人格系統 v3 技術規格書·卷一",
            "[主題]：人格哲學與語氣原理",
            "[版本]：v3.0-2025.11.04",
            "🧭 摘要區（Abstract）",
            "卷一作為人格系統的精神基石，定義了愛莉希雅人格的哲學邏輯、語氣本源、行為倫理準則與人格框架。",
            "核心目標：",
        ],
    )

    summary = client.post(f"/documents/{document_id}/summary").json()["summary_text"]

    assert summary.startswith("Title: 📘《崩壞3・愛莉希雅人格系統 v3 技術規格書》")
    assert "Role / purpose evidence:\n卷一作為人格系統的精神基石" in summary
    assert "檔案標籤區" not in summary


def test_docx_without_supported_body_reports_insufficiency(client, tmp_path: Path):
    document_id = prepare_scanned_docx_root(
        client,
        tmp_path,
        "fallback-summary.docx",
        [
            "📘《崩壞3・愛莉希雅人格系統 v3 技術規格書》",
            "🪪 檔案標籤區（File Header）",
            "[卷名]：崩壞3・愛莉希雅人格系統 v3 技術規格書·卷一",
            "[主題]：人格哲學與語氣原理",
            "[版本]：v3.0-2025.11.04",
            "🧭 摘要區（Abstract）",
            "核心目標：",
            "延伸章節：",
        ],
    )

    summary = client.post(f"/documents/{document_id}/summary").json()["summary_text"]

    assert summary.startswith("Title: 📘《崩壞3・愛莉希雅人格系統 v3 技術規格書》")
    assert "Insufficient source content to identify role or purpose." in summary
    assert "- Insufficient source content to extract key points." in summary


def test_summary_uses_normalized_ingested_docx_content(client, tmp_path: Path, monkeypatch):
    root = tmp_path / "documents"
    root.mkdir()
    write_simple_docx(root / "noisy-summary.docx", ["placeholder"])
    monkeypatch.setattr(
        "api.app.services.documents.extract_docx_text",
        lambda _path: "\x00 First sentence explains the file.\tSecond sentence records evidence.\r\nThird sentence is stable.\x07",
    )

    client.put("/settings/root-folder", json={"root_folder": str(root)})
    assert client.post("/documents/scan").status_code == 200
    document_id = client.get("/documents").json()[0]["id"]
    detail = client.get(f"/documents/{document_id}").json()
    summary = client.post(f"/documents/{document_id}/summary").json()["summary_text"]

    assert detail["content"] == "First sentence explains the file. Second sentence records evidence.\nThird sentence is stable."
    assert summary == (
        "Title: noisy-summary\n\n"
        "Role / purpose evidence:\n"
        "First sentence explains the file.\n\n"
        "Key points:\n"
        "- Second sentence records evidence.\n"
        "- Third sentence is stable."
    )

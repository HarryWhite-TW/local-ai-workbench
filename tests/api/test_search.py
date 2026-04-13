from __future__ import annotations

from pathlib import Path

from tests.api.document_factories import write_simple_docx, write_text_pdf


def prepare_search_root(client, tmp_path: Path) -> None:
    root = tmp_path / "documents"
    (root / "nested").mkdir(parents=True)
    (root / "AlphaPlan.md").write_text(
        "# Alpha Plan\n\nThis file tracks orchard milestones and delivery notes.",
        encoding="utf-8",
    )
    (root / "nested" / "release-log.txt").write_text(
        "First line.\nSecond line mentions LaunchWindow in the content body.\nThird line stays searchable.",
        encoding="utf-8",
    )
    (root / "ignore.json").write_text('{"skip": true}', encoding="utf-8")

    put_response = client.put("/settings/root-folder", json={"root_folder": str(root)})
    assert put_response.status_code == 200
    scan_response = client.post("/documents/scan")
    assert scan_response.status_code == 200


def test_search_route_returns_200_and_does_not_conflict_with_document_route(client):
    response = client.get("/documents/search", params={"q": "anything"})

    assert response.status_code == 200
    assert response.json() == []


def test_search_matches_title_relative_path_and_content_case_insensitively(client, tmp_path: Path):
    prepare_search_root(client, tmp_path)

    title_response = client.get("/documents/search", params={"q": "alphaplan"})
    path_response = client.get("/documents/search", params={"q": "NESTED/RELEASE"})
    content_response = client.get("/documents/search", params={"q": "launchwindow"})

    assert title_response.status_code == 200
    assert path_response.status_code == 200
    assert content_response.status_code == 200

    title_match = title_response.json()
    path_match = path_response.json()
    content_match = content_response.json()

    assert len(title_match) == 1
    assert title_match[0]["title"] == "AlphaPlan"
    assert title_match[0]["snippet"].startswith("# Alpha Plan This file tracks orchard milestones")

    assert len(path_match) == 1
    assert path_match[0]["relative_path"] == "nested/release-log.txt"
    assert path_match[0]["snippet"].startswith("First line. Second line mentions LaunchWindow")

    assert len(content_match) == 1
    assert content_match[0]["relative_path"] == "nested/release-log.txt"
    assert "LaunchWindow" in content_match[0]["snippet"]


def test_search_returns_empty_list_for_blank_query_and_no_matches(client, tmp_path: Path):
    prepare_search_root(client, tmp_path)

    blank_response = client.get("/documents/search", params={"q": "   "})
    no_match_response = client.get("/documents/search", params={"q": "missing-keyword"})

    assert blank_response.status_code == 200
    assert blank_response.json() == []
    assert no_match_response.status_code == 200
    assert no_match_response.json() == []


def test_search_snippet_uses_fixed_single_line_window(client, tmp_path: Path):
    root = tmp_path / "documents"
    root.mkdir()
    (root / "long-note.txt").write_text(
        "A" * 60 + "\n\nNeedleToken appears in the middle of this long searchable paragraph.\n" + "B" * 120,
        encoding="utf-8",
    )
    client.put("/settings/root-folder", json={"root_folder": str(root)})
    client.post("/documents/scan")

    response = client.get("/documents/search", params={"q": "needletoken"})

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    snippet = results[0]["snippet"]
    assert "NeedleToken" in snippet
    assert "\n" not in snippet
    assert len(snippet) <= 121
    assert snippet.startswith("...")
    assert snippet.endswith("...")


def test_search_orders_results_by_match_scope_then_earliest_match_then_relative_path(client, tmp_path: Path):
    root = tmp_path / "documents"
    (root / "folder-keyword").mkdir(parents=True)
    (root / "folder-target").mkdir(parents=True)
    (root / "alpha").mkdir(parents=True)
    (root / "beta").mkdir(parents=True)
    (root / "TargetAlpha.txt").write_text("Document body without the special term.", encoding="utf-8")
    (root / "prefix-target.txt").write_text("Document body without the special term.", encoding="utf-8")
    (root / "folder-keyword" / "notes.txt").write_text("Path match only body.", encoding="utf-8")
    (root / "folder-target" / "notes.txt").write_text("Path match only body.", encoding="utf-8")
    (root / "alpha" / "content-a.txt").write_text("prefix keyword appears in this content body.", encoding="utf-8")
    (root / "beta" / "content-b.txt").write_text("prefix keyword appears in this content body.", encoding="utf-8")

    client.put("/settings/root-folder", json={"root_folder": str(root)})
    client.post("/documents/scan")

    response = client.get("/documents/search", params={"q": "keyword"})

    assert response.status_code == 200
    results = response.json()
    assert [result["relative_path"] for result in results] == [
        "folder-keyword/notes.txt",
        "alpha/content-a.txt",
        "beta/content-b.txt",
    ]

    title_response = client.get("/documents/search", params={"q": "target"})

    assert title_response.status_code == 200
    title_results = title_response.json()
    assert [result["relative_path"] for result in title_results[:3]] == [
        "TargetAlpha.txt",
        "prefix-target.txt",
        "folder-target/notes.txt",
    ]


def test_search_uses_document_start_snippet_only_for_title_or_path_only_matches(client, tmp_path: Path):
    prepare_search_root(client, tmp_path)

    title_response = client.get("/documents/search", params={"q": "alphaplan"})
    path_response = client.get("/documents/search", params={"q": "nested/release"})

    assert title_response.status_code == 200
    assert path_response.status_code == 200
    assert title_response.json()[0]["snippet"] == "# Alpha Plan This file tracks orchard milestones and delivery notes."
    assert path_response.json()[0]["snippet"] == (
        "First line. Second line mentions LaunchWindow in the content body. Third line stays searchable."
    )


def test_search_uses_content_snippet_when_title_or_path_and_content_both_match(client, tmp_path: Path):
    root = tmp_path / "documents"
    root.mkdir()
    (root / "NeedleToken-guide.txt").write_text(
        "A" * 60 + "\n\nNeedleToken appears in the middle of this long searchable paragraph.\n" + "B" * 120,
        encoding="utf-8",
    )
    client.put("/settings/root-folder", json={"root_folder": str(root)})
    client.post("/documents/scan")

    response = client.get("/documents/search", params={"q": "needletoken"})

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    snippet = results[0]["snippet"]
    assert "NeedleToken" in snippet
    assert snippet.startswith("...")
    assert snippet.endswith("...")


def test_search_matches_ingested_pdf_and_docx_content(client, tmp_path: Path):
    root = tmp_path / "documents"
    root.mkdir()
    write_text_pdf(root / "roadmap.pdf", "PDF roadmap includes DeltaLaunch milestone and owner notes.")
    write_simple_docx(root / "meeting.docx", ["Meeting notes paragraph.", "Docx mentions PineappleTrack token."])
    client.put("/settings/root-folder", json={"root_folder": str(root)})
    client.post("/documents/scan")

    pdf_response = client.get("/documents/search", params={"q": "deltalaunch"})
    docx_response = client.get("/documents/search", params={"q": "pineappletrack"})

    assert pdf_response.status_code == 200
    assert docx_response.status_code == 200
    assert pdf_response.json()[0]["file_type"] == "pdf"
    assert "DeltaLaunch" in pdf_response.json()[0]["snippet"]
    assert docx_response.json()[0]["file_type"] == "docx"
    assert "PineappleTrack" in docx_response.json()[0]["snippet"]


def test_search_uses_normalized_docx_ingestion_content(client, tmp_path: Path, monkeypatch):
    root = tmp_path / "documents"
    root.mkdir()
    write_simple_docx(root / "noisy.docx", ["placeholder"])

    monkeypatch.setattr(
        "api.app.services.documents.extract_docx_text",
        lambda _path: "\x00 First sentence.\tSecond sentence.\r\nThird sentence.\x07",
    )

    client.put("/settings/root-folder", json={"root_folder": str(root)})
    scan_response = client.post("/documents/scan")

    assert scan_response.status_code == 200

    search_response = client.get("/documents/search", params={"q": "third sentence"})

    assert search_response.status_code == 200
    results = search_response.json()
    assert len(results) == 1
    assert results[0]["file_type"] == "docx"
    assert results[0]["snippet"] == "First sentence. Second sentence. Third sentence."

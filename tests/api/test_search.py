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
    assert "AlphaPlan" in title_match[0]["snippet"]

    assert len(path_match) == 1
    assert path_match[0]["relative_path"] == "nested/release-log.txt"
    assert "nested/release-log.txt" in path_match[0]["snippet"]

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

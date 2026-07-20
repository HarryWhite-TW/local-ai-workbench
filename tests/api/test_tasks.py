from __future__ import annotations

import sqlite3
from pathlib import Path

TASK_REQUIREMENTS_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "task_requirements"


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

    put_response = client.put("/settings/root-folder", json={"root_folder": str(root)})
    assert put_response.status_code == 200
    scan_response = client.post("/documents/scan")
    assert scan_response.status_code == 200


def prepare_summary_root(client, tmp_path: Path, filename: str, content: str) -> str:
    root = tmp_path / "documents"
    root.mkdir()
    (root / filename).write_text(content, encoding="utf-8")

    put_response = client.put("/settings/root-folder", json={"root_folder": str(root)})
    assert put_response.status_code == 200
    scan_response = client.post("/documents/scan")
    assert scan_response.status_code == 200
    documents = client.get("/documents").json()
    return documents[0]["id"]


def prepare_fixture_document(client, tmp_path: Path, fixture_name: str, *, filename: str) -> str:
    content = (TASK_REQUIREMENTS_FIXTURES_DIR / fixture_name).read_text(encoding="utf-8")
    return prepare_summary_root(client, tmp_path, filename, content)


def test_run_find_documents_returns_completed_results_and_task_audit_events(client, tmp_path: Path):
    prepare_search_root(client, tmp_path)

    response = client.post("/tasks/run", json={"task_type": "find_documents", "query": "launchwindow"})

    assert response.status_code == 200
    body = response.json()
    assert body["task_type"] == "find_documents"
    assert body["status"] == "completed"
    assert body["result_kind"] == "document_search_results"
    assert body["source_document_id"] is None
    assert body["result"]["query"] == "launchwindow"
    assert len(body["result"]["matches"]) == 1
    assert body["result"]["matches"][0]["relative_path"] == "nested/release-log.txt"
    assert body["warnings"] == []
    assert body["error"] is None

    audit_events = client.get("/audit").json()
    assert audit_events[0]["event_type"] == "task_run_completed"
    assert audit_events[0]["event_payload"]["task_type"] == "find_documents"
    assert audit_events[0]["event_payload"]["match_count"] == 1
    assert audit_events[1]["event_type"] == "task_run_requested"
    assert audit_events[1]["event_payload"]["query"] == "launchwindow"
    assert audit_events[1]["action_id"] is None


def test_run_find_documents_returns_completed_with_warnings_for_empty_results(client, tmp_path: Path):
    prepare_search_root(client, tmp_path)

    response = client.post("/tasks/run", json={"task_type": "find_documents", "query": "missing-keyword"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed_with_warnings"
    assert body["result_kind"] == "document_search_results"
    assert body["result"]["query"] == "missing-keyword"
    assert body["result"]["matches"] == []
    assert body["warnings"] == ["No matches found."]
    assert body["error"] is None


def test_run_find_documents_returns_422_and_failed_audit_when_query_is_missing(client):
    response = client.post("/tasks/run", json={"task_type": "find_documents"})

    assert response.status_code == 422
    assert response.json() == {"detail": "Query is required for find_documents."}

    audit_events = client.get("/audit").json()
    assert audit_events[0]["event_type"] == "task_run_failed"
    assert audit_events[0]["event_payload"]["task_type"] == "find_documents"
    assert audit_events[0]["event_payload"]["error"] == "Query is required for find_documents."
    assert audit_events[1]["event_type"] == "task_run_requested"


def test_run_find_documents_returns_422_when_document_id_is_provided(client):
    response = client.post(
        "/tasks/run",
        json={"task_type": "find_documents", "query": "launchwindow", "document_id": "doc_any"},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Document ID is not allowed for find_documents."}

    audit_events = client.get("/audit").json()
    assert audit_events[0]["event_type"] == "task_run_failed"
    assert audit_events[0]["event_payload"]["task_type"] == "find_documents"
    assert audit_events[0]["event_payload"]["document_id"] == "doc_any"
    assert audit_events[0]["event_payload"]["error"] == "Document ID is not allowed for find_documents."
    assert audit_events[1]["event_type"] == "task_run_requested"


def test_run_summarize_selected_document_returns_artifact_and_creates_summary_artifact(client, tmp_path: Path, db_path: Path):
    document_id = prepare_summary_root(
        client,
        tmp_path,
        "summary.md",
        "# Intro\n\nThis paragraph should be summarized. It is the first meaningful paragraph. It has a third sentence.",
    )

    response = client.post(
        "/tasks/run",
        json={"task_type": "summarize_selected_document", "document_id": document_id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["task_type"] == "summarize_selected_document"
    assert body["status"] == "completed"
    assert body["result_kind"] == "summary_artifact"
    assert body["source_document_id"] == document_id
    assert body["warnings"] == []
    assert body["error"] is None

    artifact = body["result"]["artifact"]
    assert artifact["id"].startswith("sum_")
    assert artifact["document_id"] == document_id
    assert artifact["method"] == "extractive_v1"
    assert artifact["summary_text"].startswith("Title: Intro\n\nRole / purpose evidence:")
    assert "This paragraph should be summarized." in artifact["summary_text"]

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT id, method, source_content_hash FROM summary_artifacts WHERE id = ?",
            (artifact["id"],),
        ).fetchone()
    assert row is not None
    assert row[0] == artifact["id"]
    assert row[1] == "extractive_v1"
    assert row[2] == artifact["source_content_hash"]

    audit_events = client.get("/audit").json()
    assert audit_events[0]["event_type"] == "task_run_completed"
    assert audit_events[0]["event_payload"]["task_type"] == "summarize_selected_document"
    assert audit_events[0]["event_payload"]["artifact_id"] == artifact["id"]
    assert audit_events[0]["event_payload"]["method"] == "extractive_v1"
    assert audit_events[1]["event_type"] == "summary_generated"
    assert audit_events[1]["event_payload"]["artifact_id"] == artifact["id"]
    assert audit_events[1]["event_payload"]["method"] == "extractive_v1"
    assert audit_events[1]["event_payload"]["algorithm_revision"] == "structured_source_units_r1"
    assert audit_events[1]["event_payload"]["algorithm_revision"] != artifact["method"]
    assert audit_events[2]["event_type"] == "task_run_requested"


def test_run_summarize_selected_document_returns_422_when_document_id_is_missing(client):
    response = client.post("/tasks/run", json={"task_type": "summarize_selected_document"})

    assert response.status_code == 422
    assert response.json() == {"detail": "Document ID is required for summarize_selected_document."}

    audit_events = client.get("/audit").json()
    assert audit_events[0]["event_type"] == "task_run_failed"
    assert audit_events[0]["event_payload"]["task_type"] == "summarize_selected_document"
    assert audit_events[1]["event_type"] == "task_run_requested"


def test_run_summarize_selected_document_returns_422_when_query_is_provided(client):
    response = client.post(
        "/tasks/run",
        json={
            "task_type": "summarize_selected_document",
            "document_id": "doc_any",
            "query": "summarize this",
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Query is not allowed for summarize_selected_document."}

    audit_events = client.get("/audit").json()
    assert audit_events[0]["event_type"] == "task_run_failed"
    assert audit_events[0]["event_payload"]["task_type"] == "summarize_selected_document"
    assert audit_events[0]["event_payload"]["query"] == "summarize this"
    assert audit_events[0]["event_payload"]["error"] == "Query is not allowed for summarize_selected_document."
    assert audit_events[1]["event_type"] == "task_run_requested"


def test_run_summarize_selected_document_returns_404_for_unknown_document(client):
    response = client.post(
        "/tasks/run",
        json={"task_type": "summarize_selected_document", "document_id": "doc_missing"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found."}

    audit_events = client.get("/audit").json()
    assert audit_events[0]["event_type"] == "task_run_failed"
    assert audit_events[0]["event_payload"]["task_type"] == "summarize_selected_document"
    assert audit_events[0]["event_payload"]["document_id"] == "doc_missing"
    assert audit_events[1]["event_type"] == "task_run_requested"


def test_run_extract_requirements_returns_items_and_task_audit_events(client, tmp_path: Path, db_path: Path):
    document_id = prepare_fixture_document(
        client,
        tmp_path,
        "requirements_sample.md",
        filename="requirements_sample.md",
    )

    response = client.post(
        "/tasks/run",
        json={"task_type": "extract_requirements", "document_id": document_id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["task_type"] == "extract_requirements"
    assert body["status"] == "completed"
    assert body["result_kind"] == "requirements_list"
    assert body["source_document_id"] == document_id
    assert body["warnings"] == []
    assert body["error"] is None
    assert body["result"]["method"] == "extract_requirements_v1"
    assert body["result"]["items"] == [
        {
            "text": "The system must store scanned document metadata in SQLite.",
            "source_excerpt": "The system must store scanned document metadata in SQLite.",
            "match_reason": "requirements_heading",
        },
        {
            "text": "Search results shall include a snippet from the matched document.",
            "source_excerpt": "Search results shall include a snippet from the matched document.",
            "match_reason": "requirements_heading",
        },
        {
            "text": "The API is required to reject unsupported task types with a 422 response.",
            "source_excerpt": "The API is required to reject unsupported task types with a 422 response.",
            "match_reason": "requirements_heading",
        },
        {
            "text": "The task runner must return warnings when no matches are found.",
            "source_excerpt": "The task runner must return warnings when no matches are found.",
            "match_reason": "acceptance_criteria_heading",
        },
        {
            "text": "The prototype must remain localhost-only and single-user.",
            "source_excerpt": "The prototype must remain localhost-only and single-user.",
            "match_reason": "constraints_heading",
        },
    ]

    audit_events = client.get("/audit").json()
    assert audit_events[0]["event_type"] == "task_run_completed"
    assert audit_events[0]["event_payload"]["task_type"] == "extract_requirements"
    assert audit_events[0]["event_payload"]["result_kind"] == "requirements_list"
    assert audit_events[0]["event_payload"]["source_document_id"] == document_id
    assert audit_events[0]["event_payload"]["item_count"] == len(body["result"]["items"])
    assert audit_events[0]["event_payload"]["method"] == "extract_requirements_v1"
    assert audit_events[1]["event_type"] == "task_run_requested"

    with sqlite3.connect(db_path) as connection:
        summary_count = connection.execute("SELECT COUNT(*) FROM summary_artifacts").fetchone()[0]
    assert summary_count == 0


def test_run_extract_requirements_returns_completed_with_warnings_for_empty_result(client, tmp_path: Path, db_path: Path):
    document_id = prepare_fixture_document(
        client,
        tmp_path,
        "requirements_no_match.md",
        filename="requirements_no_match.md",
    )

    response = client.post(
        "/tasks/run",
        json={"task_type": "extract_requirements", "document_id": document_id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed_with_warnings"
    assert body["result_kind"] == "requirements_list"
    assert body["source_document_id"] == document_id
    assert body["result"]["method"] == "extract_requirements_v1"
    assert body["result"]["items"] == []
    assert body["warnings"] == ["No requirements found."]
    assert body["error"] is None

    audit_events = client.get("/audit").json()
    assert audit_events[0]["event_type"] == "task_run_completed"
    assert audit_events[0]["event_payload"]["task_type"] == "extract_requirements"
    assert audit_events[0]["event_payload"]["item_count"] == 0
    assert audit_events[0]["event_payload"]["warnings"] == ["No requirements found."]

    with sqlite3.connect(db_path) as connection:
        summary_count = connection.execute("SELECT COUNT(*) FROM summary_artifacts").fetchone()[0]
    assert summary_count == 0


def test_run_extract_requirements_returns_422_when_document_id_is_missing(client):
    response = client.post("/tasks/run", json={"task_type": "extract_requirements"})

    assert response.status_code == 422
    assert response.json() == {"detail": "Document ID is required for extract_requirements."}

    audit_events = client.get("/audit").json()
    assert audit_events[0]["event_type"] == "task_run_failed"
    assert audit_events[0]["event_payload"]["task_type"] == "extract_requirements"
    assert audit_events[0]["event_payload"]["error"] == "Document ID is required for extract_requirements."
    assert audit_events[1]["event_type"] == "task_run_requested"


def test_run_extract_requirements_returns_422_when_query_is_provided(client):
    response = client.post(
        "/tasks/run",
        json={
            "task_type": "extract_requirements",
            "document_id": "doc_any",
            "query": "find requirements",
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Query is not allowed for extract_requirements."}

    audit_events = client.get("/audit").json()
    assert audit_events[0]["event_type"] == "task_run_failed"
    assert audit_events[0]["event_payload"]["task_type"] == "extract_requirements"
    assert audit_events[0]["event_payload"]["query"] == "find requirements"
    assert audit_events[0]["event_payload"]["error"] == "Query is not allowed for extract_requirements."
    assert audit_events[1]["event_type"] == "task_run_requested"


def test_run_extract_requirements_returns_404_for_unknown_document(client):
    response = client.post(
        "/tasks/run",
        json={"task_type": "extract_requirements", "document_id": "doc_missing"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found."}

    audit_events = client.get("/audit").json()
    assert audit_events[0]["event_type"] == "task_run_failed"
    assert audit_events[0]["event_payload"]["task_type"] == "extract_requirements"
    assert audit_events[0]["event_payload"]["document_id"] == "doc_missing"
    assert audit_events[1]["event_type"] == "task_run_requested"


def test_run_task_returns_422_for_unsupported_task_type(client):
    response = client.post("/tasks/run", json={"task_type": "extract_todos", "document_id": "doc_any"})

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail[0]["loc"] == ["body", "task_type"]


def test_run_task_response_includes_warnings_and_error_fields(client, tmp_path: Path):
    prepare_search_root(client, tmp_path)

    response = client.post("/tasks/run", json={"task_type": "find_documents", "query": "missing-keyword"})

    assert response.status_code == 200
    body = response.json()
    assert "warnings" in body
    assert "error" in body
    assert body["warnings"] == ["No matches found."]
    assert body["error"] is None

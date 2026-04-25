from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from api.app.schemas import TaskRunRequest
from api.app.services.audit import create_audit_event
from api.app.services.documents import DocumentNotFoundError, get_document, search_documents
from api.app.services.summary import create_summary_artifact


class TaskRunError(Exception):
    """Raised when a task cannot be executed."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def normalize_query(query: str | None) -> str:
    if query is None:
        return ""
    return " ".join(query.split())


def build_task_request_payload(payload: TaskRunRequest) -> dict[str, Any]:
    request_payload: dict[str, Any] = {"task_type": payload.task_type}
    if payload.query is not None:
        request_payload["query"] = payload.query
    if payload.document_id is not None:
        request_payload["document_id"] = payload.document_id
    return request_payload


def create_task_requested_audit_event(
    connection: sqlite3.Connection,
    *,
    payload: TaskRunRequest,
    created_at: str,
) -> None:
    create_audit_event(
        connection,
        action_id=None,
        event_type="task_run_requested",
        event_payload=build_task_request_payload(payload),
        created_at=created_at,
    )


def create_task_completed_audit_event(
    connection: sqlite3.Connection,
    *,
    task_response: dict[str, Any],
) -> None:
    payload: dict[str, Any] = {
        "task_type": task_response["task_type"],
        "status": task_response["status"],
        "result_kind": task_response["result_kind"],
        "warnings": task_response["warnings"],
    }
    if task_response["source_document_id"] is not None:
        payload["source_document_id"] = task_response["source_document_id"]

    if task_response["task_type"] == "find_documents":
        payload["query"] = task_response["result"]["query"]
        payload["match_count"] = len(task_response["result"]["matches"])

    if task_response["task_type"] == "summarize_selected_document":
        artifact = task_response["result"]["artifact"]
        payload["document_id"] = artifact["document_id"]
        payload["artifact_id"] = artifact["id"]
        payload["method"] = artifact["method"]
        payload["source_content_hash"] = artifact["source_content_hash"]

    create_audit_event(
        connection,
        action_id=None,
        event_type="task_run_completed",
        event_payload=payload,
        created_at=task_response["created_at"],
    )


def create_task_failed_audit_event(
    connection: sqlite3.Connection,
    *,
    payload: TaskRunRequest,
    detail: str,
    created_at: str,
) -> None:
    event_payload = build_task_request_payload(payload)
    event_payload["error"] = detail
    create_audit_event(
        connection,
        action_id=None,
        event_type="task_run_failed",
        event_payload=event_payload,
        created_at=created_at,
    )


def build_find_documents_response(query: str, matches: list[dict[str, str]]) -> dict[str, Any]:
    warnings: list[str] = []
    status = "completed"
    if not matches:
        status = "completed_with_warnings"
        warnings.append("No matches found.")

    created_at = utc_now()
    return {
        "task_type": "find_documents",
        "status": status,
        "result_kind": "document_search_results",
        "source_document_id": None,
        "result": {
            "query": query,
            "matches": matches,
        },
        "warnings": warnings,
        "error": None,
        "created_at": created_at,
    }


def run_find_documents_task(connection: sqlite3.Connection, payload: TaskRunRequest) -> dict[str, Any]:
    if payload.document_id is not None:
        raise TaskRunError(status_code=422, detail="Document ID is not allowed for find_documents.")

    query = normalize_query(payload.query)
    if not query:
        raise TaskRunError(status_code=422, detail="Query is required for find_documents.")

    matches = search_documents(connection, query)
    return build_find_documents_response(query, matches)


def run_summarize_selected_document_task(
    connection: sqlite3.Connection,
    payload: TaskRunRequest,
) -> dict[str, Any]:
    if normalize_query(payload.query):
        raise TaskRunError(status_code=422, detail="Query is not allowed for summarize_selected_document.")

    document_id = payload.document_id
    if not document_id:
        raise TaskRunError(status_code=422, detail="Document ID is required for summarize_selected_document.")

    try:
        get_document(connection, document_id)
    except DocumentNotFoundError as exc:
        raise TaskRunError(status_code=404, detail="Document not found.") from exc

    artifact = create_summary_artifact(connection, document_id)
    return {
        "task_type": "summarize_selected_document",
        "status": "completed",
        "result_kind": "summary_artifact",
        "source_document_id": document_id,
        "result": {
            "artifact": artifact,
        },
        "warnings": [],
        "error": None,
        "created_at": utc_now(),
    }


def run_task(connection: sqlite3.Connection, payload: TaskRunRequest) -> dict[str, Any]:
    requested_at = utc_now()
    create_task_requested_audit_event(connection, payload=payload, created_at=requested_at)

    try:
        if payload.task_type == "find_documents":
            task_response = run_find_documents_task(connection, payload)
        elif payload.task_type == "summarize_selected_document":
            task_response = run_summarize_selected_document_task(connection, payload)
        else:
            raise TaskRunError(status_code=422, detail="Unsupported task type.")
    except TaskRunError as exc:
        create_task_failed_audit_event(connection, payload=payload, detail=exc.detail, created_at=utc_now())
        raise

    create_task_completed_audit_event(connection, task_response=task_response)
    return task_response

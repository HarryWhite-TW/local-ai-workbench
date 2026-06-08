from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from api.app.services.audit import create_audit_event, list_audit_events
from api.app.services.documents import get_document
from api.app.services.summary import SummaryArtifactNotFoundError, get_latest_summary_artifact

INVALID_FILENAME_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
WHITESPACE_PATTERN = re.compile(r"\s+")
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


class ObsidianExportApprovalRequiredError(Exception):
    """Raised when a local export write is requested without explicit approval."""


class InvalidObsidianExportFolderError(Exception):
    """Raised when the requested export folder is missing or invalid."""


class ObsidianExportFileExistsError(Exception):
    """Raised when the export target file already exists."""


def find_obsidian_vault_root(export_folder: Path) -> Path | None:
    current = export_folder
    while True:
        obsidian_config = current / ".obsidian"
        if obsidian_config.exists() and obsidian_config.is_dir():
            return current

        parent = current.parent
        if parent == current:
            return None

        current = parent


def build_export_destination_status(raw_export_folder: str) -> dict[str, Any]:
    export_folder_text = as_text(raw_export_folder)
    checked_at = utc_now_iso()

    if not export_folder_text:
        return {
            "export_folder": "",
            "exists": False,
            "is_directory": False,
            "can_export": False,
            "destination_type": "missing_folder",
            "human_status": "Folder path is empty.",
            "human_next_step": "Paste an existing folder path before exporting.",
            "vault_root": None,
            "obsidian_config_path": None,
            "checked_at": checked_at,
        }

    export_folder = Path(export_folder_text).expanduser()

    if not export_folder.exists():
        return {
            "export_folder": str(export_folder),
            "exists": False,
            "is_directory": False,
            "can_export": False,
            "destination_type": "missing_folder",
            "human_status": "This folder does not exist.",
            "human_next_step": "Create the folder or choose another existing destination before exporting.",
            "vault_root": None,
            "obsidian_config_path": None,
            "checked_at": checked_at,
        }

    resolved_export_folder = export_folder.resolve()

    if not resolved_export_folder.is_dir():
        return {
            "export_folder": str(resolved_export_folder),
            "exists": True,
            "is_directory": False,
            "can_export": False,
            "destination_type": "not_directory",
            "human_status": "This path is not a folder.",
            "human_next_step": "Choose an existing folder before exporting.",
            "vault_root": None,
            "obsidian_config_path": None,
            "checked_at": checked_at,
        }

    vault_root = find_obsidian_vault_root(resolved_export_folder)

    if vault_root is None:
        return {
            "export_folder": str(resolved_export_folder),
            "exists": True,
            "is_directory": True,
            "can_export": True,
            "destination_type": "plain_markdown_folder",
            "human_status": "This is a normal Markdown folder.",
            "human_next_step": "Export is allowed, but no Obsidian vault was detected.",
            "vault_root": None,
            "obsidian_config_path": None,
            "checked_at": checked_at,
        }

    obsidian_config_path = vault_root / ".obsidian"
    if vault_root == resolved_export_folder:
        return {
            "export_folder": str(resolved_export_folder),
            "exists": True,
            "is_directory": True,
            "can_export": True,
            "destination_type": "obsidian_vault_root",
            "human_status": "Obsidian vault detected.",
            "human_next_step": "Markdown exports written here should appear in this vault.",
            "vault_root": str(vault_root),
            "obsidian_config_path": str(obsidian_config_path),
            "checked_at": checked_at,
        }

    return {
        "export_folder": str(resolved_export_folder),
        "exists": True,
        "is_directory": True,
        "can_export": True,
        "destination_type": "inside_obsidian_vault",
        "human_status": "This folder is inside an Obsidian vault.",
        "human_next_step": "You can export Markdown here. It should appear in the detected vault under this folder.",
        "vault_root": str(vault_root),
        "obsidian_config_path": str(obsidian_config_path),
        "checked_at": checked_at,
    }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def as_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def yaml_string(value: Any) -> str:
    text = as_text(value)
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def build_frontmatter(
    document: Mapping[str, Any],
    summary_artifact: Mapping[str, Any] | None,
    *,
    exported_at: str,
) -> str:
    summary = summary_artifact or {}
    source_content_hash = as_text(summary.get("source_content_hash"), as_text(document.get("content_hash")))

    lines = [
        "---",
        'source: "local-ai-workbench"',
        'type: "document_summary"',
        f'exported_at: {yaml_string(exported_at)}',
        f'document_id: {yaml_string(document.get("id"))}',
        f'title: {yaml_string(document.get("title"))}',
        f'relative_path: {yaml_string(document.get("relative_path"))}',
        f'file_type: {yaml_string(document.get("file_type"))}',
        f'source_content_hash: {yaml_string(source_content_hash)}',
        f'summary_id: {yaml_string(summary.get("id"))}',
        f'summary_method: {yaml_string(summary.get("method"))}',
        "tags:",
        "  - local-ai-workbench",
        "  - document-summary",
        "---",
    ]
    return "\n".join(lines)


def build_audit_section(audit_events: Sequence[Mapping[str, Any]]) -> str:
    if not audit_events:
        return "- No audit events provided."

    lines = []
    for event in audit_events:
        event_type = as_text(event.get("event_type"), "unknown_event")
        created_at = as_text(event.get("created_at"), "unknown_time")
        lines.append(f"- `{created_at}` — `{event_type}`")
    return "\n".join(lines)


def select_document_audit_events(
    audit_events: Sequence[Mapping[str, Any]],
    *,
    document_id: str,
    summary_id: str | None = None,
) -> list[Mapping[str, Any]]:
    selected = []
    for event in audit_events:
        payload = event.get("event_payload")
        if not isinstance(payload, Mapping):
            continue
        if payload.get("document_id") == document_id:
            selected.append(event)
            continue
        if summary_id and payload.get("artifact_id") == summary_id:
            selected.append(event)
    return selected


def build_obsidian_document_summary_markdown(
    document: Mapping[str, Any],
    summary_artifact: Mapping[str, Any] | None = None,
    *,
    audit_events: Sequence[Mapping[str, Any]] | None = None,
    exported_at: str | None = None,
) -> str:
    export_timestamp = exported_at or utc_now_iso()
    title = as_text(document.get("title"), "Untitled document")
    relative_path = as_text(document.get("relative_path"), "unknown path")
    file_type = as_text(document.get("file_type"), "unknown")
    content_hash = as_text(document.get("content_hash"), "unknown")
    scanned_at = as_text(document.get("scanned_at"), "unknown")

    summary = summary_artifact or {}
    summary_text = as_text(summary.get("summary_text"), "No summary artifact provided.")
    summary_created_at = as_text(summary.get("created_at"), "unknown")
    summary_method = as_text(summary.get("method"), "not_available")

    frontmatter = build_frontmatter(document, summary_artifact, exported_at=export_timestamp)
    audit_section = build_audit_section(audit_events or [])

    sections = [
        frontmatter,
        "",
        f"# {title}",
        "",
        "## Source Document",
        "",
        f"- Relative path: `{relative_path}`",
        f"- File type: `{file_type}`",
        f"- Content hash: `{content_hash}`",
        f"- Scanned at: `{scanned_at}`",
        "",
        "## Summary",
        "",
        summary_text,
        "",
        "## Summary Metadata",
        "",
        f"- Method: `{summary_method}`",
        f"- Created at: `{summary_created_at}`",
        "",
        "## Audit Context",
        "",
        audit_section,
        "",
        "## Workbench Note",
        "",
        "This note was generated by Local AI Workbench as a one-way Markdown export preview.",
        "It does not modify the original source document.",
    ]

    return "\n".join(sections).strip() + "\n"


def build_obsidian_export_preview(connection: sqlite3.Connection, document_id: str) -> dict[str, Any]:
    document = get_document(connection, document_id)

    try:
        summary_artifact = get_latest_summary_artifact(connection, document_id)
        has_summary = True
    except SummaryArtifactNotFoundError:
        summary_artifact = None
        has_summary = False

    summary_id = as_text(summary_artifact.get("id")) if summary_artifact else None
    audit_events = select_document_audit_events(
        list_audit_events(connection),
        document_id=document_id,
        summary_id=summary_id,
    )
    markdown = build_obsidian_document_summary_markdown(
        document,
        summary_artifact,
        audit_events=audit_events,
    )

    return {
        "document_id": document_id,
        "has_summary": has_summary,
        "markdown": markdown,
    }


def sanitize_markdown_filename(title: Any, document_id: str) -> str:
    base = as_text(title, "document")
    base = INVALID_FILENAME_PATTERN.sub("-", base)
    base = WHITESPACE_PATTERN.sub(" ", base).strip(" .")
    if not base or base.upper() in WINDOWS_RESERVED_NAMES:
        base = "document"
    base = base[:80].rstrip(" .")
    if not base:
        base = "document"
    return f"{base}-{document_id}.md"


def validate_export_folder(raw_export_folder: str) -> Path:
    export_folder = Path(as_text(raw_export_folder)).expanduser()
    if not export_folder.exists():
        raise InvalidObsidianExportFolderError("Export folder does not exist.")
    if not export_folder.is_dir():
        raise InvalidObsidianExportFolderError("Export folder is not a directory.")
    return export_folder.resolve()


def write_obsidian_export(
    connection: sqlite3.Connection,
    document_id: str,
    *,
    export_folder: str,
    approved: bool,
) -> dict[str, Any]:
    if not approved:
        raise ObsidianExportApprovalRequiredError("Obsidian export requires approved=true after preview.")

    folder = validate_export_folder(export_folder)
    document = get_document(connection, document_id)
    preview = build_obsidian_export_preview(connection, document_id)
    filename = sanitize_markdown_filename(document.get("title"), document_id)
    export_path = (folder / filename).resolve()

    if export_path.parent != folder:
        raise InvalidObsidianExportFolderError("Export target escaped the selected folder.")
    if export_path.exists():
        raise ObsidianExportFileExistsError("Export file already exists.")

    markdown = str(preview["markdown"])
    with export_path.open("w", encoding="utf-8", newline="\n") as file:
        file.write(markdown)

    exported_at = utc_now_iso()
    create_audit_event(
        connection,
        action_id=None,
        event_type="obsidian_export_written",
        event_payload={
            "document_id": document_id,
            "export_path": str(export_path),
            "filename": filename,
            "has_summary": preview["has_summary"],
        },
        created_at=exported_at,
    )

    return {
        "document_id": document_id,
        "has_summary": preview["has_summary"],
        "export_path": str(export_path),
        "filename": filename,
        "bytes_written": len(markdown.encode("utf-8")),
        "exported_at": exported_at,
    }

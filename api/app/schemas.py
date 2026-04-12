from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ActionType = Literal["stub_email_draft", "stub_calendar_event", "stub_export"]
ActionStatus = Literal["preview", "approved"]


class ActionPreviewCreateRequest(BaseModel):
    action_type: ActionType
    title: str = Field(min_length=1, max_length=200)
    preview_payload: dict[str, Any]


class ActionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    action_type: ActionType
    title: str
    status: ActionStatus
    preview_payload: dict[str, Any]
    created_at: str
    updated_at: str
    approved_at: str | None


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    action_id: str | None
    event_type: str
    event_payload: dict[str, Any]
    created_at: str


class HealthResponse(BaseModel):
    status: Literal["ok"]


class RootFolderUpdateRequest(BaseModel):
    root_folder: str = Field(min_length=1)


class RootFolderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_folder: str | None
    updated_at: str | None


class DocumentScanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_folder: str
    found: int
    created: int
    skipped: int
    scanned_at: str


class DocumentListItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    relative_path: str
    file_type: Literal["md", "txt"]
    title: str
    modified_at: str
    scanned_at: str


class DocumentSearchResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    relative_path: str
    title: str
    file_type: Literal["md", "txt"]
    snippet: str


class DocumentDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    relative_path: str
    file_type: Literal["md", "txt"]
    title: str
    size_bytes: int
    modified_at: str
    content_hash: str
    content: str
    scanned_at: str


class SummaryArtifactResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    document_id: str
    method: Literal["extractive_v1"]
    source_content_hash: str
    summary_text: str
    created_at: str

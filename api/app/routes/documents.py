from fastapi import APIRouter, HTTPException, status

from api.app.db import get_connection
from api.app.schemas import (
    DocumentDetailResponse,
    DocumentListItemResponse,
    ObsidianExportPreviewResponse,
    DocumentSearchResultResponse,
    DocumentScanResponse,
    SummaryArtifactResponse,
)
from api.app.services.documents import (
    DocumentNotFoundError,
    RootFolderNotConfiguredError,
    get_document,
    list_documents,
    scan_documents,
    search_documents,
)
from api.app.services.obsidian_export import build_obsidian_export_preview
from api.app.services.settings import InvalidRootFolderError
from api.app.services.summary import (
    SummaryArtifactNotFoundError,
    create_summary_artifact,
    get_latest_summary_artifact,
)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/scan", response_model=DocumentScanResponse)
def post_documents_scan() -> DocumentScanResponse:
    with get_connection() as connection:
        try:
            result = scan_documents(connection)
        except RootFolderNotConfiguredError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except InvalidRootFolderError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return DocumentScanResponse(**result)


@router.get("", response_model=list[DocumentListItemResponse])
def get_documents() -> list[DocumentListItemResponse]:
    with get_connection() as connection:
        return [DocumentListItemResponse(**document) for document in list_documents(connection)]


@router.get("/search", response_model=list[DocumentSearchResultResponse])
def get_document_search_results(q: str) -> list[DocumentSearchResultResponse]:
    with get_connection() as connection:
        return [DocumentSearchResultResponse(**result) for result in search_documents(connection, q)]


@router.get("/{document_id}/obsidian-preview", response_model=ObsidianExportPreviewResponse)
def get_document_obsidian_preview(document_id: str) -> ObsidianExportPreviewResponse:
    with get_connection() as connection:
        try:
            preview = build_obsidian_export_preview(connection, document_id)
        except DocumentNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.") from exc
    return ObsidianExportPreviewResponse(**preview)


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document_by_id(document_id: str) -> DocumentDetailResponse:
    with get_connection() as connection:
        try:
            document = get_document(connection, document_id)
        except DocumentNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.") from exc
    return DocumentDetailResponse(**document)


@router.post("/{document_id}/summary", response_model=SummaryArtifactResponse)
def post_document_summary(document_id: str) -> SummaryArtifactResponse:
    with get_connection() as connection:
        try:
            artifact = create_summary_artifact(connection, document_id)
        except DocumentNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.") from exc
    return SummaryArtifactResponse(**artifact)


@router.get("/{document_id}/summary", response_model=SummaryArtifactResponse)
def get_document_summary(document_id: str) -> SummaryArtifactResponse:
    with get_connection() as connection:
        try:
            artifact = get_latest_summary_artifact(connection, document_id)
        except DocumentNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.") from exc
        except SummaryArtifactNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Summary artifact not found.",
            ) from exc
    return SummaryArtifactResponse(**artifact)

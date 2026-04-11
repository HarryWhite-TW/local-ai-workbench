from fastapi import APIRouter, HTTPException, status

from api.app.db import get_connection
from api.app.schemas import DocumentDetailResponse, DocumentListItemResponse, DocumentScanResponse
from api.app.services.documents import (
    DocumentNotFoundError,
    RootFolderNotConfiguredError,
    get_document,
    list_documents,
    scan_documents,
)
from api.app.services.settings import InvalidRootFolderError

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


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document_by_id(document_id: str) -> DocumentDetailResponse:
    with get_connection() as connection:
        try:
            document = get_document(connection, document_id)
        except DocumentNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.") from exc
    return DocumentDetailResponse(**document)

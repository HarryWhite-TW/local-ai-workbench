from fastapi import APIRouter, HTTPException

from api.app.db import get_connection
from api.app.schemas import RootFolderResponse, RootFolderUpdateRequest
from api.app.services.settings import (
    InvalidRootFolderError,
    get_root_folder_setting,
    set_root_folder_setting,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/root-folder", response_model=RootFolderResponse)
def get_root_folder() -> RootFolderResponse:
    with get_connection() as connection:
        result = get_root_folder_setting(connection)
    return RootFolderResponse(**result)


@router.put("/root-folder", response_model=RootFolderResponse)
def put_root_folder(payload: RootFolderUpdateRequest) -> RootFolderResponse:
    with get_connection() as connection:
        try:
            result = set_root_folder_setting(connection, payload.root_folder)
        except InvalidRootFolderError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return RootFolderResponse(**result)


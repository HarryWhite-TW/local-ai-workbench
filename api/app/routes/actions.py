from fastapi import APIRouter, HTTPException, status

from api.app.db import get_connection
from api.app.schemas import ActionPreviewCreateRequest, ActionResponse
from api.app.services.actions import (
    ActionNotFoundError,
    ActionStateError,
    approve_action,
    create_preview_action,
    list_actions,
)

router = APIRouter(prefix="/actions", tags=["actions"])


@router.get("", response_model=list[ActionResponse])
def get_actions() -> list[ActionResponse]:
    with get_connection() as connection:
        return [ActionResponse(**action) for action in list_actions(connection)]


@router.post("/preview", response_model=ActionResponse, status_code=status.HTTP_201_CREATED)
def post_action_preview(payload: ActionPreviewCreateRequest) -> ActionResponse:
    with get_connection() as connection:
        action = create_preview_action(
            connection,
            action_type=payload.action_type,
            title=payload.title,
            preview_payload=payload.preview_payload,
        )
    return ActionResponse(**action)


@router.post("/{action_id}/approve", response_model=ActionResponse)
def post_action_approve(action_id: str) -> ActionResponse:
    with get_connection() as connection:
        try:
            action = approve_action(connection, action_id)
        except ActionNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found.") from exc
        except ActionStateError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Action is not in preview state.",
            ) from exc
    return ActionResponse(**action)


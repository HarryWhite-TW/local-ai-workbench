from fastapi import APIRouter, HTTPException

from api.app.db import get_connection
from api.app.schemas import TaskRunRequest, TaskRunResponse
from api.app.services.tasks import TaskRunError, run_task

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("/run", response_model=TaskRunResponse)
def post_task_run(payload: TaskRunRequest) -> TaskRunResponse:
    result: dict | None = None
    task_error: TaskRunError | None = None

    with get_connection() as connection:
        try:
            result = run_task(connection, payload)
        except TaskRunError as exc:
            task_error = exc

    if task_error is not None:
        raise HTTPException(status_code=task_error.status_code, detail=task_error.detail) from task_error

    assert result is not None
    return TaskRunResponse(**result)

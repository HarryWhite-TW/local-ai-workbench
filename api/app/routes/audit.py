from fastapi import APIRouter

from api.app.db import get_connection
from api.app.schemas import AuditEventResponse
from api.app.services.audit import list_audit_events

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditEventResponse])
def get_audit() -> list[AuditEventResponse]:
    with get_connection() as connection:
        return [AuditEventResponse(**event) for event in list_audit_events(connection)]


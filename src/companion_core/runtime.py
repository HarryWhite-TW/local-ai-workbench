"""Only execution facts cross this boundary; acceptance is not a runtime event."""
from dataclasses import dataclass
from enum import Enum
from typing import Iterator, Protocol

from .domain import Authority, Failure


class RuntimeFailure(RuntimeError):
    """Adapter-derived reason only; never a provider response body."""

    def __init__(self, reason: Failure):
        self.reason = reason
        super().__init__(reason.value)


class EventKind(str, Enum):
    SESSION = "session_bound"
    INSPECTING = "inspecting_repository"
    RECEIVING = "receiving_result"
    COMPLETED = "execution_complete"
    FAILED = "execution_failed"
    CANCELLED = "execution_cancelled"


@dataclass(frozen=True)
class Request:
    intent: str
    workspace: str
    authority: Authority


@dataclass(frozen=True)
class RuntimeEvent:
    kind: EventKind
    session_id: str | None = None
    text: str | None = None


class Runtime(Protocol):
    provider_id: str

    def run(self, request: Request) -> Iterator[RuntimeEvent]: ...

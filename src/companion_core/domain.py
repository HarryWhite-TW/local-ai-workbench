from dataclasses import dataclass
from enum import Enum


class Authority(str, Enum):
    NONE = "NONE"
    READ_ONLY = "READ_ONLY"


class Execution(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Acceptance(str, Enum):
    UNREVIEWED = "UNREVIEWED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class Failure(str, Enum):
    UNKNOWN = "unknown"
    AUTHENTICATION = "authentication_unavailable"
    TIMEOUT = "runtime_timeout"
    PROTOCOL = "protocol_incompatibility"
    POLICY = "policy_mismatch"
    CONNECTION = "runtime_connection_loss"
    INTERRUPTED = "local_interruption_unconfirmed"


@dataclass(frozen=True)
class Task:
    id: str
    intent: str
    workspace: str
    provider: str
    authority: Authority
    execution: Execution = Execution.CREATED
    session_id: str | None = None
    result: str | None = None
    acceptance: Acceptance = Acceptance.UNREVIEWED
    reviewer: str | None = None
    failure: Failure | None = None

    @property
    def state(self) -> str:
        if self.execution == Execution.COMPLETED:
            return ("RESULT_PENDING_REVIEW" if self.acceptance == Acceptance.UNREVIEWED
                    else self.acceptance.value)
        return self.execution.value


@dataclass(frozen=True)
class Progress:
    task_id: str
    stage: str

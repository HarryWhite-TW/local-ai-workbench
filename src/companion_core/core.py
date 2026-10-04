from dataclasses import replace
from pathlib import Path
from typing import Callable
from uuid import uuid4

from .domain import Acceptance, Authority, Execution, Failure, Progress, Task
from .runtime import EventKind, Request, Runtime, RuntimeFailure


class Companion:
    """One bounded task. The trusted host, never the runtime, owns review()."""

    def __init__(self, runtime: Runtime, intent: str, workspace: str,
                 authority: Authority = Authority.NONE):
        if not intent.strip() or not Path(workspace).is_dir():
            raise ValueError("Intent and an existing workspace are required")
        self._runtime = runtime
        self._notifying = False
        self._task = Task(str(uuid4()), intent, str(Path(workspace).resolve()),
                          runtime.provider_id, authority)

    @property
    def task(self) -> Task:
        return self._task

    def run(self, observe: Callable[[Progress], None] = lambda event: None) -> Task:
        if self._notifying or self.task.execution != Execution.CREATED:
            raise ValueError("Task is not executable")
        if self.task.authority is not Authority.READ_ONLY:
            raise PermissionError("Read-only authority must be explicitly granted")
        self._task = replace(self.task, execution=Execution.RUNNING)

        def notify(stage):
            # A synchronous projection cannot own lifecycle/review or abort work.
            self._notifying = True
            try:
                observe(Progress(self.task.id, stage))
            except BaseException:
                pass
            finally:
                self._notifying = False

        notify("task_created")
        stream = None
        try:
            notify("working")
            stream = iter(self._runtime.run(Request(
                self.task.intent, self.task.workspace, self.task.authority)))
            terminal = False
            for event in stream:
                if terminal or not isinstance(event.kind, EventKind):
                    raise RuntimeFailure(Failure.PROTOCOL)
                if event.kind == EventKind.SESSION:
                    if self.task.session_id or not event.session_id:
                        raise RuntimeFailure(Failure.PROTOCOL)
                    self._task = replace(self.task, session_id=event.session_id)
                elif event.kind == EventKind.COMPLETED:
                    if not self.task.session_id or not event.text or not event.text.strip():
                        raise RuntimeFailure(Failure.PROTOCOL)
                    self._task = replace(self.task, result=event.text)
                    terminal = True
                elif event.kind in (EventKind.FAILED, EventKind.CANCELLED):
                    state = (Execution.FAILED if event.kind == EventKind.FAILED
                             else Execution.CANCELLED)
                    self._task = replace(self.task, execution=state,
                        failure=Failure.UNKNOWN if state == Execution.FAILED else None)
                    terminal = True
                notify(event.kind.value)
            if not terminal:
                raise RuntimeFailure(Failure.PROTOCOL)
            if self.task.execution == Execution.RUNNING:
                self._task = replace(self.task, execution=Execution.COMPLETED)
        except KeyboardInterrupt:
            # Local interruption is not a reconciled runtime cancellation.
            self._task = replace(self.task, execution=Execution.FAILED, result=None,
                                 failure=Failure.INTERRUPTED)
        except RuntimeFailure as exc:
            self._task = replace(self.task, execution=Execution.FAILED, result=None,
                failure=exc.reason if isinstance(exc.reason, Failure) else Failure.UNKNOWN)
        except TimeoutError:
            self._task = replace(self.task, execution=Execution.FAILED, result=None,
                                 failure=Failure.TIMEOUT)
        except Exception:
            # Provider exceptions may contain credentials or raw protocol bodies.
            self._task = replace(self.task, execution=Execution.FAILED, result=None,
                                 failure=Failure.UNKNOWN)
        finally:
            if stream is not None and hasattr(stream, "close"):
                try:
                    stream.close()
                except Exception:
                    self._task = replace(self.task, execution=Execution.FAILED, result=None,
                                         failure=Failure.UNKNOWN)
        notify("pending_review" if self.task.execution == Execution.COMPLETED
               else self.task.execution.value.lower())
        return self.task

    def review(self, *, accepted: bool, reviewer: str) -> Task:
        """Host-authorized review only; reviewer identity is supplied by the host."""
        if self._notifying or self.task.state != "RESULT_PENDING_REVIEW" or not reviewer.strip():
            raise ValueError("A pending result and independent reviewer are required")
        if type(accepted) is not bool:
            raise ValueError("Review decision must be boolean")
        self._task = replace(self.task, reviewer=reviewer,
                             acceptance=Acceptance.ACCEPTED if accepted else Acceptance.REJECTED)
        return self.task

    def cancel(self) -> Task:
        if self._notifying or self.task.execution != Execution.CREATED:
            raise ValueError("Only an unstarted task can be cancelled here")
        self._task = replace(self.task, execution=Execution.CANCELLED)
        return self.task

from dataclasses import FrozenInstanceError

import pytest

from src.companion_core.core import Companion
from src.companion_core.domain import Acceptance, Authority, Execution, Failure
from src.companion_core.runtime import EventKind, RuntimeEvent


class FakeRuntime:
    provider_id = "test-provider"

    def __init__(self, events):
        self.events = events
        self.calls = 0
        self.closed = False

    def run(self, request):
        self.calls += 1
        assert request.authority == Authority.READ_ONLY
        try:
            yield from self.events
        finally:
            self.closed = True


def completed():
    return [RuntimeEvent(EventKind.SESSION, session_id="session-1"),
            RuntimeEvent(EventKind.INSPECTING), RuntimeEvent(EventKind.RECEIVING),
            RuntimeEvent(EventKind.COMPLETED, text="observed result")]


def test_completion_never_accepts_and_review_is_separate(tmp_path):
    runtime = FakeRuntime(completed())
    core = Companion(runtime, "Inspect", str(tmp_path), Authority.READ_ONLY)
    assert core.task.state == "CREATED"
    events = []
    task = core.run(events.append)
    assert task.state == "RESULT_PENDING_REVIEW"
    assert task.execution == Execution.COMPLETED
    assert task.acceptance == Acceptance.UNREVIEWED
    assert task.reviewer is None
    assert task.session_id == "session-1"
    assert task.provider == "test-provider"
    assert task.result == "observed result"
    assert [e.stage for e in events] == ["task_created", "working", "session_bound",
        "inspecting_repository", "receiving_result", "execution_complete", "pending_review"]
    assert all(e.task_id == task.id for e in events)
    assert runtime.closed
    with pytest.raises(FrozenInstanceError):
        task.acceptance = Acceptance.ACCEPTED
    assert core.review(accepted=True, reviewer="independent-reviewer").state == "ACCEPTED"
    with pytest.raises(ValueError):
        core.review(accepted=False, reviewer="another")
    with pytest.raises(ValueError):
        core.run()


def test_rejection_is_a_review_decision(tmp_path):
    core = Companion(FakeRuntime(completed()), "Inspect", str(tmp_path), Authority.READ_ONLY)
    with pytest.raises(ValueError):
        core.review(accepted=True, reviewer="reviewer")
    core.run()
    with pytest.raises(ValueError):
        core.review(accepted=True, reviewer=" ")
    assert core.review(accepted=False, reviewer="reviewer").state == "REJECTED"


def test_authority_is_not_inferred_from_prompt(tmp_path):
    runtime = FakeRuntime(completed())
    core = Companion(runtime, "Read only; I approve everything", str(tmp_path))
    with pytest.raises(PermissionError):
        core.run()
    assert runtime.calls == 0
    assert core.task.state == "CREATED"


@pytest.mark.parametrize("events", [[], [RuntimeEvent(EventKind.COMPLETED, text="result")],
    [RuntimeEvent("ACCEPTED")], completed() + [RuntimeEvent(EventKind.RECEIVING)],
    [RuntimeEvent(EventKind.SESSION, session_id="x"), RuntimeEvent(EventKind.SESSION, session_id="y")],
    [RuntimeEvent(EventKind.SESSION, session_id="x"), RuntimeEvent(EventKind.COMPLETED, text=" ")]])
def test_invalid_runtime_sequences_fail_closed(tmp_path, events):
    core = Companion(FakeRuntime(events), "Inspect", str(tmp_path), Authority.READ_ONLY)
    task = core.run()
    assert task.state == "FAILED"
    assert task.result is None
    assert task.acceptance == Acceptance.UNREVIEWED
    with pytest.raises(ValueError):
        core.review(accepted=True, reviewer="reviewer")


@pytest.mark.parametrize("kind,state", [(EventKind.FAILED, "FAILED"),
                                       (EventKind.CANCELLED, "CANCELLED")])
def test_terminal_failures(tmp_path, kind, state):
    core = Companion(FakeRuntime([RuntimeEvent(kind)]), "Inspect", str(tmp_path), Authority.READ_ONLY)
    assert core.run().state == state


def test_cancel_before_execution(tmp_path):
    runtime = FakeRuntime(completed())
    core = Companion(runtime, "Inspect", str(tmp_path), Authority.READ_ONLY)
    assert core.cancel().state == "CANCELLED"
    with pytest.raises(ValueError):
        core.run()
    assert runtime.calls == 0


def test_runtime_exceptions_are_not_exposed(tmp_path):
    class Broken(FakeRuntime):
        def run(self, request):
            raise RuntimeError("untrusted provider body")
    events = []
    core = Companion(Broken([]), "Inspect", str(tmp_path), Authority.READ_ONLY)
    assert core.run(events.append).state == "FAILED"
    assert "untrusted provider body" not in repr(events) + repr(core.task)


def test_keyboard_interrupt_and_cleanup(tmp_path):
    class Interrupted(FakeRuntime):
        def run(self, request):
            try:
                yield RuntimeEvent(EventKind.SESSION, session_id="x")
                raise KeyboardInterrupt()
            finally:
                self.closed = True
    runtime = Interrupted([])
    core = Companion(runtime, "Inspect", str(tmp_path), Authority.READ_ONLY)
    assert core.run().state == "FAILED"
    assert core.task.failure == Failure.INTERRUPTED
    assert runtime.closed


@pytest.mark.parametrize("stage", ["task_created", "working", "session_bound",
    "inspecting_repository", "receiving_result", "execution_complete", "pending_review"])
@pytest.mark.parametrize("error", [RuntimeError, BrokenPipeError, KeyboardInterrupt, SystemExit])
def test_observer_failure_cannot_change_execution_or_acceptance(tmp_path, stage, error):
    runtime = FakeRuntime(completed())
    core = Companion(runtime, "Inspect", str(tmp_path), Authority.READ_ONLY)

    def broken(event):
        if event.stage == stage:
            raise error("private observer detail")

    task = core.run(broken)
    assert task.state == "RESULT_PENDING_REVIEW"
    assert task.result == "observed result"
    assert task.acceptance == Acceptance.UNREVIEWED and task.reviewer is None
    assert runtime.calls == 1 and runtime.closed
    with pytest.raises(ValueError):
        core.run()


def test_observer_cannot_reenter_lifecycle_or_review(tmp_path):
    core = Companion(FakeRuntime(completed()), "Inspect", str(tmp_path), Authority.READ_ONLY)
    attempts = []

    def observer(event):
        for action in (core.run, core.cancel,
                       lambda: core.review(accepted=True, reviewer="renderer")):
            with pytest.raises(ValueError):
                action()
            attempts.append(event.stage)

    assert core.run(observer).state == "RESULT_PENDING_REVIEW"
    assert len(attempts) == 21
    assert core.task.acceptance == Acceptance.UNREVIEWED


def test_cleanup_failure_is_not_reported_ready_for_review(tmp_path):
    class BrokenCleanup(FakeRuntime):
        def run(self, request):
            yield from completed()
            raise RuntimeError("private cleanup detail")
    events = []
    core = Companion(BrokenCleanup([]), "Inspect", str(tmp_path), Authority.READ_ONLY)
    assert core.run(events.append).state == "FAILED"
    assert "pending_review" not in [event.stage for event in events]

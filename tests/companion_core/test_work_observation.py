"""Read-only projection proof using the real Core, Surface and ReviewStore."""
import json
import threading

from src.companion_core.domain import Execution
from src.companion_core.review import ReviewStore
from src.companion_core.runtime import EventKind, RuntimeEvent
from src.companion_core.surface import Surface, OBSERVATIONS


class Runtime:
    provider_id = "synthetic-no-ai"

    def __init__(self, *, cleanup_failure=False, burst=1, private_session=False):
        self.cleanup_failure = cleanup_failure
        self.burst = burst
        self.private_session = private_session

    def run(self, request):
        try:
            yield RuntimeEvent(EventKind.SESSION, session_id=
                "Authorization: synthetic-private" if self.private_session else "synthetic-public")
            for _ in range(self.burst):
                yield RuntimeEvent(EventKind.INSPECTING, text="PRIVATE REASONING synthetic")
                yield RuntimeEvent(EventKind.RECEIVING, text="Authorization: synthetic-private")
            yield RuntimeEvent(EventKind.COMPLETED, text="公開合成成果")
        finally:
            if self.cleanup_failure:
                raise OSError("Authorization: synthetic-private cleanup")


def create(tmp_path, runtime):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return Surface(runtime, workspace, ReviewStore(tmp_path / "reviews", workspace=str(workspace)))


def finish(surface):
    task_id = surface.start("合成觀察驗證")["task_id"]
    surface.worker.join(5)
    assert not surface.worker.is_alive()
    return task_id, surface.snapshot()


def test_core_events_are_ordered_exact_safe_and_read_only(tmp_path):
    surface = create(tmp_path, Runtime())
    task_id, state = finish(surface)
    observation = state["observation"]
    assert observation["task_id"] == task_id
    assert observation["tool_details"] == "not_provided" and not observation["durable"]
    events = observation["events"]
    assert [e["sequence"] for e in events] == list(range(1, len(events) + 1))
    assert all(e["task_id"] == task_id and e["kind"] in OBSERVATIONS for e in events)
    assert next(e for e in events if e["kind"] == "execution_complete")["confirmation"] == "reported"
    assert events[-1]["kind"] == "pending_review" and events[-1]["confirmation"] == "confirmed"
    for private in ("PRIVATE REASONING", "Authorization", "synthetic-private"):
        assert private not in json.dumps(observation)
    assert surface.active.task.execution is Execution.COMPLETED
    assert state["active"]["state"] == "RESULT_PENDING_REVIEW"
    state["observation"]["events"][0]["title"] = "forged"
    assert surface.snapshot()["observation"]["events"][0]["title"] != "forged"


def test_terminal_report_never_confirms_success_before_cleanup(tmp_path):
    surface = create(tmp_path, Runtime(cleanup_failure=True))
    _, state = finish(surface)
    events = state["observation"]["events"]
    assert state["active"]["state"] == "FAILED" and not state["tasks"]
    assert next(e for e in events if e["kind"] == "execution_complete")["confirmation"] == "reported"
    assert events[-1]["kind"] == "failed" and events[-1]["confirmation"] == "confirmed"
    assert not any(e["kind"] == "pending_review" for e in events)
    assert "synthetic-private" not in json.dumps(state)


def test_projection_is_bounded_and_is_not_recovered_history(tmp_path):
    surface = create(tmp_path, Runtime(burst=300))
    _, state = finish(surface)
    observation = state["observation"]
    assert len(observation["events"]) == 128 and observation["omitted"] > 0
    assert observation["events"][-1]["kind"] == "pending_review"
    reopened = Surface(Runtime(), surface.workspace, ReviewStore(surface.store.directory))
    restored = reopened.snapshot()
    assert restored["observation"]["events"] == [] and restored["observation"]["task_id"] is None
    assert restored["tasks"] == state["tasks"]


def test_observation_failure_cannot_abort_execution(tmp_path):
    surface = create(tmp_path, Runtime())
    def fail(*_):
        raise OSError("synthetic projection failed")
    surface._event = fail
    task_id, state = finish(surface)
    assert state["active"]["state"] == "RESULT_PENDING_REVIEW"
    assert surface.target(task_id)["result"] == "公開合成成果"


def test_private_session_is_not_projected_and_store_still_fails_closed(tmp_path):
    surface = create(tmp_path, Runtime(private_session=True))
    _, state = finish(surface)
    assert "synthetic-private" not in json.dumps(state)
    assert not state["tasks"] and "未能安全保存" in state["notice"]


def test_cancel_request_does_not_create_confirmed_cancel_event(tmp_path):
    ready, release = threading.Event(), threading.Event()
    class Waiting:
        provider_id = "synthetic-no-ai"
        def run(self, request):
            yield RuntimeEvent(EventKind.SESSION, session_id="synthetic")
            ready.set()
            assert request.cancel_requested.wait(5)
            assert release.wait(5)
            yield RuntimeEvent(EventKind.CANCELLED)
    surface = create(tmp_path, Waiting())
    task_id = surface.start("等待合成停止確認")["task_id"]
    try:
        assert ready.wait(2)
        assert surface.cancel({"task_id": task_id})["state"] == "CANCEL_REQUESTED"
        pending = surface.snapshot()
        assert pending["active"]["state"] == "CANCEL_REQUESTED"
        assert not any(e["kind"] in ("cancelled", "execution_cancelled") for e in pending["observation"]["events"])
        release.set()
        surface.worker.join(5)
        final = surface.snapshot()
        assert final["active"]["state"] == "CANCELLED"
        assert final["observation"]["events"][-1]["kind"] == "cancelled"
        assert final["observation"]["events"][-1]["confirmation"] == "confirmed"
    finally:
        release.set()
        surface.worker.join(5)

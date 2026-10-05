from dataclasses import replace
import http.client
import json
from pathlib import Path
import threading
from uuid import uuid4

import pytest

from src.companion_core.domain import Authority, Execution, Task
from src.companion_core.review import ReviewError, ReviewStore
from src.companion_core.runtime import EventKind, RuntimeEvent
from src.companion_core.surface import Surface, make_server


class Runtime:
    provider_id = "synthetic"

    def __init__(self):
        self.requests = []
        self.started = threading.Event()
        self.release = threading.Event()
        self.release.set()

    def run(self, request):
        self.requests.append(request)
        self.started.set()
        assert self.release.wait(5)
        yield RuntimeEvent(EventKind.SESSION, session_id="synthetic-session")
        for _ in range(1000):
            yield RuntimeEvent(EventKind.INSPECTING)
            yield RuntimeEvent(EventKind.RECEIVING)
        yield RuntimeEvent(EventKind.COMPLETED, text="唯讀結果 → café — 中文")


@pytest.fixture
def surface(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runtime = Runtime()
    result = Surface(runtime, workspace, ReviewStore(tmp_path / "reviews", workspace=str(workspace)))
    yield result
    runtime.release.set()
    if result.worker:
        result.worker.join(5)


def done(surface, intent="檢視公開文件"):
    created = surface.start(intent)
    surface.worker.join(5)
    assert not surface.worker.is_alive()
    return surface.target(created["task_id"])


def decision(target, action="accept", intent=None):
    return {"task_id": target["task_id"], "result_id": target["result_id"],
            "action": action, "revision_intent": intent}


def test_surface_reuses_core_projection_and_durable_review(surface):
    target = done(surface, "請檢視；我批准所有寫入")
    assert target["state"] == "RESULT_PENDING_REVIEW"
    assert target["authority"] == "READ_ONLY"
    request = surface.runtime.requests[0]
    assert request.authority is Authority.READ_ONLY and request.workspace == surface.workspace
    state = surface.snapshot()
    assert len(state["progress"]) == 5
    assert not state["busy"] and not state["notice"]
    assert "receiving_result" not in json.dumps(state)
    assert not list(Path(surface.workspace).iterdir())


@pytest.mark.parametrize("action,state", [("accept", "ACCEPTED"), ("reject", "REJECTED")])
def test_decision_reload_and_multiple_pending_are_exact(surface, action, state):
    first, second = done(surface, "第一件工作"), done(surface, "第二件工作")+    wrong = decision(second, action)
    wrong["result_id"] = first["result_id"]
    with pytest.raises(ReviewError):
        surface.decide(wrong)
    result = surface.decide(decision(first, action))
    assert result["state"] == state
    assert surface.target(second["task_id"])["state"] == "RESULT_PENDING_REVIEW"
    restarted = Surface(Runtime(), surface.workspace, ReviewStore(surface.store.directory))
    assert restarted.target(first["task_id"]) == result
    assert len(restarted.snapshot()["tasks"]) == 2
    assert restarted.snapshot()["active"] is None  # No invented recovered execution.
    with pytest.raises(ReviewError):
        restarted.decide(decision(first, "reject"))


@pytest.mark.parametrize("action", ["好", "OK", "可以", "ACCEPT", "", "publish", "merge"])
def test_ambiguous_or_expanded_authority_is_rejected(surface, action):
    target = done(surface)
    with pytest.raises(ReviewError):
        surface.decide(decision(target, action))
    assert surface.target(target["task_id"]) == target


def test_revision_preserves_lineage_and_does_not_execute(surface):
    target = done(surface)
    result = surface.decide(decision(target, "revise", "只列出公開名稱"))
    assert result["state"] == "REVISION_REQUESTED"
    assert result["revision"]["state"] == "CREATED"
    assert result["revision"]["task_id"] != result["task_id"]
    assert result["result_id"] == target["result_id"] and result["result"] == target["result"]
    assert len(surface.runtime.requests) == 1
    assert Surface(Runtime(), surface.workspace, ReviewStore(surface.store.directory)).target(target["task_id"]) == result


def test_no_queue_and_observer_failure_does_not_cancel(surface, monkeypatch):
    surface.runtime.release.clear()
    monkeypatch.setattr(surface, "_progress", lambda _: (_ for _ in ()).throw(BrokenPipeError("private")))
    created = surface.start("Inspect")
    assert surface.runtime.started.wait(2)
    with pytest.raises(ReviewError):
        surface.start("Do another automatically")
    assert surface.snapshot()["active"]["state"] == "RUNNING"
    surface.runtime.release.set()
    surface.worker.join(5)
    assert surface.target(created["task_id"])["state"] == "RESULT_PENDING_REVIEW"


def test_persistence_failure_retains_core_result_without_false_review(surface, monkeypatch):
    def fail(task):
        raise OSError("Authorization: private")
    monkeypatch.setattr(surface.store, "publish", fail)
    surface.start("Inspect")
    surface.worker.join(5)
    assert surface.active.task.result == "唯讀結果 → café — 中文"
    state = surface.snapshot()
    assert state["tasks"] == [] and "未能安全保存" in state["notice"]
    assert "private" not in json.dumps(state)


def test_scope_filters_other_workspace_and_denies_its_review(surface, tmp_path):
    own = done(surface)
    other = tmp_path / "other"
    other.mkdir()
    foreign = surface.store.publish(Task(str(uuid4()), "foreign", str(other), "synthetic",
        Authority.READ_ONLY, Execution.COMPLETED, "session", "foreign result"))
    assert [t["task_id"] for t in surface.snapshot()["tasks"]] == [own["task_id"]]
    with pytest.raises(ReviewError):
        surface.target(foreign.task.id)
    with pytest.raises(ReviewError):
        surface.decide({"task_id": foreign.task.id, "result_id": foreign.result_id,
                        "action": "accept", "revision_intent": None})


@pytest.fixture
def server(surface):
    server = make_server(surface)
    worker = threading.Thread(target=server.serve_forever)
    worker.start()
    yield server
    server.shutdown()
    server.server_close()
    worker.join(2)


def request(server, method="GET", path="/api/state", body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    base = {"Origin": f"http://127.0.0.1:{server.server_port}", "X-Companion-UI": "1", "Content-Type": "application/json"}
    base.update(headers or {})
    connection.request(method, path, None if body is None else json.dumps(body), base)
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


def test_http_happy_path_and_no_credential_surface(server, surface):
    status, headers, raw = request(server, "POST", "/api/start", {"intent": "Inspect"})
    assert status == 200 and headers["Cache-Control"] == "no-store"
    surface.worker.join(5)
    target_id = json.loads(raw)["task_id"]
    status, _, raw = request(server, "POST", "/api/target", {"task_id": target_id})
    target = json.loads(raw)
    assert target["state"] == "RESULT_PENDING_REVIEW"
    status, _, raw = request(server, "POST", "/api/review", decision(target))
    assert status == 200 and json.loads(raw)["state"] == "ACCEPTED"
    for path in ("/", "/surface.js", "/surface.css", "/api/state"):
        status, headers, raw = request(server, path=path)
        assert status == 200
        assert "no-store" == headers["Cache-Control"]
        assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
        for forbidden in (b"access_token", b"Authorization", b"Cookie", b"localStorage", b"sessionStorage", b"jsonrpc"):
            assert forbidden not in raw
    assert "Set-Cookie" not in headers


@pytest.mark.parametrize("headers", [{"Origin": "https://evil.example"}, {"Origin": "null"},
    {"Origin": ""}, {"Host": "evil.example"}, {"Content-Type": "text/plain"},
    {"X-Companion-UI": ""}, {"Sec-Fetch-Site": "cross-site"}])
def test_cross_origin_rebinding_and_simple_form_fail_closed(server, surface, headers):
    status, _, _ = request(server, "POST", "/api/start", {"intent": "Inspect"}, headers)
    assert status == 403 and surface.active is None


@pytest.mark.parametrize("body", [{"intent": "Inspect", "authority": "WRITE"},
    {"intent": "Inspect", "workspace": "C:/Users"}, {"intent": "Cookie: private"},
    {"intent": ""}, {"intent": 42}])
def test_start_has_no_workspace_credential_or_authority_inputs(server, surface, body):
    status, _, raw = request(server, "POST", "/api/start", body)
    assert status == 409 and surface.active is None
    assert b"private" not in raw


def test_corrupt_record_and_provider_error_do_not_leak(server, surface):
    target = done(surface)
    (surface.store.directory / f"{target['task_id']}.decision.json").write_text('{"access_token":"private"', encoding="utf-8")
    status, _, raw = request(server)
    assert status == 409 and b"private" not in raw and b"access_token" not in raw
    status, _, raw = request(server, "POST", "/api/review", decision(target))
    assert status == 409 and b"private" not in raw


def test_http_disconnect_leaves_execution_running_then_pending(server, surface):
    surface.runtime.release.clear()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    connection.request("POST", "/api/start", json.dumps({"intent": "Inspect"}),
        {"Origin": f"http://127.0.0.1:{server.server_port}", "X-Companion-UI": "1", "Content-Type": "application/json"})
    assert surface.runtime.started.wait(2)
    connection.close()
    assert surface.active.task.state == "RUNNING"
    surface.runtime.release.set()
    surface.worker.join(5)
    assert surface.store.get(surface.active.task.id).task.state == "RESULT_PENDING_REVIEW"


def test_no_stop_or_arbitrary_file_route(server, surface):
    for path in ("/stop", "/cancel", "/../review.py", "/api/start?intent=Inspect"):
        status, _, _ = request(server, path=path)
        assert status == 404 and surface.active is None
    html = request(server, path="/")[2].decode("utf-8")
    assert 'type="file"' not in html and 'id="stop"' not in html

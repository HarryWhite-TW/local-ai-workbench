"""Running cancellation: exact intent, one reader, reconciled local effects."""
import base64
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from src.companion_core import codex
from src.companion_core.core import Companion
from src.companion_core.domain import Authority, Failure
from src.companion_core.runtime import EventKind, Request, RuntimeEvent, RuntimeFailure
from src.companion_core.review import ReviewError, ReviewStore
from src.companion_core.surface import Surface
from tests.companion_core.test_codex import FakeRpc, notification
from tests.companion_core.test_surface import surface, server, request


class WaitingRuntime:
    provider_id = "synthetic"

    def __init__(self, outcome="cancel"):
        self.started = threading.Event()
        self.release = threading.Event()
        self.outcome = outcome

    def run(self, request):
        self.request = request
        self.started.set()
        assert self.release.wait(5)
        yield RuntimeEvent(EventKind.SESSION, session_id="session")
        if self.outcome == "complete":
            yield RuntimeEvent(EventKind.COMPLETED, text="preserved result")
        elif self.outcome == "fail":
            raise RuntimeFailure(Failure.CANCELLATION)
        else:
            yield RuntimeEvent(EventKind.CANCELLED)


@pytest.mark.parametrize("outcome,state", [
    ("cancel", "CANCELLED"), ("complete", "RESULT_PENDING_REVIEW"), ("fail", "FAILED")])
def test_running_lifecycle_review_and_duplicate_stop(tmp_path, outcome, state):
    runtime = WaitingRuntime(outcome)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    core = Companion(runtime, "Inspect", str(workspace), Authority.READ_ONLY)
    worker = threading.Thread(target=core.run)
    worker.start()
    try:
        assert runtime.started.wait(2)
        assert core.cancel().state == "CANCEL_REQUESTED"
        assert core.cancel().state == "CANCEL_REQUESTED"
        assert runtime.request.cancel_requested.is_set()
        with pytest.raises(ValueError):
            core.review(accepted=True, reviewer="human")
        runtime.release.set()
        worker.join(5)
        assert not worker.is_alive() and core.task.state == state
        store = ReviewStore(tmp_path / "reviews", workspace=str(workspace))
        if outcome == "complete":
            assert core.task.result == "preserved result"
            assert store.publish(core.task).task.state == state
        else:
            assert core.task.result is None
            with pytest.raises(ReviewError):
                store.publish(core.task)
    finally:
        runtime.release.set()
        worker.join(5)


def test_external_stop_during_observer_is_not_renderer_authority(tmp_path):
    runtime = WaitingRuntime()
    core = Companion(runtime, "Inspect", str(tmp_path), Authority.READ_ONLY)
    entered, release = threading.Event(), threading.Event()

    def observer(event):
        if event.stage == "task_created":
            entered.set()
            assert release.wait(5)
            with pytest.raises(ValueError):
                core.cancel()

    worker = threading.Thread(target=core.run, args=(observer,))
    worker.start()
    try:
        assert entered.wait(2)
        assert core.cancel().state == "CANCEL_REQUESTED"
        release.set()
        assert runtime.started.wait(2)
        runtime.release.set()
        worker.join(5)
        assert core.task.state == "CANCELLED"
    finally:
        release.set()
        runtime.release.set()
        worker.join(5)


class CancelRpc(FakeRpc):
    def __init__(self, messages, cancel):
        super().__init__()
        self.messages = iter(messages)
        self.cancel = cancel
        self.interrupts = []

    def call(self, method, params):
        result = super().call(method, params)
        if method == "turn/start":
            self.cancel.set()  # Explicit request before identity is returned.
        return result

    def begin(self, method, params):
        self.interrupts.append((method, params))
        return 17


@pytest.mark.parametrize("status,expected", [
    ("interrupted", EventKind.INTERRUPTED), ("completed", EventKind.COMPLETED)])
@pytest.mark.parametrize("ack_first", [True, False])
def test_exact_one_shot_and_terminal_race(status, expected, ack_first):
    stop = threading.Event()
    terminal = notification("turn/completed", turn={"id": "turn", "status": status})
    ack = {"id": 17, "result": {}}
    messages = [
        notification("item/started", item={"type": "commandExecution"}),
        notification("turn/completed", threadId="wrong", turn={"id": "turn", "status": "interrupted"}),
        notification("turn/completed", turn={"id": "wrong", "status": "interrupted"}),
        notification("item/completed", item={"type": "agentMessage", "text": "result"}),
        *( [ack, terminal] if ack_first else [terminal, ack] ),
    ]
    rpc = CancelRpc(messages, stop)
    events = list(codex.CodexRuntime("unused", "model", lambda: "synthetic")._execute(
        rpc, Request("Inspect", ".", Authority.READ_ONLY, stop), "synthetic"))
    assert rpc.interrupts == [("turn/interrupt", {"threadId": "session", "turnId": "turn"})]
    assert events[-1].kind == expected
    assert EventKind.CANCELLED not in [e.kind for e in events]  # No host reconciliation here.


def test_completed_already_queued_prevents_late_interrupt():
    stop = threading.Event()
    rpc = CancelRpc([
        notification("turn/completed", turn={"id": "turn", "status": "completed"})], stop)
    events = list(codex.CodexRuntime("unused", "model", lambda: "synthetic")._execute(
        rpc, Request("Inspect", ".", Authority.READ_ONLY, stop), "synthetic"))
    assert events[-1].kind == EventKind.COMPLETED
    assert rpc.interrupts == []


@pytest.mark.parametrize("failure", ["error", "connection", "timeout"])
def test_interrupt_failure_never_retries_or_confirms(failure):
    stop = threading.Event()
    class Broken(CancelRpc):
        def notification(self, timeout):
            if not self.interrupts:
                return {}
            if failure == "error":
                return {"id": 17, "error": {"message": "Authorization: private"}}
            if failure == "connection":
                raise RuntimeFailure(Failure.CONNECTION)
            raise RuntimeFailure(Failure.TIMEOUT)
    rpc = Broken([], stop)
    with pytest.raises(RuntimeFailure):
        list(codex.CodexRuntime("unused", "model", lambda: "synthetic", timeout=.02)._execute(
            rpc, Request("Inspect", ".", Authority.READ_ONLY, stop), "synthetic"))
    assert len(rpc.interrupts) == 1


@pytest.mark.parametrize("bad", [{}, {"task_id": 1}, {"task_id": "old"},
    {"task_id": "active", "authority": "WRITE"}, {"task_id": "active", "workspace": "C:/"},
    {"task_id": "active", "provider": "other"}])
def test_cancel_api_exact_shape_and_identity(server, surface, bad):
    surface.runtime.release.clear()
    ident = surface.start("Inspect")["task_id"]
    assert surface.runtime.started.wait(2)
    body = {k: ident if v == "active" else v for k, v in bad.items()}
    assert request(server, "POST", "/api/cancel", body)[0] == 409
    assert not surface.runtime.requests[0].cancel_requested.is_set()


@pytest.mark.parametrize("mode", ["success", "reconcile_failure", "transport_failure"])
def test_adapter_does_not_publish_cancel_before_reconciliation(tmp_path, monkeypatch, mode):
    import io
    from types import SimpleNamespace
    stop = threading.Event()
    stop.set()
    class Process:
        pid = 900003
        stdin = io.StringIO()
        stdout = io.StringIO()
        exited = False
        def poll(self): return 0 if self.exited else None
    process = Process()
    monkeypatch.setattr(codex.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(codex, "_Rpc", lambda _: SimpleNamespace(finish=process.stdout.close))
    checks = []
    def reconcile(p):
        assert p is process and not p.stdin.closed
        checks.append("reconcile")
        if mode == "reconcile_failure":
            raise RuntimeFailure(Failure.CANCELLATION)
        p.exited = True
    monkeypatch.setattr(codex, "_reconcile_windows_tree", reconcile)
    runtime = codex.CodexRuntime("unused", "model", lambda: "synthetic")
    def execute(*args):
        yield RuntimeEvent(EventKind.SESSION, session_id="session")
        if mode == "transport_failure":
            raise RuntimeFailure(Failure.CONNECTION)
        yield RuntimeEvent(EventKind.INTERRUPTED)
    monkeypatch.setattr(runtime, "_execute", execute)
    stream = runtime.run(Request("Inspect", str(tmp_path), Authority.READ_ONLY, stop))
    assert next(stream).kind == EventKind.SESSION and checks == []
    if mode == "success":
        event = next(stream)
        assert checks == ["reconcile"] and process.exited
        assert event.kind == EventKind.CANCELLED
        assert list(stream) == []
    else:
        with pytest.raises(RuntimeFailure):
            list(stream)
        assert checks == ["reconcile"]
    assert process.stdin.closed and process.stdout.closed


def test_completion_after_interrupt_error_preserves_exact_result():
    stop = threading.Event()
    rpc = CancelRpc([
        {},
        {"id": 17, "error": {"message": "private"}},
        notification("item/completed", item={"type": "agentMessage", "text": "result"}),
        notification("turn/completed", turn={"id": "turn", "status": "completed"}),
    ], stop)
    events = list(codex.CodexRuntime("unused", "model", lambda: "synthetic")._execute(
        rpc, Request("Inspect", ".", Authority.READ_ONLY, stop), "synthetic"))
    assert events[-1].kind == EventKind.COMPLETED and events[-1].text == "result"
    assert len(rpc.interrupts) == 1


@pytest.mark.parametrize("headers", [
    {"Origin": "https://evil.example"}, {"Origin": "null"}, {"X-Companion-UI": ""},
    {"Host": "evil.example"}, {"Sec-Fetch-Site": "cross-site"}, {"Content-Type": "text/plain"}])
def test_cancel_api_same_origin_guard(server, surface, headers):
    surface.runtime.release.clear()
    ident = surface.start("Inspect")["task_id"]
    assert surface.runtime.started.wait(2)
    assert request(server, "POST", "/api/cancel", {"task_id": ident}, headers)[0] == 403
    assert surface.active.task.state == "RUNNING"


def test_http_stop_duplicate_and_natural_completion_review(server, surface):
    surface.runtime.release.clear()
    ident = surface.start("Inspect")["task_id"]
    assert surface.runtime.started.wait(2)
    for _ in range(2):
        status, _, raw = request(server, "POST", "/api/cancel", {"task_id": ident})
        assert status == 200 and json.loads(raw)["state"] == "CANCEL_REQUESTED"
        assert set(json.loads(raw)) == {"task_id", "intent", "state"}
    surface.runtime.release.set()
    surface.worker.join(5)
    assert surface.target(ident)["state"] == "RESULT_PENDING_REVIEW"
    assert request(server, "POST", "/api/cancel", {"task_id": ident})[0] == 409


@pytest.mark.skipif(os.name != "nt", reason="Windows native tree reconciliation")
def test_windows_actual_transport_core_surface_and_tree(tmp_path, monkeypatch):
    """No model/auth: real pipes, real Windows parent/child, real production kill."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    peer = tmp_path / "peer.py"
    interrupts = tmp_path / "interrupts.json"
    payload = base64.b64encode(
        "Write-Output 'READY'; Start-Sleep -Seconds 120".encode("utf-16le")).decode()
    peer.write_text(r'''
import json, os, subprocess, sys
def send(m): print(json.dumps(m), flush=True)
for line in sys.stdin:
 m=json.loads(line); method=m.get("method")
 if method=="initialize": send({"id":m["id"],"result":{}})
 elif method=="thread/start":
  send({"id":m["id"],"result":{"thread":{"id":"session"},"sandbox":{"type":"readOnly","networkAccess":False},"approvalPolicy":"never"}})
 elif method=="turn/start":
  send({"id":m["id"],"result":{"turn":{"id":"turn"}}})
  shell=os.path.join(os.environ["SystemRoot"],"System32","cmd.exe")
  command=os.path.join(os.environ["SystemRoot"],"System32","WindowsPowerShell","v1.0","powershell.exe")+" -NoProfile -NonInteractive -EncodedCommand "+sys.argv[2]
  child=subprocess.Popen([shell,"/d","/c",command],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
  while b"READY" not in child.stdout.readline(): pass
  send({"method":"item/started","params":{"threadId":"session","turnId":"turn","item":{"type":"commandExecution"}}})
 elif method=="turn/interrupt":
  with open(sys.argv[1],"w") as f: json.dump(m["params"],f)
  send({"id":m["id"],"result":{}})
  send({"method":"turn/completed","params":{"threadId":"session","turn":{"id":"turn","status":"interrupted"}}})
''', encoding="utf-8")
    original = subprocess.Popen
    children = []
    def launch(command, **kwargs):
        if command[0] == "synthetic-codex":
            p = original([sys.executable, "-u", str(peer), str(interrupts), payload], **kwargs)
            children.append(p)
            return p
        return original(command, **kwargs)
    monkeypatch.setattr(subprocess, "Popen", launch)
    surface = Surface(codex.CodexRuntime("synthetic-codex", "model", lambda: "synthetic", timeout=15),
        workspace, ReviewStore(tmp_path / "reviews", workspace=str(workspace)))
    unrelated = original([sys.executable, "-c", "import time; time.sleep(60)"],
        creationflags=subprocess.CREATE_NO_WINDOW)
    reconciled = []
    real_reconcile = codex._reconcile_windows_tree
    def reconcile(process):
        assert surface.active.task.state == "CANCEL_REQUESTED"
        assert surface.store.targets() == []
        before = codex._windows_processes()
        owned = {process.pid}
        for _ in range(8):
            owned.update(pid for pid, (parent, _) in before.items() if parent in owned)
        assert len(owned) >= 3 and process.poll() is None
        assert interrupts.exists()  # Exact provider Interrupted preceded this boundary.
        real_reconcile(process)
        after = codex._windows_processes()
        assert all(after.get(pid) != before[pid] for pid in owned)
        assert unrelated.poll() is None
        assert surface.active.task.state == "CANCEL_REQUESTED"
        reconciled.append(sorted(owned))
        print("WINDOWS_CANCEL_EVIDENCE", json.dumps({"owned_pids": sorted(owned),
            "all_alive_before": True, "all_gone_after": True, "unrelated_alive": True}))
    monkeypatch.setattr(codex, "_reconcile_windows_tree", reconcile)
    try:
        ident = surface.start("Read only wait")["task_id"]
        end = time.monotonic() + 10
        while time.monotonic() < end and not any("檢視" in text for text in surface.snapshot()["progress"]):
            time.sleep(.05)
        assert any("檢視" in text for text in surface.snapshot()["progress"])
        assert surface.cancel({"task_id": ident})["state"] == "CANCEL_REQUESTED"
        surface.cancel({"task_id": ident})
        surface.worker.join(25)
        assert not surface.worker.is_alive()
        assert surface.active.task.state == "CANCELLED"
        assert len(reconciled) == 1
        assert json.loads(interrupts.read_text()) == {"threadId": "session", "turnId": "turn"}
        assert surface.store.targets() == []
        assert list(workspace.iterdir()) == []
        state = json.dumps(surface.snapshot())
        assert "synthetic" not in state and "session" not in state
        assert all(p.poll() is not None for p in children)
    finally:
        # Test-only cleanup, never used as a passing cancellation oracle.
        for p in children:
            if p.poll() is None:
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"],
                    capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        if surface.worker:
            surface.worker.join(5)
        unrelated.terminate()
        unrelated.wait(5)


@pytest.mark.skipif(os.name != "nt", reason="Windows reconciliation contract")
@pytest.mark.parametrize("case", ["success", "nonzero", "survivor", "lost_root", "wrong_parent"])
def test_tree_reconciliation_fail_closed(monkeypatch, case):
    class Process:
        pid = 900001
        exited = case == "lost_root"
        def poll(self): return 0 if self.exited else None
        def wait(self, timeout): self.exited = True
    process = Process()
    owned = {process.pid: (os.getpid() if case != "wrong_parent" else 999999, "2026-01-01"),
        900002: (process.pid, "2026-01-02")}
    snapshots = iter([owned, owned if case == "survivor" else {}])
    monkeypatch.setattr(codex, "_windows_processes", lambda: next(snapshots, owned))
    kills = []
    def kill(command, **kwargs):
        kills.append(command)
        return subprocess.CompletedProcess(command, 1 if case == "nonzero" else 0)
    monkeypatch.setattr(codex.subprocess, "run", kill)
    clock = iter([0, 10])
    monkeypatch.setattr(codex.time, "monotonic", lambda: next(clock, 10))
    if case == "success":
        codex._reconcile_windows_tree(process)
        assert process.exited
    else:
        with pytest.raises(RuntimeFailure) as caught:
            codex._reconcile_windows_tree(process)
        assert caught.value.reason == Failure.CANCELLATION
    assert len(kills) == (0 if case in ("lost_root", "wrong_parent") else 1)
    if kills:
        assert kills[0][1:] == ["/PID", str(process.pid), "/T", "/F"]


def test_cancel_rejects_duplicate_json_keys(server, surface):
    import http.client
    surface.runtime.release.clear()
    ident = surface.start("Inspect")["task_id"]
    assert surface.runtime.started.wait(2)
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    body = '{"task_id":"old","task_id":' + json.dumps(ident) + '}'
    conn.request("POST", "/api/cancel", body, {
        "Origin": f"http://127.0.0.1:{server.server_port}",
        "X-Companion-UI": "1", "Content-Type": "application/json"})
    response = conn.getresponse()
    assert response.status == 409
    assert b"old" not in response.read()
    conn.close()
    assert not surface.runtime.requests[0].cancel_requested.is_set()


def test_unconfirmed_cleanup_returns_failure_without_waiting_for_live_stdout(tmp_path, monkeypatch):
    """A failed tree kill must not block the UI on the reader's pipe lock."""
    original = subprocess.Popen
    children = []
    ready = threading.Event()

    def launch(command, **kwargs):
        child = original([sys.executable, "-c", "import time; time.sleep(60)"], **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(codex.subprocess, "Popen", launch)
    runtime = codex.CodexRuntime("synthetic-codex", "model", lambda: "synthetic")

    def execute(rpc, request, token):
        yield RuntimeEvent(EventKind.SESSION, session_id="session")
        ready.set()
        assert request.cancel_requested.wait(5)
        yield RuntimeEvent(EventKind.INTERRUPTED)

    attempts = []

    def failed_reconciliation(process):
        attempts.append(process.pid)
        raise RuntimeFailure(Failure.CANCELLATION)

    monkeypatch.setattr(runtime, "_execute", execute)
    monkeypatch.setattr(codex, "_reconcile_windows_tree", failed_reconciliation)
    core = Companion(runtime, "Inspect", str(tmp_path), Authority.READ_ONLY)
    worker = threading.Thread(target=core.run)
    worker.start()
    try:
        assert ready.wait(3)
        core.cancel()
        worker.join(2)
        assert not worker.is_alive(), "failed cleanup blocked on live stdout"
        assert core.task.state == "FAILED" and core.task.failure == Failure.CANCELLATION
        assert len(attempts) == 1
    finally:
        # Failed-reconciliation fixture remains owned by this test, not the UI.
        for child in children:
            if child.poll() is None:
                child.terminate()
            child.wait(5)
        worker.join(5)


def test_state_cleanup_failure_after_completion_is_not_reported_as_success(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"
    state.mkdir()

    class BrokenState:
        name = str(state)

        def cleanup(self):
            raise PermissionError("synthetic state cleanup failure")

    original = subprocess.Popen
    monkeypatch.setattr(codex.tempfile, "TemporaryDirectory", lambda **kwargs: BrokenState())
    monkeypatch.setattr(codex.subprocess, "Popen", lambda command, **kwargs:
                        original([sys.executable, "-c", "pass"], **kwargs))
    runtime = codex.CodexRuntime("synthetic-codex", "model", lambda: "synthetic")
    monkeypatch.setattr(runtime, "_execute", lambda rpc, request, token: iter((
        RuntimeEvent(EventKind.SESSION, session_id="session"),
        RuntimeEvent(EventKind.COMPLETED, text="result"))))

    stages = []
    core = Companion(runtime, "Inspect", str(workspace), Authority.READ_ONLY)
    task = core.run(stages.append)
    assert task.state == "FAILED" and task.failure == Failure.UNKNOWN
    assert task.result is None
    assert "pending_review" not in [event.stage for event in stages]

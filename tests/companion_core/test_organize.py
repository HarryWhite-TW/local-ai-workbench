"""Focused organizer contracts. RPC is synthetic; these are NOT model/browser evidence."""
import base64
import hashlib
import http.client
import io
import json
from pathlib import Path
import threading
from types import SimpleNamespace
from uuid import uuid4
import zipfile

import pytest

from src.companion_core.chat import Conversations
from src.companion_core.daily import WorkNotConnected
from src.companion_core.native_execution import RpcRejected, policy
from src.companion_core.organize import DocumentOrganizer, snapshots, validate_plan
from src.companion_core.review import ReviewStore
from src.companion_core.runtime import RuntimeFailure
from src.companion_core.domain import Failure
from src.companion_core.siwc import ChatError
from src.companion_core.surface import Surface, make_server

FILES = [
    {"name": "notes.txt", "content": base64.b64encode(b"\xef\xbb\xbfInvoice for the design project.\r\nAmount: 1200.\r\n").decode()},
    {"name": "notes.txt", "content": base64.b64encode(b"Weekly study notes about photosynthesis.\n").decode()},
]
PLAN = {"items": [
    {"id": "D1", "category": "Finance", "reason": "Contains an invoice and amount.", "evidence": "Invoice for the design project."},
    {"id": "D2", "category": "Study", "reason": "Contains biology study notes.", "evidence": "study notes about photosynthesis."},
]}


class Rpc:
    def __init__(self, workspace):
        self.workspace, self.calls, self.messages = workspace, [], []
        self.mode = "complete"
        self.gate = self.release = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def call(self, method, params):
        self.calls.append((method, params))
        if method == "config/read":
            return {"config": {"mcp_servers": {"unrelated": {"enabled": True}}}}
        if method in ("thread/start", "thread/read"):
            return {"thread": {"id": "thread-1", "cwd": self.workspace},
                    "approvalPolicy": "never", "sandbox": policy(self.workspace)}
        if method == "turn/start":
            if self.mode == "reject":
                raise RpcRejected("turn/start", -32600, "invalid_request")
            if self.mode == "lost":
                raise RuntimeFailure(Failure.CONNECTION)
            if self.gate:
                self.gate.set()
                self.release.wait(5)
            answer = json.dumps(PLAN) if self.mode != "bad_plan" else '{"items":[]}'
            self.messages = [
                {"method": "item/completed", "params": {"threadId": "thread-1", "turnId": "turn-1",
                  "item": {"id": "result", "type": "agentMessage", "phase": "final_answer", "text": answer}}},
                {"method": "turn/completed", "params": {"threadId": "thread-1",
                  "turn": {"id": "turn-1", "status": "completed"}}}]
            if self.mode == "disconnect":
                self.messages = []
            return {"turn": {"id": "turn-1"}}
        if method == "thread/turns/list":
            return {"data": [{"id": "turn-1", "status": "completed", "items": [
                {"id": "result", "type": "agentMessage", "text": json.dumps(PLAN)}]}]}
        raise AssertionError(method)

    def notification(self, timeout):
        if not self.messages:
            raise RuntimeFailure(Failure.CONNECTION)
        return self.messages.pop(0)

    def begin(self, method, params):
        assert method == "turn/interrupt"
        self.calls.append((method, params))
        self.messages = [{"method": "turn/completed", "params": {
            "threadId": "thread-1", "turn": {"id": "turn-1", "status": "interrupted"}}}]
        return 1


@pytest.fixture
def env(tmp_path):
    workspace, data = tmp_path / "workspace", tmp_path / "state"
    workspace.mkdir(); data.mkdir()
    (workspace / "AGENTS.md").write_text("Read-only sample project", encoding="utf-8")
    auth = SimpleNamespace(pending=None, lock=threading.RLock(), vault=SimpleNamespace(data={"active": "owner"}))
    auth.snapshot = lambda: {"active": auth.vault.data["active"], "accounts": [], "pending": bool(auth.pending)}
    chat = Conversations(workspace, data, auth)
    rpc = Rpc(str(workspace))
    organizer = DocumentOrganizer(chat, client_factory=lambda: rpc)
    chat.organizer = organizer
    yield chat, organizer, rpc
    organizer.close()


def invoke(organizer, action, body):
    output = []
    organizer.respond(action, body, output.append)
    assert len(output) == 1
    return output[0]


def request(chat):
    return {"id": str(uuid4()), "chat": None, "account": "owner", "workspace": chat.workspace,
            "question": "Organize these documents by actual content.", "files": FILES}


def start(env):
    chat, organizer, rpc = env
    body = request(chat)
    result = invoke(organizer, "start", body)
    organizer.worker.join(5)
    assert not organizer.worker.is_alive()
    return body, invoke(organizer, "state", {"chat": result["chat"]})[0]


def test_preview_confirmation_copies_exact_bytes_and_survives_restart(env, tmp_path):
    chat, organizer, rpc = env
    original = tmp_path / "original.txt"
    raw = base64.b64decode(FILES[0]["content"])
    original.write_bytes(raw)
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    body, job = start(env)
    assert job["state"] == "PREVIEW"
    with chat.connect() as db:
        assert db.execute("SELECT output FROM document_organization").fetchone()[0] is None
    with pytest.raises(ChatError):
        invoke(organizer, "download", {"id": job["id"]})
    with pytest.raises(ChatError):
        invoke(organizer, "confirm", {"id": job["id"], "approval": "wrong"})
    result = invoke(organizer, "confirm", {"id": job["id"], "approval": job["approval"]})
    assert result["state"] == "COMPLETED"
    again = invoke(organizer, "confirm", {"id": job["id"], "approval": job["approval"]})
    assert again["output_sha256"] == result["output_sha256"]
    restored = DocumentOrganizer(chat, client_factory=lambda: rpc)
    download = invoke(restored, "download", {"id": job["id"]})
    payload = base64.b64decode(download["content"])
    assert hashlib.sha256(payload).hexdigest() == result["output_sha256"]
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert archive.namelist() == ["Finance/D1-notes.txt", "Study/D2-notes.txt"]
        for item, f in zip(archive.namelist(), FILES):
            assert archive.read(item) == base64.b64decode(f["content"])
    assert hashlib.sha256(original.read_bytes()).hexdigest() == before
    assert len([c for c in rpc.calls if c[0] == "turn/start"]) == 1
    thread_params = next(p for m, p in rpc.calls if m == "thread/start")
    assert thread_params["config"]["mcp_servers"]["unrelated"]["enabled"] is False
    turn_params = next(p for m, p in rpc.calls if m == "turn/start")
    assert turn_params["sandboxPolicy"] == {"type": "readOnly", "networkAccess": False}
    assert turn_params["approvalPolicy"] == "never"
    assert "Invoice for the design project." in turn_params["input"][0]["text"]
    assert invoke(organizer, "start", body)["id"] == job["id"]


@pytest.mark.parametrize("change", [
    lambda p: p["items"].pop(),
    lambda p: p["items"][1].update(id="D1"),
    lambda p: p["items"][0].update(category="../outside"),
    lambda p: p["items"][0].update(category="NUL.txt"),
    lambda p: p["items"][0].update(category="folder:stream"),
    lambda p: p["items"][0].update(evidence="This quote was not in the input."),
    lambda p: p["items"][0].update(command="write files"),
])
def test_untrusted_model_plan_cannot_select_paths_or_invent_sources(change):
    plan = json.loads(json.dumps(PLAN))
    change(plan)
    with pytest.raises((ValueError, TypeError)):
        validate_plan(json.dumps(plan), snapshots(FILES))


@pytest.mark.parametrize("file", [
    {"name": "../private.txt", "content": FILES[0]["content"]},
    {"name": "secret.exe", "content": FILES[0]["content"]},
    {"name": "binary.txt", "content": base64.b64encode(b"\xff\x00").decode()},
    {"name": "private.txt", "content": base64.b64encode(b"api_key=synthetic-secret-value-12345").decode()},
])
def test_upload_rejects_paths_binary_and_credentials(file):
    with pytest.raises(ChatError):
        snapshots([file])


def test_account_and_workspace_boundaries(env):
    chat, organizer, _ = env
    body, job = start(env)
    chat.auth.vault.data["active"] = "other"
    for action, payload in [("state", {"chat": job["chat"]}), ("confirm", {"id": job["id"], "approval": job["approval"]}),
                            ("download", {"id": job["id"]}), ("start", body)]:
        with pytest.raises(ChatError):
            invoke(organizer, action, payload)
    chat.auth.vault.data["active"] = "owner"
    chat.auth.pending = {"active": True}
    with pytest.raises(ChatError):
        invoke(organizer, "state", {"chat": job["chat"]})
    chat.auth.pending = None
    chat.workspace += "-other"
    with pytest.raises(ChatError):
        invoke(organizer, "state", {"chat": job["chat"]})


@pytest.mark.parametrize("mode,expected", [("reject", "FAILED"), ("lost", "UNKNOWN"), ("disconnect", "UNKNOWN"), ("bad_plan", "FAILED")])
def test_no_copies_for_rejection_uncertainty_or_invalid_plan(env, mode, expected):
    chat, organizer, rpc = env
    rpc.mode = mode
    _, job = start(env)
    assert job["state"] == expected and job["approval"] is None
    with chat.connect() as db:
        assert db.execute("SELECT output FROM document_organization").fetchone()[0] is None
    with pytest.raises(ChatError):
        invoke(organizer, "confirm", {"id": job["id"], "approval": ""})


def test_reconcile_exact_turn_does_not_replay_model(env):
    chat, organizer, rpc = env
    rpc.mode = "disconnect"
    _, job = start(env)
    assert job["state"] == "UNKNOWN"
    invoke(organizer, "reconcile", {"id": job["id"]})
    organizer.worker.join(5)
    restored = invoke(organizer, "state", {"chat": job["chat"]})[0]
    assert restored["state"] == "PREVIEW"
    assert len([m for m, _ in rpc.calls if m == "turn/start"]) == 1
    assert next(p for m, p in rpc.calls if m == "thread/turns/list")["threadId"] == "thread-1"


def test_loopback_routes_reject_cross_origin_and_bound_uploads(env):
    chat, organizer, _ = env
    surface = Surface(WorkNotConnected(), chat.workspace, ReviewStore(chat.path.parent / "reviews", workspace=chat.workspace))
    server = make_server(surface, chat)
    worker = threading.Thread(target=server.serve_forever); worker.start()
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port)
    origin = f"http://127.0.0.1:{server.server_port}"
    try:
        conn.request("GET", "/")
        response = conn.getresponse()
        assert response.status == 200 and b'data-organize-enabled="true"' in response.read()
        conn.request("POST", "/api/chat/organize-start", json.dumps(request(chat)), headers={
            "Content-Type": "application/json", "X-Companion-UI": "1", "Origin": "https://untrusted.invalid"})
        response = conn.getresponse(); response.read(); assert response.status == 403
        body = request(chat)
        conn.request("POST", "/api/chat/organize-start", json.dumps(body), headers={
            "Content-Type": "application/json", "X-Companion-UI": "1", "Origin": origin})
        response = conn.getresponse(); result = json.loads(response.read()); assert response.status == 200
        organizer.worker.join(5)
        conn.request("POST", "/api/chat/organize-state", json.dumps({"chat": result["chat"]}), headers={
            "Content-Type": "application/json", "X-Companion-UI": "1", "Origin": origin})
        response = conn.getresponse(); job = json.loads(response.read())[0]; assert job["state"] == "PREVIEW"
        headers = {"Content-Type": "application/json", "X-Companion-UI": "1", "Origin": origin}
        conn.request("POST", "/api/chat/organize-confirm", json.dumps({"id": job["id"], "approval": job["approval"]}), headers=headers)
        response = conn.getresponse(); assert response.status == 200
        confirmed = json.loads(response.read()); assert confirmed["state"] == "COMPLETED"
        conn.request("POST", "/api/chat/organize-download", json.dumps({"id": job["id"]}), headers=headers)
        response = conn.getresponse(); assert response.status == 200
        download = json.loads(response.read())
        payload = base64.b64decode(download["content"])
        assert hashlib.sha256(payload).hexdigest() == confirmed["output_sha256"]
        with zipfile.ZipFile(io.BytesIO(payload)) as copies:
            assert copies.read("Finance/D1-notes.txt") == base64.b64decode(FILES[0]["content"])
            assert copies.read("Study/D2-notes.txt") == base64.b64decode(FILES[1]["content"])
    finally:
        conn.close(); server.shutdown(); worker.join(5); server.server_close()


def test_cleanup_failure_never_publishes_confirmable_preview(env):
    chat, organizer, rpc = env
    class BadCleanup(Rpc):
        def __exit__(self, *args):
            raise OSError("synthetic private provider message")
    bad = BadCleanup(chat.workspace)
    organizer.client_factory = lambda: bad
    _, job = start(env)
    assert job["state"] == "UNKNOWN" and job["approval"] is None
    assert "private provider" not in (job["error"] or "")
    with chat.connect() as db:
        assert db.execute("SELECT output FROM document_organization").fetchone()[0] is None


def test_changed_request_id_and_stale_owner_do_not_submit(env):
    chat, organizer, rpc = env
    body, job = start(env)
    body["question"] = "A different request"
    with pytest.raises(ChatError):
        invoke(organizer, "start", body)
    body = request(chat)
    body["account"] = "previous-owner"
    with pytest.raises(ChatError):
        invoke(organizer, "start", body)
    assert len([m for m, _ in rpc.calls if m == "turn/start"]) == 1


def test_pinned_runtime_rejects_wrong_executable_before_model(env, monkeypatch, tmp_path):
    chat, organizer, rpc = env
    executable = tmp_path / "codex.exe"
    executable.write_bytes(b"synthetic executable identity")
    organizer.executable = executable
    organizer.client_factory = organizer._client
    calls = []
    def version(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="codex-cli 0.166.0-alpha.5.1")
    monkeypatch.setattr("src.companion_core.organize.subprocess.run", version)
    _, job = start(env)
    assert job["state"] == "FAILED" and "0.162.1" in job["error"]
    assert calls == [[str(executable), "--version"]] and not rpc.calls

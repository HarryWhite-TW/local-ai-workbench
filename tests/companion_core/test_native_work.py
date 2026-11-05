"""Synthetic native RPC only; real proposal/SQLite/Core/ReviewStore boundaries.

These tests do NOT establish native Windows login, model execution, cancellation
or restart support. A normal native-host end-to-end run remains required.
"""
import io
import json
from pathlib import Path
from types import SimpleNamespace
import threading
from uuid import uuid4

import pytest

from src.companion_core.chat import Conversations, now
from src.companion_core.domain import Authority, Execution, Failure
from src.companion_core.native_execution import (
    NativeClient, SETTINGS, answer_from, check_thread, observe_turn, policy, read_turn)
from src.companion_core.native_work import NativeWork, SOURCES, capture_sources
from src.companion_core.review import ReviewError, ReviewStore
from src.companion_core.runtime import RuntimeFailure
from src.companion_core.siwc import ChatError
from src.companion_core.surface import Surface, make_server


class FakeRpc:
    def __init__(self, workspace):
        self.workspace, self.calls = workspace, []
        self.thread, self.turn = "native-thread", "native-turn"
        self.mode = "complete"
        self.messages = []
        self.gate = self.release = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def reply_thread(self):
        return {"thread": {"id": self.thread, "cwd": self.workspace},
                "approvalPolicy": "never", "sandbox": policy(self.workspace)}

    def call(self, method, params):
        self.calls.append((method, params))
        if method == "config/read":
            return {"config": {"mcp_servers": {"existing": {"enabled": True, "env": {"PRIVATE": "synthetic"}}}}}
        if method in ("thread/start", "thread/resume", "thread/read"):
            return self.reply_thread()
        if method == "turn/start":
            if self.mode == "lost_start":
                raise RuntimeFailure(Failure.CONNECTION)
            if self.gate:
                self.gate.set()
            if self.mode == "disconnect":
                self.messages = [None]
            elif self.mode == "cancel":
                self.messages = []
            else:
                item = {"id": "answer", "type": "agentMessage", "text": "Grounded finding: daily.py:1.", "phase": "final_answer"}
                self.messages = [
                    {"method": "turn/completed", "params": {"threadId": "foreign", "turn": {"id": self.turn, "status": "completed"}}},
                    {"method": "item/completed", "params": {"threadId": self.thread, "turnId": "foreign", "item": item}},
                    {"method": "item/completed", "params": {"threadId": self.thread, "turnId": self.turn, "item": item}},
                    {"method": "turn/completed", "params": {"threadId": self.thread,
                        "turn": {"id": self.turn, "status": "failed" if self.mode == "failed" else "completed"}}}]
            return {"turn": {"id": self.turn}}
        if method == "thread/turns/list":
            return {"data": [{"id": "native-turn", "status": "completed", "items": [
                {"id": "answer", "type": "agentMessage", "text": "Recovered finding.", "phase": "final_answer"}]}]}
        raise AssertionError(method)

    def notification(self, timeout):
        if self.release:
            self.release.wait(3)
        if self.messages:
            item = self.messages.pop(0)
            if item is None:
                raise RuntimeFailure(Failure.CONNECTION)
            return item
        raise RuntimeFailure(Failure.TIMEOUT)

    def begin(self, method, params):
        self.calls.append((method, params))
        assert method == "turn/interrupt"
        self.messages = [{"method": "turn/completed", "params": {"threadId": self.thread,
            "turn": {"id": self.turn, "status": "interrupted"}}}]
        return 99


@pytest.fixture
def env(tmp_path):
    root, data = tmp_path / "project", tmp_path / "state"
    root.mkdir(); data.mkdir()
    for name in SOURCES.values():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("def inspect():\n    return 'source'\n", encoding="utf-8")
    auth = SimpleNamespace(pending=None, vault=SimpleNamespace(data={"active": "owner"}))
    auth.snapshot = lambda: {"active": auth.vault.data["active"], "accounts": [], "pending": bool(auth.pending)}
    chat = Conversations(root, data, auth)
    ident, turn = str(uuid4()), str(uuid4())
    with chat.connect() as db:
        db.execute("INSERT INTO chats VALUES (?,?,?,?,?)", (ident, str(root), "owner", "Diagnosis", now()))
        db.execute("""INSERT INTO turns (id,chat,question,answer,sources,model,created,status)
            VALUES (?,?,?,?,?,?,?,?)""", (turn, ident, "Diagnose source", "Ground findings with evidence",
                                        "[]", "synthetic", now(), "complete"))
    rpc = FakeRpc(str(root))
    work = NativeWork(chat, client_factory=lambda: rpc)
    surface = Surface(work, root, ReviewStore(tmp_path / "reviews", workspace=str(root)))
    chat.work, work.surface = work, surface
    yield SimpleNamespace(root=root, chat=chat, work=work, rpc=rpc, surface=surface, ident=ident, turn=turn)
    if surface.worker:
        surface.worker.join(5)


def preview(e):
    p = e.work.create({"chat": e.ident, "turn": e.turn})
    return e.work.preview({"id": p["id"], "goal": p["goal"], "expected": p["expected"],
                           "selection": ["daily", "codex"]})


def start(e, p):
    return e.work.confirm({"id": p["id"], "approval": p["approval"], "authority": "READ_ONLY"})


def finish(e, p):
    started = start(e, p)
    e.surface.worker.join(5)
    assert not e.surface.worker.is_alive()
    return started


def test_full_conversation_to_native_request_to_scoped_receipt(env):
    e = env
    p = preview(e)
    before = {name: (e.root / name).read_bytes() for name in SOURCES.values()}
    started = finish(e, p)
    target = e.surface.target(started["task_id"])
    linked = e.work.state(e.ident)[0]
    assert target["state"] == linked["state"] == "RESULT_PENDING_REVIEW"
    assert linked["review_status"] == "PENDING_REVIEW"
    assert linked["thread_id"] == "native-thread" and linked["turn_id"] == "native-turn"
    assert linked["candidate_id"] in target["result"]
    assert "Grounded finding" in target["result"]
    assert target["independent_review_required"]
    turn = next(params for method, params in e.rpc.calls if method == "turn/start")
    assert turn["clientUserMessageId"] == started["task_id"]
    assert turn["sandboxPolicy"] == policy(str(e.root)) and turn["approvalPolicy"] == "never"
    config = next(params["config"] for method, params in e.rpc.calls if method == "thread/start")
    assert config["mcp_servers"] == {"existing": {"enabled": False}}
    assert "PRIVATE" not in str(config)
    prompt = json.loads(turn["input"][0]["text"])
    assert prompt["source_manifest"] == linked["candidate_id"]
    assert {r["key"] for r in prompt["sources"]} == {"daily", "codex"}
    for name, raw in before.items():
        assert (e.root / name).read_bytes() == raw
    assert e.work.context("work:" + p["id"], e.ident)["text"] == target["result"]
    with pytest.raises(ChatError):
        start(e, p)  # Approval cannot be replayed.


@pytest.mark.parametrize("mode,expected", [("disconnect", "UNKNOWN"), ("lost_start", "UNKNOWN"), ("failed", "FAILED")])
def test_real_terminal_failure_vs_unconfirmed_transport(env, mode, expected):
    e = env; e.rpc.mode = mode
    p = preview(e); finish(e, p)
    assert e.surface.active.task.state == expected
    assert e.work.state(e.ident)[0]["state"] == expected
    assert not e.surface.store.targets()
    reloaded = NativeWork(e.chat, client_factory=lambda: e.rpc)
    reloaded.surface = Surface(reloaded, e.root, e.surface.store)
    assert reloaded.state(e.ident)[0]["state"] == expected
    assert reloaded.surface.snapshot()["tasks"][0]["state"] == expected
    assert sum(m == "turn/start" for m, _ in e.rpc.calls) == 1


def test_restart_reconciliation_never_restarts_turn(env):
    e = env; e.rpc.mode = "disconnect"
    p = preview(e); started = finish(e, p)
    reloaded = NativeWork(e.chat, client_factory=lambda: e.rpc)
    reloaded.surface = Surface(reloaded, e.root, e.surface.store)
    result = reloaded.reconcile({"id": p["id"]})
    assert result["state"] == "RESULT_PENDING_REVIEW"
    assert "Recovered finding" in reloaded.result({"id": p["id"]})["result"]
    assert result["task_id"] == started["task_id"]
    assert sum(m == "turn/start" for m, _ in e.rpc.calls) == 1
    assert not any(m == "thread/resume" for m, _ in e.rpc.calls)


def test_lost_start_identity_cannot_be_guessed_or_retried(env):
    e = env; e.rpc.mode = "lost_start"
    p = preview(e); finish(e, p)
    e.work.reconcile({"id": p["id"]})
    assert e.work.state(e.ident)[0]["state"] == "UNKNOWN"
    assert sum(m == "turn/start" for m, _ in e.rpc.calls) == 1
    with pytest.raises(ChatError):
        e.work.revise({"id": p["id"], "feedback": "Try again"})


def test_stop_needs_matching_terminal_not_only_request(env):
    e = env; e.rpc.mode = "cancel"
    e.rpc.gate, e.rpc.release = threading.Event(), threading.Event()
    p = preview(e); start(e, p)
    assert e.rpc.gate.wait(3)
    stopped = e.work.stop({"id": p["id"]})
    assert stopped["state"] == "CANCEL_REQUESTED"
    assert e.work.state(e.ident)[0]["execution_status"] != "CANCELLED"
    e.rpc.release.set(); e.surface.worker.join(5)
    assert e.surface.active.task.state == "CANCELLED"
    assert e.work.state(e.ident)[0]["state"] == "CANCELLED"
    assert sum(m == "turn/interrupt" for m, _ in e.rpc.calls) == 1


def test_single_revision_same_thread_new_preview_and_no_self_acceptance(env):
    e = env; p = preview(e); started = finish(e, p)
    target = e.surface.target(started["task_id"])
    for action in ("accept", "reject", "revise"):
        with pytest.raises(ReviewError):
            e.surface.decide({"task_id": started["task_id"], "result_id": target["result_id"],
                              "action": action, "revision_intent": "feedback" if action == "revise" else None})
    child = e.work.revise({"id": p["id"], "feedback": "Check one missing edge"})
    assert child["chat"] == p["chat"] and child["parent"] == p["id"]
    with pytest.raises(ChatError):
        e.work.confirm({"id": child["id"], "approval": p["approval"], "authority": "READ_ONLY"})
    child = e.work.preview({"id": child["id"], "goal": child["goal"], "expected": child["expected"],
                           "selection": ["daily", "codex"]})
    e.rpc.turn = "native-turn-revision"
    finish(e, child)
    assert e.work.state(e.ident)[1]["thread_id"] == e.work.state(e.ident)[0]["thread_id"]
    assert sum(m == "thread/start" for m, _ in e.rpc.calls) == 1
    assert sum(m == "thread/resume" for m, _ in e.rpc.calls) == 1
    for parent in (p, child):
        with pytest.raises(ChatError):
            e.work.revise({"id": parent["id"], "feedback": "No third diagnosis"})
    assert e.surface.store.get(started["task_id"]).task.state == "RESULT_PENDING_REVIEW"


@pytest.mark.parametrize("account,pending", [("other", None), (None, None), ("owner", object())])
def test_account_isolation_including_results_recovery_and_emission(env, account, pending):
    e = env; p = preview(e); finish(e, p)
    e.chat.auth.vault.data["active"], e.chat.auth.pending = account, pending
    assert e.surface.snapshot()["tasks"] == []
    for operation, body in [(e.work.result, {"id": p["id"]}), (e.work.reconcile, {"id": p["id"]}),
                            (e.work.stop, {"id": p["id"]}), (e.work.state, e.ident)]:
        with pytest.raises(ChatError):
            operation(body)
    with pytest.raises(ChatError):
        e.work.respond("work-state", {"chat": e.ident}, lambda value: pytest.fail("leaked result"))


def test_changed_source_and_unapproved_scope_rejected(env):
    e = env; p = preview(e)
    (e.root / SOURCES["daily"]).write_text("changed", encoding="utf-8")
    with pytest.raises(ChatError):
        start(e, p)
    assert e.surface.active is None and not e.rpc.calls
    for selection in ([], ["../secret"], ["daily", "daily"], [{}]):
        with pytest.raises(ChatError):
            capture_sources(e.root, selection)


def test_answer_drops_reasoning_and_commentary_rejects_tools():
    assert answer_from([{"type": "reasoning", "text": "private reasoning"},
                        {"type": "agentMessage", "phase": "commentary", "text": "progress"},
                        {"type": "agentMessage", "phase": "final_answer", "text": "finding"}]) == "finding"
    with pytest.raises(RuntimeFailure):
        answer_from([{"type": "commandExecution", "command": "anything"}])


def test_thread_workspace_and_policy_checked(env):
    e = env; r = e.rpc.reply_thread()
    assert check_thread(r, str(e.root), execution=True) == e.rpc.thread
    for key, value in (("approvalPolicy", "onRequest"), ("sandbox", {"type": "workspaceWrite"})):
        bad = dict(r); bad[key] = value
        with pytest.raises(RuntimeFailure):
            check_thread(bad, str(e.root), execution=True)
    with pytest.raises(RuntimeFailure):
        check_thread(r, str(e.root / "other"), execution=True)


def test_readback_exact_turn_only(env):
    e = env
    with pytest.raises(RuntimeFailure):
        read_turn(e.rpc, str(e.root), e.rpc.thread, "different")
    with pytest.raises(RuntimeFailure):
        read_turn(e.rpc, str(e.root), e.rpc.thread, None)


def test_timeout_and_interrupt_ack_alone_cannot_confirm():
    rpc = SimpleNamespace(notification=lambda timeout: {"id": 99, "result": {}})
    with pytest.raises(RuntimeFailure):
        observe_turn(rpc, "thread", "turn", threading.Event(), lambda **kw: None, timeout=0)


def test_native_launch_contract_does_not_copy_or_inject_credentials(env, monkeypatch):
    e = env; captured = {}
    executable = e.root / "codex.exe"; executable.write_bytes(b"synthetic")
    monkeypatch.setenv("OPENAI_API_KEY", "SYNTHETIC_PRIVATE_ENV")
    monkeypatch.setenv("ACCESS_TOKEN", "SYNTHETIC_PRIVATE_ENV")
    monkeypatch.setenv("CODEX_HOME", "SYNTHETIC_ALTERNATE_HOME")
    class Process:
        stdin, stdout = io.StringIO(), io.StringIO("")
        def wait(self, timeout): return 0
    def popen(command, **kwargs):
        captured.update(command=command, **kwargs)
        return Process()
    monkeypatch.setattr("src.companion_core.native_execution.subprocess.Popen", popen)
    monkeypatch.setattr(NativeClient, "call", lambda self, method, params:
                        {"account": {"type": "chatgpt"}} if method == "account/read" else {})
    with NativeClient(e.chat.path.parent, executable):
        pass
    assert not {"ACCESS_TOKEN", "OPENAI_API_KEY", "CODEX_HOME"} & captured["env"].keys()
    command = captured["command"]
    assert command[:4] == [str(executable), "app-server", "--listen", "stdio://"]
    for setting in ('mcp_servers={}', 'notify=[]', 'features.shell_tool=false',
                    'features.unified_exec=false', 'features.plugins=false', 'features.hooks=false'):
        assert setting in command
    assert "externalSandbox" not in str(command) and "danger-full-access" not in str(command)


def test_http_routes_reuse_same_proposal_and_guard_without_socket(env, monkeypatch):
    e = env
    class Server:
        def __init__(self, address, handler):
            self.server_port, self.handler = 9123, handler
    monkeypatch.setattr("src.companion_core.surface.ThreadingHTTPServer", Server)
    server = make_server(e.surface, e.chat, e.work)
    def post(path, body, origin="http://127.0.0.1:9123"):
        handler = object.__new__(server.handler); handler.server = server
        raw = json.dumps(body).encode()
        handler.path, handler.client_address, handler.rfile = path, ("127.0.0.1", 9999), io.BytesIO(raw)
        handler.headers = {"Host": "127.0.0.1:9123", "Origin": origin, "X-Companion-UI": "1",
                           "Content-Type": "application/json", "Content-Length": str(len(raw))}
        replies = []; handler._reply = lambda code, data, *args: replies.append((code, data))
        handler.do_POST()
        return replies[-1]
    assert post("/api/start", {"intent": "bypass"})[0] == 409
    assert post("/api/chat/work-create", {"chat": e.ident, "turn": e.turn}, "https://foreign.invalid")[0] == 403
    code, proposal = post("/api/chat/work-create", {"chat": e.ident, "turn": e.turn})
    assert code == 200 and proposal["kind"] == "native_codex"
    code, p = post("/api/chat/work-preview", dict(id=proposal["id"], goal=proposal["goal"],
        expected=proposal["expected"], selection=["daily", "codex"]))
    assert code == 200
    code, started = post("/api/chat/work-confirm", dict(id=p["id"], approval=p["approval"], authority="READ_ONLY"))
    assert code == 200
    e.surface.worker.join(5)
    code, result = post("/api/chat/work-result", {"id": p["id"]})
    assert code == 200 and result["review_status"] == "PENDING_REVIEW"
    assert post("/api/review", dict(task_id=started["task_id"], result_id=result["result_id"],
                                   action="accept", revision_intent=None))[0] == 409

@pytest.mark.parametrize("scenario", [
    test_full_conversation_to_native_request_to_scoped_receipt,
    test_restart_reconciliation_never_restarts_turn,
    test_single_revision_same_thread_new_preview_and_no_self_acceptance,
    test_http_routes_reuse_same_proposal_and_guard_without_socket,
])
def test_synthetic_receipt_io_contract_only(env, monkeypatch, scenario):
    # Deliberate storage double: validates wiring, never hardlink atomicity.
    # The four original tests above still run against unmodified real ReviewStore.
    from src.companion_core.review import _encoded
    def synthetic_publish(self, path, value):
        self.directory.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as f:
            f.write(_encoded(value))
    monkeypatch.setattr(ReviewStore, "_publish", synthetic_publish)
    if scenario is test_http_routes_reuse_same_proposal_and_guard_without_socket:
        scenario(env, monkeypatch)
    else:
        scenario(env)

def test_actual_hardlink_persistence_fails_closed(env, monkeypatch):
    def denied(*args, **kwargs):
        raise PermissionError("synthetic OS denial")
    monkeypatch.setattr("src.companion_core.review.os.link", denied)
    p = preview(env)
    finish(env, p)
    assert env.surface.active.task.state == "RESULT_PENDING_REVIEW"
    assert env.surface.notice
    assert not env.surface.store.targets()
    assert env.work.state(env.ident)[0]["result_id"] is None

# First-use regression: synthetic RPC responses; no native process/model is launched.
@pytest.mark.parametrize("code,message,kind,definite", [
    (-32602, "SYNTHETIC_PRIVATE_RPC_DETAIL", "invalid_parameters", True),
    (-32603, "SYNTHETIC_PRIVATE_RPC_DETAIL", "request_rejected", False),
    (-32603, "windows unelevated restricted-token sandbox cannot enforce split filesystem read restrictions directly; refusing to run unsandboxed",
     "windows_read_restriction_unsupported", True),
])
def test_native_rpc_rejection_preserves_safe_correlated_fact(code, message, kind, definite):
    import queue
    from src.companion_core.native_execution import RpcRejected
    rpc = NativeClient.__new__(NativeClient)
    rpc.process = SimpleNamespace(stdin=io.StringIO())
    rpc.sequence, rpc.saved, rpc.messages = 0, [], queue.Queue()
    rpc.messages.put({"id": 998, "error": {"code": -32602, "message": "foreign"}})
    rpc.messages.put({"id": 1, "error": {"code": code, "message": message, "data": {"private": "omit"}}})
    with pytest.raises(RpcRejected) as caught:
        rpc.call("turn/start", {"threadId": "owned"})
    error = caught.value
    assert (error.method, error.code, error.kind, error.definitely_not_started) == ("turn/start", code, kind, definite)
    assert message not in str(error) and "private" not in str(error.__dict__)
    assert len(rpc.saved) == 1 and rpc.saved[0]["id"] == 998


@pytest.mark.parametrize("code,message,expected,outcome", [
    (-32602, "SYNTHETIC_PRIVATE_RPC_DETAIL", "FAILED", "REJECTED"),
    (-32603, "SYNTHETIC_PRIVATE_RPC_DETAIL", "UNKNOWN", "UNKNOWN"),
    (-32603, "windows unelevated restricted-token sandbox cannot enforce split filesystem read restrictions directly; refusing to run unsandboxed",
     "FAILED", "REJECTED"),
])
def test_first_use_turn_start_rejected_vs_uncertain(env, code, message, expected, outcome):
    from src.companion_core.native_execution import RpcRejected
    e = env
    original = e.rpc.call
    def call(method, params):
        if method == "turn/start":
            e.rpc.calls.append((method, params))
            raise RpcRejected.from_error(method, {"code": code, "message": message})
        return original(method, params)
    e.rpc.call = call
    p = preview(e); finish(e, p)
    linked = e.work.state(e.ident)[0]
    assert e.surface.active.task.state == linked["state"] == expected
    assert linked["failure_stage"] == "turn/start" and linked["failure_code"] == code
    assert linked["start_outcome"] == outcome and linked["turn_id"] is None
    assert message not in json.dumps(linked)
    assert linked["result_id"] is None
    before = len(e.rpc.calls)
    if expected == "FAILED":
        assert e.work.reconcile({"id": p["id"]})["state"] == "FAILED"
        assert len(e.rpc.calls) == before
    assert sum(m == "turn/start" for m, _ in e.rpc.calls) == 1
    reloaded = NativeWork(e.chat, client_factory=lambda: e.rpc)
    reloaded.surface = Surface(reloaded, e.root, e.surface.store)
    assert reloaded.state(e.ident)[0]["state"] == expected


def test_first_use_pre_turn_transport_failure_is_not_sent(env):
    e = env; original = e.rpc.call
    def call(method, params):
        if method == "config/read":
            raise RuntimeFailure(Failure.CONNECTION)
        return original(method, params)
    e.rpc.call = call
    p = preview(e); finish(e, p)
    linked = e.work.state(e.ident)[0]
    assert linked["state"] == "FAILED" and linked["start_outcome"] == "NOT_SENT"
    assert linked["failure_stage"] == "config/read"
    assert not any(m == "turn/start" for m, _ in e.rpc.calls)


def test_first_use_malformed_turn_reply_stays_unknown(env):
    e = env; original = e.rpc.call
    def call(method, params):
        if method == "turn/start":
            e.rpc.calls.append((method, params))
            return {"turn": {}}
        return original(method, params)
    e.rpc.call = call
    p = preview(e); finish(e, p)
    linked = e.work.state(e.ident)[0]
    assert linked["state"] == "UNKNOWN" and linked["start_outcome"] == "UNKNOWN"
    assert not linked["can_hide_draft"]


def test_first_use_create_reuses_draft_and_unknown_identity(env):
    e = env; p = preview(e)
    again = e.work.create({"chat": e.ident, "turn": e.turn})
    assert again["id"] == p["id"] and again["goal"] == p["goal"]
    e.rpc.mode = "lost_start"; finish(e, p)
    calls = len(e.rpc.calls)
    linked = e.work.create({"chat": e.ident, "turn": e.turn})
    assert linked["id"] == p["id"] and linked["state"] == "UNKNOWN"
    assert len(e.rpc.calls) == calls
    with e.chat.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM work_proposals").fetchone()[0] == 1
    with pytest.raises(ChatError):
        e.work.draft_visibility({"id": p["id"], "hidden": True})


def test_first_use_draft_fold_restore_invalidates_preview_authority(env):
    e = env; p = preview(e)
    hidden = e.work.draft_visibility({"id": p["id"], "hidden": True})
    assert hidden["draft_hidden"] and hidden["can_hide_draft"] and hidden["task_id"] is None
    with pytest.raises(ChatError):
        start(e, p)
    restored = e.work.create({"chat": e.ident, "turn": e.turn})
    assert restored["id"] == p["id"] and not restored["draft_hidden"]
    with pytest.raises(ChatError):
        start(e, p)  # Restoring never restores an old approval.
    assert not e.rpc.calls


@pytest.mark.parametrize("mode", ["lost_start", "failed"])
def test_first_use_bound_work_is_never_a_hideable_draft(env, mode):
    e = env; e.rpc.mode = mode; p = preview(e); finish(e, p)
    with pytest.raises(ChatError):
        e.work.draft_visibility({"id": p["id"], "hidden": True})
    assert not e.work.state(e.ident)[0]["can_hide_draft"]


def test_first_use_legacy_unknown_is_not_relabelled_not_started(env):
    e = env; p = preview(e); task_id = str(uuid4())
    with e.chat.connect() as db:
        db.execute("UPDATE work_proposals SET task_id=? WHERE id=?", (task_id, p["id"]))
        db.execute("UPDATE native_work SET thread_id=?,state='UNKNOWN' WHERE proposal=?", ("native-thread", p["id"]))
    linked = e.work.state(e.ident)[0]
    assert linked["state"] == "UNKNOWN" and linked["start_outcome"] is None
    assert e.work.reconcile({"id": p["id"]})["state"] == "UNKNOWN"
    assert not any(m == "turn/start" for m, _ in e.rpc.calls)


def test_first_use_account_guard_covers_draft_reuse_and_visibility(env):
    e = env; p = preview(e)
    e.chat.auth.vault.data["active"] = "other"
    with pytest.raises(ChatError):
        e.work.create({"chat": e.ident, "turn": e.turn})
    with pytest.raises(ChatError):
        e.work.draft_visibility({"id": p["id"], "hidden": True})


def _official_01621_turn_schema():
    return json.loads((Path(__file__).parent / "fixtures" / "codex_0_162_1_TurnStartParams.json").read_text(encoding="utf-8"))


def test_turn_start_readonly_matches_official_declared_fields():
    # Declaration compatibility check, not a live-server/deserializer claim.
    schema = _official_01621_turn_schema()
    readonly = next(v for v in schema["definitions"]["SandboxPolicy"]["oneOf"]
                    if v.get("properties", {}).get("type", {}).get("enum") == ["readOnly"])
    actual = policy(r"C:\approved-project")
    assert actual == {"type": "readOnly", "networkAccess": False}
    assert set(actual) <= set(readonly["properties"])
    assert set(readonly["required"]) <= set(actual)
    assert type(actual["networkAccess"]) is bool
    legacy = {**actual, "access": {"type": "restricted", "includePlatformDefaults": False,
                                  "readableRoots": [r"C:\approved-project"]}}
    assert set(legacy) - set(readonly["properties"]) == {"access"}
    assert 'sandbox_mode="read-only"' in SETTINGS
    assert 'approval_policy="never"' in SETTINGS
    assert 'features.shell_tool=false' in SETTINGS
    assert 'features.unified_exec=false' in SETTINGS
    assert 'features.plugins=false' in SETTINGS


def test_turn_start_snapshot_payload_declared_by_01621(env):
    e = env
    e.rpc.mode = "failed"  # Terminal fixture: tests the actual request without receipt I/O.
    p = preview(e); started = finish(e, p)
    params = next(v for m, v in e.rpc.calls if m == "turn/start")
    schema = _official_01621_turn_schema()
    assert set(params) <= set(schema["properties"])
    assert set(schema["required"]) <= set(params)
    assert params["sandboxPolicy"] == {"type": "readOnly", "networkAccess": False}
    assert params["approvalPolicy"] == "never"
    assert params["clientUserMessageId"] == started["task_id"]
    assert params["threadId"] == e.rpc.thread
    assert params["cwd"] == str(e.root)
    assert len(params["input"]) == 1
    item = params["input"][0]
    text_variant = next(v for v in schema["definitions"]["UserInput"]["oneOf"]
                        if v.get("properties", {}).get("type", {}).get("enum") == ["text"])
    assert set(item) <= set(text_variant["properties"])
    assert set(text_variant["required"]) <= set(item)
    prompt = json.loads(item["text"])
    assert {r["key"] for r in prompt["sources"]} == {"daily", "codex"}
    assert prompt["source_manifest"] == e.work.state(e.ident)[0]["candidate_id"]
    assert all(r["text"] == (e.root / r["name"]).read_bytes().decode("utf-8-sig") for r in prompt["sources"])


def test_turn_start_invalid_request_remains_explicit_failure(env):
    from src.companion_core.native_execution import RpcRejected
    e = env; original = e.rpc.call
    def call(method, params):
        if method == "turn/start":
            e.rpc.calls.append((method, params))
            raise RpcRejected.from_error(method, {"code": -32600, "message": "SYNTHETIC_REQUEST_REJECTED"})
        return original(method, params)
    e.rpc.call = call
    p = preview(e); finish(e, p)
    state = e.work.state(e.ident)[0]
    assert state["state"] == "FAILED" and state["failure_stage"] == "turn/start"
    assert state["failure_code"] == -32600 and state["start_outcome"] == "REJECTED"
    assert state["turn_id"] is None and state["result_id"] is None
    assert sum(m == "turn/start" for m, _ in e.rpc.calls) == 1
    assert e.work.create({"chat": e.ident, "turn": e.turn})["id"] == p["id"]


def test_ux02_preview_shows_only_exact_authorized_snapshots(env):
    p = preview(env)
    assert [r['key'] for r in p['source_snapshots']] == ['daily', 'codex']
    for snapshot, manifest in zip(p['source_snapshots'], p['manifest']):
        assert {k: snapshot[k] for k in manifest} == manifest
        assert snapshot['text'] == (env.root / manifest['name']).read_bytes().decode('utf-8-sig')
    assert not env.rpc.calls


def test_ux02_preview_drift_between_manifest_and_display_fails_closed(env):
    capture = env.work.capture
    count = 0
    def changing(root, selection):
        nonlocal count
        count += 1
        if count == 2:
            (env.root / SOURCES['daily']).write_text('changed snapshot', encoding='utf-8')
        return capture(root, selection)
    env.work.capture = changing
    with pytest.raises(ChatError, match='來源已變更'):
        preview(env)
    assert not env.rpc.calls


def test_ux02_presentation_preserves_model_excerpts_without_claiming_acceptance():
    from src.companion_core.native_work import diagnosis_presentation
    report = 'Codex 唯讀工程診斷（模型輸出，未經獨立技術審查）\nThread: identity\n\n## 結論\nNeeds review.\n## 程式碼依據\nwork.py L124 checks authority.\n## 下一步\nInspect source drift.\n## 限制\nNo tests executed.'
    view = diagnosis_presentation(report)
    assert view['overview'] == 'Needs review.'
    assert view['evidence'] == 'work.py L124 checks authority.'
    assert view['next_steps'] == 'Inspect source drift.'
    assert view['limitations'] == 'No tests executed.'
    legacy = diagnosis_presentation('Legacy diagnosis with unknown layout.')
    assert legacy['overview'] == 'Legacy diagnosis with unknown layout.'
    assert not legacy['next_steps'] and 'acceptance' not in view


def test_ux02_result_projection_retains_original_reviewstore_report(env):
    p = preview(env)
    finish(env, p)
    result = env.work.result({'id': p['id']})
    persisted = env.surface.target(result['task_id'])
    assert result['result'] == persisted['result']
    assert result['result_id'] == persisted['result_id']
    assert result['review_status'] == 'PENDING_REVIEW'
    assert result['presentation']['overview']

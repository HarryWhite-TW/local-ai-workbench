import json
import subprocess
import sys

import pytest

from src.companion_core.codex import CodexRuntime, POLICY, SETTINGS, _Rpc
from src.companion_core.core import Companion
from src.companion_core.domain import Authority
from src.companion_core.runtime import EventKind, Request


REQUEST = Request("Inspect", ".", Authority.READ_ONLY)


def notification(method, **params):
    return {"method": method, "params": {"threadId": "session", "turnId": "turn", **params}}


class FakeRpc:
    def __init__(self, status="completed", sandbox=None, approval="never"):
        self.calls = []
        self.sandbox = sandbox if sandbox is not None else dict(POLICY)
        self.approval = approval
        self.messages = iter([
            notification("turn/completed", threadId="other", turn={"id": "turn", "status": "completed"}),
            notification("item/completed", turnId="old", item={"type": "agentMessage", "text": "wrong"}),
            notification("item/started", item={"type": "commandExecution"}),
            notification("item/agentMessage/delta", delta="not exposed"),
            notification("item/completed", item={"type": "agentMessage", "text": "result"}),
            notification("turn/completed", turn={"id": "old", "status": "completed"}),
            notification("turn/completed", turn={"id": "turn", "status": status}),
        ])

    def call(self, method, params):
        self.calls.append((method, params))
        if method == "thread/start":
            return {"thread": {"id": "session"}, "sandbox": self.sandbox,
                    "approvalPolicy": self.approval}
        if method == "turn/start":
            return {"turn": {"id": "turn"}}
        return {}

    def send(self, message):
        pass

    def notification(self, timeout):
        return next(self.messages)


def test_adapter_translates_and_binds_only_matching_events():
    rpc = FakeRpc()
    events = list(CodexRuntime("unused", "model", lambda: "synthetic")._execute(rpc, REQUEST, "synthetic"))
    assert [e.kind for e in events] == [EventKind.SESSION, EventKind.INSPECTING,
                                      EventKind.RECEIVING, EventKind.COMPLETED]
    assert events[0].session_id == "session"
    assert events[-1].text == "result"
    assert "thread/start" not in repr(events) and "not exposed" not in repr(events)
    calls = dict(rpc.calls)
    assert calls["thread/start"]["sandbox"] == "read-only"
    assert calls["turn/start"]["sandboxPolicy"] == POLICY
    assert calls["turn/start"]["approvalPolicy"] == "never"


@pytest.mark.parametrize("sandbox,approval", [({}, "never"),
    ({"type": "dangerFullAccess"}, "never"),
    ({"type": "readOnly", "networkAccess": True}, "never"),
    (POLICY, "on-request")])
def test_policy_downgrade_never_starts_turn(sandbox, approval):
    rpc = FakeRpc(sandbox=sandbox, approval=approval)
    with pytest.raises(PermissionError):
        list(CodexRuntime("unused", "model", lambda: "synthetic")._execute(rpc, REQUEST, "synthetic"))
    assert "turn/start" not in dict(rpc.calls)


@pytest.mark.parametrize("status,kind", [("failed", EventKind.FAILED),
    ("interrupted", EventKind.CANCELLED), ("unknown", EventKind.FAILED)])
def test_adapter_terminal_translation(status, kind):
    events = list(CodexRuntime("unused", "model", lambda: "synthetic")._execute(FakeRpc(status), REQUEST, "synthetic"))
    assert events[-1].kind == kind
    assert events[-1].text is None


def test_no_authority_no_credential_or_process():
    def forbidden():
        raise AssertionError("Credential boundary must not be reached")
    with pytest.raises(PermissionError):
        list(CodexRuntime("unused", "model", forbidden).run(Request("Inspect", ".", Authority.NONE)))


def test_real_pipe_transport_and_host_boundary(tmp_path, monkeypatch):
    # Synthetic protocol peer: no OAuth material and no live model use in tests.
    script = tmp_path / "peer.py"
    script.write_text('''import json, sys
def send(value):
 print(json.dumps(value), flush=True)
for line in sys.stdin:
 m=json.loads(line)
 method=m.get("method")
 if method=="initialize": send({"id":m["id"],"result":{}})
 elif method=="thread/start":
  send({"id":m["id"],"result":{"thread":{"id":"session"},"sandbox":{"type":"readOnly","networkAccess":False},"approvalPolicy":"never"}})
 elif method=="turn/start":
  send({"method":"item/agentMessage/delta","params":{"threadId":"session","turnId":"turn","delta":"fragment"}})
  send({"id":m["id"],"result":{"turn":{"id":"turn"}}})
  send({"id":900,"method":"item/commandExecution/requestApproval","params":{}})
 elif m.get("id")==900:
  assert "error" in m and "result" not in m
  send({"method":"item/completed","params":{"threadId":"session","turnId":"turn","item":{"type":"agentMessage","text":"result synthetic"}}})
  send({"method":"turn/completed","params":{"threadId":"session","turn":{"id":"turn","status":"completed"}}})
''', encoding="utf-8")
    original = subprocess.Popen
    children = []

    def launch(command, **kwargs):
        assert "sandbox_mode=\"read-only\"" in command
        assert kwargs["env"]["ACCESS_TOKEN"] == "synthetic"
        assert "OPENAI_API_KEY" not in kwargs["env"]
        assert "PYTHONPATH" not in kwargs["env"]
        assert 'shell_environment_policy.exclude=["ACCESS_TOKEN","OPENAI_API_KEY","OPENAI_ACCESS_TOKEN"]' in SETTINGS
        assert not str(kwargs["cwd"]).startswith(str(tmp_path))
        p = original([sys.executable, "-u", str(script)], **kwargs)
        children.append(p)
        return p

    monkeypatch.setattr(subprocess, "Popen", launch)
    core = Companion(CodexRuntime("unused", "model", lambda: "synthetic"),
                     "Inspect", str(tmp_path), Authority.READ_ONLY)
    events = []
    task = core.run(events.append)
    assert task.state == "RESULT_PENDING_REVIEW"
    assert task.result == "result [credential redacted]"
    assert "receiving_result" in [e.stage for e in events]
    assert "synthetic" not in repr(task) + repr(events)
    assert all(p.poll() == 0 for p in children)


def test_transport_errors_and_unknown_requests_fail_closed():
    class Input:
        def __init__(self):
            self.sent = []
        def write(self, data):
            self.sent.append(json.loads(data))
        def flush(self):
            pass
    class Process:
        stdin = Input()
        stdout = iter([json.dumps({"id": 40, "method": "future/escalation"}),
                       json.dumps({"id": 1, "error": {"message": "sensitive body"}})])
    process = Process()
    rpc = _Rpc(process)
    with pytest.raises(RuntimeError, match="Runtime request failed"):
        rpc.call("initialize", {})
    assert any(m.get("id") == 40 and "error" in m for m in process.stdin.sent)

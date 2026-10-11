"""Codex 0.158 app-server adapter. OAuth acquisition/validation belongs to the host.

The credential callback returns a validated, short-lived ChatGPT-plan token.
It must not return an API key. Nothing here implements OAuth or stores tokens.
"""
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
from typing import Callable

from .domain import Authority, Failure
from .runtime import EventKind, Request, RuntimeEvent, RuntimeFailure


POLICY = {"type": "readOnly", "networkAccess": False}
SETTINGS = (
    'model_provider="openai_chatgpt_plan"',
    'model_providers.openai_chatgpt_plan.name="ChatGPT plan"',
    'model_providers.openai_chatgpt_plan.base_url="https://api.openai.com/v1"',
    'model_providers.openai_chatgpt_plan.env_key="ACCESS_TOKEN"',
    'model_providers.openai_chatgpt_plan.wire_api="responses"',
    'model_providers.openai_chatgpt_plan.requires_openai_auth=false',
    'model_providers.openai_chatgpt_plan.supports_websockets=false',
    'sandbox_mode="read-only"', 'approval_policy="never"',
    'windows.sandbox="unelevated"', 'shell_environment_policy.inherit="core"',
    'shell_environment_policy.exclude=["ACCESS_TOKEN","OPENAI_API_KEY","OPENAI_ACCESS_TOKEN"]',
    'features.multi_agent=false', 'features.shell_snapshot=false',
    'web_search="disabled"', 'analytics.enabled=false', 'otel.log_user_prompt=false',
)


class _Rpc:
    def __init__(self, process):
        self.process = process
        self.messages = queue.Queue()
        self.saved = []
        self.sequence = 0
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            for line in self.process.stdout:
                self.messages.put(json.loads(line))
        except (json.JSONDecodeError, UnicodeError):
            self.messages.put(RuntimeFailure(Failure.PROTOCOL))
        except Exception:
            pass
        finally:
            # Only the reader closes stdout. Closing it from the execution owner
            # can block on this thread's read lock if host reconciliation failed.
            close = getattr(self.process.stdout, "close", None)
            if close:
                try:
                    close()
                except Exception:
                    pass
            self.messages.put(None)

    def finish(self):
        # EOF may remain unavailable after an unconfirmed host cleanup.
        self.reader.join(timeout=.2)

    def send(self, message):
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def receive(self, timeout):
        deadline = time.monotonic() + timeout
        while True:
            try:
                message = self.messages.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty:
                raise RuntimeFailure(Failure.TIMEOUT) from None
            if isinstance(message, RuntimeFailure):
                raise message
            if message is None:
                raise RuntimeFailure(Failure.CONNECTION)
            if not isinstance(message, dict):
                raise RuntimeFailure(Failure.PROTOCOL)
            if "id" in message and "method" in message:
                # Never approve a capability escalation, external tool or input request.
                self.send({"id": message["id"], "error": {
                    "code": -32601, "message": "Read-only Companion denies this request"}})
                continue
            return message

    def begin(self, method, params):
        self.sequence += 1
        ident = self.sequence
        self.send({"id": ident, "method": method, "params": params})
        return ident

    def call(self, method, params):
        ident = self.begin(method, params)
        deadline = time.monotonic() + 30
        while True:
            message = self.receive(max(0, deadline - time.monotonic()))
            if message.get("id") == ident:
                if "error" in message:
                    raise RuntimeError("Runtime request failed")
                if "result" not in message:
                    raise RuntimeFailure(Failure.PROTOCOL)
                return message["result"]
            self.saved.append(message)

    def notification(self, timeout):
        return self.saved.pop(0) if self.saved else self.receive(timeout)


def _redact(text, token):
    text = text.replace(token, "[credential redacted]")
    return re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
                  "[credential redacted]", text)


def _windows_processes():
    """Metadata only. No command lines, credentials or process bodies."""
    shell = str(Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe")
    script = (
        "$ErrorActionPreference='Stop'; "
        "@(Get-CimInstance Win32_Process | Where-Object { $_.CreationDate } | "
        "Select-Object ProcessId,ParentProcessId,"
        "@{n='Created';e={$_.CreationDate.ToUniversalTime().ToString('o')}}) | "
        "ConvertTo-Json -Compress")
    result = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW, check=True)
    rows = json.loads(result.stdout)
    if not isinstance(rows, list):
        raise RuntimeFailure(Failure.CANCELLATION)
    return {int(p["ProcessId"]): (int(p["ParentProcessId"]), p["Created"]) for p in rows}


def _reconcile_windows_tree(process):
    """One owner, one tree kill, then verify all known identities are gone.

    Keep the Popen process handle open throughout: never reacquire a root by name.
    An already-lost root or ambiguous snapshot cannot confirm cancellation.
    """
    try:
        if os.name != "nt" or process.poll() is not None:
            raise RuntimeFailure(Failure.CANCELLATION)
        before = _windows_processes()
        root = before.get(process.pid)
        if root is None or root[0] != os.getpid():
            raise RuntimeFailure(Failure.CANCELLATION)
        owned = {process.pid: root}
        while True:
            added = False
            for pid, identity in before.items():
                parent, created = identity
                if parent in owned and pid not in owned:
                    if created < owned[parent][1]:
                        raise RuntimeFailure(Failure.CANCELLATION)
                    owned[pid] = identity
                    added = True
            if not added:
                break
        if process.poll() is not None:
            raise RuntimeFailure(Failure.CANCELLATION)
        killer = str(Path(os.environ["SystemRoot"]) / "System32/taskkill.exe")
        result = subprocess.run([killer, "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
        if result.returncode != 0:
            raise RuntimeFailure(Failure.CANCELLATION)
        process.wait(timeout=5)
        deadline = time.monotonic() + 5
        while True:
            after = _windows_processes()
            if not any(after.get(pid) == identity for pid, identity in owned.items()):
                return
            if time.monotonic() >= deadline:
                raise RuntimeFailure(Failure.CANCELLATION)
            time.sleep(.1)
    except Exception:
        raise RuntimeFailure(Failure.CANCELLATION) from None


class CodexRuntime:
    provider_id = "codex-app-server"

    def __init__(self, executable: str, model: str, credential: Callable[[], str],
                 timeout: float = 180):
        self.executable = executable
        self.model = model
        self._credential = credential
        self.timeout = timeout

    def run(self, request: Request):
        if request.authority is not Authority.READ_ONLY:
            raise PermissionError("Only read-only execution is supported")
        try:
            token = self._credential()
        except Exception:
            raise RuntimeFailure(Failure.AUTHENTICATION) from None
        if not token or token.startswith("sk-"):
            raise RuntimeFailure(Failure.AUTHENTICATION)
        env = {k: v for k, v in os.environ.items() if k.upper() in {
            "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "USERPROFILE",
            "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "PROGRAMFILES",
            "PROGRAMFILES(X86)", "PROGRAMDATA"}}
        # A fresh home avoids inherited provider, plugin and MCP configuration.
        state_dir = tempfile.TemporaryDirectory(prefix="companion-codex-")
        try:
            state = state_dir.name
            if Path(state).resolve().is_relative_to(Path(request.workspace).resolve()):
                raise RuntimeFailure(Failure.POLICY)
            env.update(CODEX_HOME=state, ACCESS_TOKEN=token, RUST_LOG="off")
            command = [self.executable, "app-server", "--listen", "stdio://"]
            for setting in SETTINGS:
                command.extend(["-c", setting])
            process = subprocess.Popen(command, cwd=state, env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", creationflags=(subprocess.CREATE_NO_WINDOW
                    if os.name == "nt" else 0))
            rpc = _Rpc(process)
            reconciliation_attempted = False
            completed = False
            try:
                for event in self._execute(rpc, request, token):
                    if event.kind == EventKind.INTERRUPTED:
                        reconciliation_attempted = True
                        _reconcile_windows_tree(process)
                        yield RuntimeEvent(EventKind.CANCELLED)
                    else:
                        completed = event.kind == EventKind.COMPLETED
                        yield event
            finally:
                try:
                    # A pending Stop with failed transport still needs owned-host
                    # cleanup, but cleanup alone never fabricates Interrupted.
                    if not completed and not reconciliation_attempted and request.cancel_requested is not None and request.cancel_requested.is_set():
                        reconciliation_attempted = True
                        if process.poll() is None:
                            _reconcile_windows_tree(process)
                    if not reconciliation_attempted:
                        process.stdin.close()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            if os.name == "nt":
                                _reconcile_windows_tree(process)
                            else:
                                process.kill()
                                process.wait(timeout=5)
                finally:
                    process.stdin.close()
                    rpc.finish()
        finally:
            prior = sys.exc_info()[1]
            try:
                state_dir.cleanup()
            except Exception:
                # A failed owned-tree reconciliation already means cancellation
                # is unconfirmed. Preserve that reason if its state dir is locked.
                if not (isinstance(prior, RuntimeFailure)
                        and prior.reason == Failure.CANCELLATION):
                    raise

    def _execute(self, rpc, request, token):
        rpc.call("initialize", {"clientInfo": {"name": "companion_core",
                 "title": "Companion Core", "version": "0.1.0"}})
        rpc.send({"method": "initialized", "params": {}})
        started = rpc.call("thread/start", {"model": self.model,
            "modelProvider": "openai_chatgpt_plan", "cwd": request.workspace,
            "sandbox": "read-only", "approvalPolicy": "never"})
        sandbox = started.get("sandbox", {})
        if (sandbox.get("type") != "readOnly" or sandbox.get("networkAccess", False) is not False
                or started.get("approvalPolicy") != "never"):
            raise RuntimeFailure(Failure.POLICY)
        session = started.get("thread", {}).get("id")
        if not isinstance(session, str) or not session:
            raise RuntimeFailure(Failure.PROTOCOL)
        yield RuntimeEvent(EventKind.SESSION, session_id=session)
        turn = rpc.call("turn/start", {"threadId": session, "cwd": request.workspace,
            "approvalPolicy": "never", "sandboxPolicy": dict(POLICY),
            "input": [{"type": "text", "text": request.intent}]})["turn"]["id"]
        if not isinstance(turn, str) or not turn:
            raise RuntimeFailure(Failure.PROTOCOL)
        deadline = time.monotonic() + self.timeout
        answer = ""
        interrupt_id = None
        interrupt_acknowledged = False
        interrupted = False
        interrupt_failed = False
        while True:
            if time.monotonic() >= deadline:
                raise RuntimeFailure(Failure.CANCELLATION if interrupt_id is not None else Failure.TIMEOUT)
            try:
                message = rpc.notification(min(.1, max(0, deadline - time.monotonic())))
            except RuntimeFailure as exc:
                if exc.reason != Failure.TIMEOUT:
                    raise
                message = {}
            # Only this execution owner consumes RPC messages or sends interrupt.
            # Consume queued terminal truth before considering a Stop signal.
            if interrupt_id is not None and message.get("id") == interrupt_id:
                interrupt_acknowledged = "error" not in message and message.get("result") == {}
                interrupt_failed = not interrupt_acknowledged
            params = message.get("params", {})
            method = message.get("method")
            if method == "turn/completed" and params.get("threadId") == session:
                terminal = params.get("turn", {})
                if terminal.get("id") == turn:
                    status = terminal.get("status")
                    if status == "completed":
                        yield RuntimeEvent(EventKind.COMPLETED, text=_redact(answer, token))
                        return
                    if status != "interrupted":
                        yield RuntimeEvent(EventKind.FAILED)
                        return
                    if interrupt_id is None:
                        raise RuntimeFailure(Failure.CANCELLATION)
                    interrupted = True
            if interrupted and interrupt_acknowledged:
                yield RuntimeEvent(EventKind.INTERRUPTED)
                return
            if interrupted and interrupt_failed:
                raise RuntimeFailure(Failure.CANCELLATION)
            if (interrupt_id is None and request.cancel_requested is not None
                    and request.cancel_requested.is_set()):
                # Mark submission before writing; a write failure must never retry.
                interrupt_id = rpc.begin("turn/interrupt", {"threadId": session, "turnId": turn})
                deadline = min(deadline, time.monotonic() + 15)
            if params.get("threadId") != session or params.get("turnId") != turn:
                continue
            if method == "item/agentMessage/delta":
                # Progress only: never leak a token split across streaming chunks.
                yield RuntimeEvent(EventKind.RECEIVING)
            elif method == "item/started" and params.get("item", {}).get("type") == "commandExecution":
                yield RuntimeEvent(EventKind.INSPECTING)
            elif method == "item/completed" and params.get("item", {}).get("type") == "agentMessage":
                answer = params["item"].get("text", "")

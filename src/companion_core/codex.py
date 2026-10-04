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
import tempfile
import threading
import time
from typing import Callable

from .domain import Authority
from .runtime import EventKind, Request, RuntimeEvent


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
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            for line in self.process.stdout:
                self.messages.put(json.loads(line))
        except Exception:
            pass
        finally:
            self.messages.put(None)

    def send(self, message):
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def receive(self, timeout):
        deadline = time.monotonic() + timeout
        while True:
            message = self.messages.get(timeout=max(0, deadline - time.monotonic()))
            if not isinstance(message, dict):
                raise RuntimeError("Runtime connection closed")
            if "id" in message and "method" in message:
                # Never approve a capability escalation, external tool or input request.
                self.send({"id": message["id"], "error": {
                    "code": -32601, "message": "Read-only Companion denies this request"}})
                continue
            return message

    def call(self, method, params):
        self.sequence += 1
        ident = self.sequence
        self.send({"id": ident, "method": method, "params": params})
        deadline = time.monotonic() + 30
        while True:
            message = self.receive(max(0, deadline - time.monotonic()))
            if message.get("id") == ident:
                if "error" in message:
                    raise RuntimeError("Runtime request failed")
                return message["result"]
            self.saved.append(message)

    def notification(self, timeout):
        return self.saved.pop(0) if self.saved else self.receive(timeout)


def _redact(text, token):
    text = text.replace(token, "[credential redacted]")
    return re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
                  "[credential redacted]", text)


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
        token = self._credential()
        if not token or token.startswith("sk-"):
            raise PermissionError("ChatGPT-plan credential required")
        env = {k: v for k, v in os.environ.items() if k.upper() in {
            "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "USERPROFILE",
            "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "PROGRAMFILES",
            "PROGRAMFILES(X86)", "PROGRAMDATA"}}
        # A fresh home avoids inherited provider, plugin and MCP configuration.
        with tempfile.TemporaryDirectory(prefix="companion-codex-") as state:
            if Path(state).resolve().is_relative_to(Path(request.workspace).resolve()):
                raise PermissionError("Runtime state must be outside the workspace")
            env.update(CODEX_HOME=state, ACCESS_TOKEN=token, RUST_LOG="off")
            command = [self.executable, "app-server", "--listen", "stdio://"]
            for setting in SETTINGS:
                command.extend(["-c", setting])
            process = subprocess.Popen(command, cwd=state, env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", creationflags=(subprocess.CREATE_NO_WINDOW
                    if os.name == "nt" else 0))
            rpc = _Rpc(process)
            try:
                yield from self._execute(rpc, request, token)
            finally:
                process.stdin.close()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
                    else:
                        process.kill()
                    process.wait(timeout=5)
                process.stdout.close()

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
            raise PermissionError("Read-only policy was not confirmed")
        session = started.get("thread", {}).get("id")
        if not isinstance(session, str) or not session:
            raise RuntimeError("Missing runtime session")
        yield RuntimeEvent(EventKind.SESSION, session_id=session)
        turn = rpc.call("turn/start", {"threadId": session, "cwd": request.workspace,
            "approvalPolicy": "never", "sandboxPolicy": dict(POLICY),
            "input": [{"type": "text", "text": request.intent}]})["turn"]["id"]
        deadline = time.monotonic() + self.timeout
        answer = ""
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError("Execution deadline exceeded")
            message = rpc.notification(max(0, deadline - time.monotonic()))
            params = message.get("params", {})
            if params.get("threadId") != session:
                continue
            method = message.get("method")
            if method == "turn/completed":
                terminal = params.get("turn", {})
                if terminal.get("id") != turn:
                    continue
                status = terminal.get("status")
                kind = {"completed": EventKind.COMPLETED, "interrupted": EventKind.CANCELLED}.get(
                    status, EventKind.FAILED)
                yield RuntimeEvent(kind, text=_redact(answer, token) if kind == EventKind.COMPLETED else None)
                return
            if params.get("turnId") != turn:
                continue
            if method == "item/agentMessage/delta":
                # Progress only: never leak a token split across streaming chunks.
                yield RuntimeEvent(EventKind.RECEIVING)
            elif method == "item/started" and params.get("item", {}).get("type") == "commandExecution":
                yield RuntimeEvent(EventKind.INSPECTING)
            elif method == "item/completed" and params.get("item", {}).get("type") == "agentMessage":
                answer = params["item"].get("text", "")

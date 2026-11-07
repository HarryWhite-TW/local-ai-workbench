"""Native Codex diagnosis transport; uses the installed account, never SIWC tokens.

Protocol/config reference: openai/codex rust-v0.162.1 app-server-protocol/schema.
Only explicitly supplied source snapshots are analysed. No shell or external
tools are exposed; unsupported policy/protocol fails closed. Native-host proof
is required before claiming real execution support.
"""
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

from .codex import _Rpc
from .domain import Failure
from .native_codex import find_codex, normalized
from .runtime import RuntimeFailure

DISABLED = (
    "shell_tool", "unified_exec", "apply_patch_freeform", "js_repl", "code_mode",
    "apps", "connectors", "plugins", "multi_agent", "multi_agent_v2",
    "collab", "enable_fanout", "hooks", "codex_hooks", "plugin_hooks",
    "computer_use", "browser_use", "image_generation", "imagegenext",
    "web_search", "web_search_request", "web_search_cached", "standalone_web_search",
    "shell_snapshot", "memories", "memory_tool", "remote_control",
    "skill_search", "tool_search", "search_tool", "goals", "deferred_executor",
    "in_app_local_automation", "daemon_auto_start", "workspace_dependencies",
    "code_mode_host", "code_mode_only", "code_mode_tool_search", "code_mode_prewarm",
    "experimental_use_unified_exec_tool", "stable_environment_tools",
)
SETTINGS = (
    'model_provider="openai"', 'sandbox_mode="read-only"', 'approval_policy="never"',
    'windows.sandbox="unelevated"', 'mcp_servers={}', 'notify=[]',
    'web_search="disabled"', 'apps._default.enabled=false',
    'skills.bundled.enabled=false', 'skills.include_instructions=false',
    'project_doc_max_bytes=0', 'analytics.enabled=false',
    'otel.log_user_prompt=false', 'check_for_update_on_startup=false',
    'features.skip_host_skill_discovery=true',
) + tuple("features." + name + "=false" for name in DISABLED)
ALLOWED = {"config/read", "account/read", "thread/start", "thread/resume", "thread/read",
           "thread/turns/list", "turn/start", "turn/interrupt"}


def policy(workspace):
    # Codex 0.162.1 declares only these readOnly policy fields. Source scope
    # is the host-captured snapshot; this RPC does not encode read-root ACLs.
    # Keep the argument for existing callers and keep all tool gates disabled.
    return {"type": "readOnly", "networkAccess": False}


class RpcRejected(RuntimeError):
    """A correlated JSON-RPC error, never a raw provider error body."""
    def __init__(self, method, code, kind="request_rejected"):
        self.method, self.code, self.kind = method, code, kind
        self.definitely_not_started = code in (-32600, -32601, -32602) or kind == "windows_read_restriction_unsupported"
        super().__init__("Native RPC rejected: " + method + " (" + str(code) + ")")

    @classmethod
    def from_error(cls, method, error):
        if (not isinstance(error, dict) or type(error.get("code")) is not int
                or not isinstance(error.get("message"), str)):
            raise RuntimeFailure(Failure.PROTOCOL)
        code = error["code"]
        message = error["message"][:4096].lower()
        kind = {-32600: "invalid_request", -32601: "method_unavailable",
                -32602: "invalid_parameters"}.get(code, "request_rejected")
        if ("windows unelevated restricted-token sandbox cannot enforce" in message
                and ("read restrictions" in message or "deny-read" in message)):
            kind = "windows_read_restriction_unsupported"
        # Discard message/data; only this finite category and numeric code survive.
        return cls(method, code, kind)


class NativeClient(_Rpc):
    """One owned stdio process; existing RPC denial and correlation semantics."""
    def __init__(self, directory, executable=None, *, settings=()):
        self.directory = directory
        self.executable = executable or find_codex()
        self.settings = tuple(settings)
        self.process = None

    def __enter__(self):
        if not self.executable or not Path(self.executable).is_file() or Path(self.executable).suffix.lower() != ".exe":
            raise RuntimeFailure(Failure.AUTHENTICATION)
        command = [str(self.executable), "app-server", "--listen", "stdio://"]
        for setting in SETTINGS + self.settings:
            command += ["-c", setting]
        # No credential callback, copied auth file, alternate CODEX_HOME or
        # API-key environment. Native Codex owns its normal login store.
        env = {k: v for k, v in os.environ.items() if k.upper() in {
            "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "USERPROFILE",
            "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "PROGRAMFILES",
            "PROGRAMFILES(X86)", "PROGRAMDATA"}}
        self.process = subprocess.Popen(command, cwd=self.directory, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.messages, self.saved, self.sequence = queue.Queue(maxsize=128), [], 0
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        try:
            self.call("initialize", {"clientInfo": {"name": "nexus_readonly_diagnosis", "version": "0.1.0"}})
            self.send({"method": "initialized", "params": {}})
            account = self.call("account/read", {"refreshToken": False}).get("account")
            if not isinstance(account, dict) or account.get("type") != "chatgpt":
                raise RuntimeFailure(Failure.AUTHENTICATION)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def _read(self):
        try:
            while True:
                line = self.process.stdout.readline(2_097_153)
                if not line or len(line) > 2_097_152:
                    break
                self.messages.put_nowait(json.loads(line))
        except (OSError, ValueError, queue.Full):
            pass
        finally:
            try:
                self.messages.put_nowait(None)
            except queue.Full:
                pass


    def call(self, method, params):
        ident = self.begin(method, params)
        deadline = time.monotonic() + 30
        while True:
            message = self.receive(max(0, deadline - time.monotonic()))
            if message.get("id") == ident:
                if "error" in message:
                    raise RpcRejected.from_error(method, message["error"])
                if not isinstance(message.get("result"), dict):
                    raise RuntimeFailure(Failure.PROTOCOL)
                return message["result"]
            self.saved.append(message)
            if len(self.saved) > 128:
                raise RuntimeFailure(Failure.PROTOCOL)

    def begin(self, method, params):
        if method not in ALLOWED and method != "initialize":
            raise RuntimeFailure(Failure.POLICY)
        return super().begin(method, params)

    def __exit__(self, *args):
        # Closing an owned host is cleanup, never proof of turn cancellation.
        if self.process is None:
            return
        try:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=3)
        finally:
            self.reader.join(timeout=1)
            if not self.reader.is_alive():
                self.process.stdout.close()


def check_thread(reply, workspace, expected=None, execution=False):
    thread = reply.get("thread", {})
    ident = thread.get("id")
    if (not isinstance(ident, str) or not ident or len(ident) > 100
            or (expected is not None and ident != expected)
            or normalized(thread.get("cwd", "")) != normalized(workspace)):
        raise RuntimeFailure(Failure.PROTOCOL)
    if execution:
        sandbox = reply.get("sandbox", {})
        if (reply.get("approvalPolicy") != "never" or sandbox.get("type") != "readOnly"
                or sandbox.get("networkAccess", False) is not False):
            raise RuntimeFailure(Failure.POLICY)
    return ident


def answer_from(items):
    if not isinstance(items, list):
        raise RuntimeFailure(Failure.PROTOCOL)
    # Never persist reasoning, tool arguments, command output or provider errors.
    if any(i.get("type") not in ("userMessage", "agentMessage", "reasoning", "plan")
           for i in items if isinstance(i, dict)):
        raise RuntimeFailure(Failure.POLICY)
    parts = [i["text"] for i in items if isinstance(i, dict)
             and i.get("type") == "agentMessage" and i.get("phase") != "commentary"
             and isinstance(i.get("text"), str)]
    result = "\n\n".join(parts)
    if len(result) > 40_000:
        raise RuntimeFailure(Failure.PROTOCOL)
    return result


def observe_turn(rpc, thread_id, turn_id, cancel, mark, timeout=180):
    deadline, interrupted, messages = time.monotonic() + timeout, False, {}
    while time.monotonic() < deadline:
        try:
            message = rpc.notification(.1)
        except RuntimeFailure as exc:
            if exc.reason != Failure.TIMEOUT:
                raise
            message = {}
        params = message.get("params", {})
        method = message.get("method")
        if params.get("threadId") == thread_id:
            if method == "turn/completed":
                terminal = params.get("turn", {})
                if terminal.get("id") == turn_id:
                    status = terminal.get("status")
                    if status not in ("completed", "failed", "interrupted"):
                        raise RuntimeFailure(Failure.PROTOCOL)
                    if status == "completed":
                        result = answer_from(list(messages.values()))
                        if not result.strip():
                            raise RuntimeFailure(Failure.PROTOCOL)
                        return "COMPLETED", result
                    return ("CANCELLED" if status == "interrupted" else "FAILED"), None
            if params.get("turnId") == turn_id:
                if method in ("item/started", "item/completed"):
                    item = params.get("item", {})
                    answer_from([item])  # Reject unexpected tool activity.
                    if method == "item/completed" and item.get("type") == "agentMessage":
                        ident = item.get("id")
                        if not isinstance(ident, str) or len(messages) >= 32:
                            raise RuntimeFailure(Failure.PROTOCOL)
                        messages[ident] = item
                        mark(event="receiving_result")
                elif method == "item/agentMessage/delta":
                    mark(event="receiving_result")
        # Read queued terminal evidence before sending a cancellation request.
        if cancel.is_set() and not interrupted:
            rpc.begin("turn/interrupt", {"threadId": thread_id, "turnId": turn_id})
            interrupted = True
            mark(state="CANCEL_REQUESTED", event="cancel_requested")
    raise RuntimeFailure(Failure.CANCELLATION if interrupted else Failure.TIMEOUT)


def read_turn(rpc, workspace, thread_id, turn_id):
    check_thread(rpc.call("thread/read", {"threadId": thread_id}), workspace, thread_id)
    if not turn_id:
        # A lost turn/start reply is not permission to guess a turn or retry.
        raise RuntimeFailure(Failure.CONNECTION)
    page = rpc.call("thread/turns/list", {"threadId": thread_id, "limit": 5,
                                        "sortDirection": "desc", "itemsView": "full"})
    turns = [t for t in page.get("data", []) if t.get("id") == turn_id]
    if len(turns) != 1:
        raise RuntimeFailure(Failure.CONNECTION)
    turn = turns[0]
    state = {"completed": "COMPLETED", "failed": "FAILED",
             "interrupted": "CANCELLED"}.get(turn.get("status"), "UNKNOWN")
    result = answer_from(turn.get("items", [])) if state == "COMPLETED" else None
    if state == "COMPLETED" and not result.strip():
        raise RuntimeFailure(Failure.PROTOCOL)
    return state, result

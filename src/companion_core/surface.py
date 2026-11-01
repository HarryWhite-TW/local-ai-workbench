"""Shared foreground loopback surface; daily entry is src.companion_core.daily.

This module's main is the separate trusted-host Codex adapter entry (--help).
daily.py supplies SIWC/chat/work/history; this module does not choose that backend.
No arbitrary workspace picker, execution queue or publication action.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
from urllib.parse import parse_qs, urlsplit

from .codex import CodexRuntime
from .core import Companion
from .domain import Authority, Execution
from .presentation import FAILURES, HumanView, safe_text
from .review import ReviewError, ReviewStore


# Display-only allowlist. Runtime bodies, tool arguments and reasoning never enter
# this projection. A runtime terminal report is provisional until Core finishes.
OBSERVATIONS = {
    "task_created": ("工作已建立", "Core 已建立唯讀工作。"),
    "working": ("執行已開始", "Core 已開始執行；完成比例未提供。"),
    "session_bound": ("執行連線已建立", "執行端已回報連線身分；不公開原始連線資料。"),
    "inspecting_repository": ("檢視階段已回報", "有檢視操作回報；工具名稱、命令、輸出與完成狀態未提供。"),
    "receiving_result": ("正在接收結果", "有結果接收回報；部分文字未公開，尚未確認完整成果。"),
    "execution_complete": ("結果已回報，收尾未確認", "執行端已回報結果；以 Core 收尾後的狀態為準。"),
    "execution_failed": ("失敗已回報", "執行端回報失敗；原始錯誤內容不公開。"),
    "execution_cancelled": ("取消已回報，收尾未確認", "取消回報仍需 Core 完成收尾。"),
    "pending_review": ("執行完成已確認", "Core 已取得結果；保存與人類審查仍是不同狀態。"),
    "failed": ("執行失敗已確認", "Core 確認失敗；安全原因見目前狀態說明。"),
    "cancelled": ("取消已確認", "Core 確認取消；沒有可審查成果。"),
}


class Surface:
    """One live Core reference and a disposable progress projection, not a store."""

    def __init__(self, runtime, workspace, store):
        self.workspace = str(Path(workspace).resolve())
        if not Path(self.workspace).is_dir():
            raise ValueError("Workspace unavailable")
        self.runtime, self.store = runtime, store
        self.active = None
        self.worker = None
        self.lines = []
        self.events = []
        self.event_sequence = 0
        self.notice = ""
        self.lock = threading.Lock()

    def _progress(self, text):
        with self.lock:
            self.lines.append(text)

    def _event(self, core, stage):
        if stage not in OBSERVATIONS:
            return
        title, detail = OBSERVATIONS[stage]
        with self.lock:
            if self.active is not core:
                return
            self.event_sequence += 1
            self.events.append({"task_id": core.task.id, "sequence": self.event_sequence,
                "kind": stage, "title": title, "detail": detail,
                "confirmation": "confirmed" if stage in
                    ("working", "pending_review", "failed", "cancelled")
                    else "reported"})
            self.events = self.events[-128:]

    def _observe(self, core, view, event):
        # Progress comes from Core, not arbitrary provider payloads.
        if event.task_id == core.task.id:
            self._event(core, event.stage)
            view.progress(event)

    def start(self, intent, *, bind=None, finished=None):
        if not isinstance(intent, str) or not intent.strip() or len(intent) > 4000 or safe_text(intent) != intent:
            raise ReviewError()
        with self.lock:
            if self.worker and self.worker.is_alive():
                raise ReviewError()
            core = Companion(self.runtime, intent.strip(), self.workspace, Authority.READ_ONLY)
            if bind:
                bind(core.task.id)
            self.active, self.lines, self.notice = core, [], ""
            self.events, self.event_sequence = [], 0
            view = HumanView(self._progress)
            self.worker = threading.Thread(target=self._execute, args=(core, view, finished), daemon=False)
            self.worker.start()
            return {"task_id": core.task.id}

    def _execute(self, core, view, finished=None):
        task = core.run(lambda event: self._observe(core, view, event))
        if task.state == "RESULT_PENDING_REVIEW":
            try:
                self.store.publish(task)
            except Exception:
                # Keep the valid Core result; a persistence error isn't acceptance.
                with self.lock:
                    self.notice = "執行已有結果，但未能安全保存待審記錄；請勿視為審查成功。"
        if finished:
            finished(task)

    def cancel(self, body):
        if (not isinstance(body, dict) or set(body) != {"task_id"}
                or not isinstance(body["task_id"], str)):
            raise ReviewError()
        with self.lock:
            if (not self.active or body["task_id"] != self.active.task.id
                    or not self._visible(self.active.task)
                    or self.active.task.execution not in
                    (Execution.RUNNING, Execution.CANCEL_REQUESTED)):
                raise ReviewError()
            return self._summary(self.active.cancel())

    def _visible(self, task):
        return (Path(task.workspace).resolve() == Path(self.workspace)
                and (not hasattr(self.runtime, 'can_view') or self.runtime.can_view(task)))

    def _scoped(self, target):
        if not self._visible(target.task):
            raise ReviewError()
        return target

    @staticmethod
    def _summary(task):
        return {"task_id": task.id, "intent": safe_text(task.intent), "state": task.state}

    def target(self, task_id):
        target = self._scoped(self.store.get(task_id))
        data = self._summary(target.task)
        data.update(result_id=target.result_id, result=safe_text(target.task.result),
                    authority=target.task.authority.value, provider=safe_text(target.task.provider))
        data["revision"] = (self._summary(target.revision) if target.revision else None)
        return data

    def decide(self, body):
        if (not isinstance(body, dict) or set(body) != {"task_id", "result_id", "action", "revision_intent"}
                or not all(isinstance(body[k], str) for k in ("task_id", "result_id", "action"))):
            raise ReviewError()
        self._scoped(self.store.get(body["task_id"]))
        self.store.decide(body["task_id"], body["result_id"], body["action"],
                          reviewer="local-human", revision_intent=body["revision_intent"])
        return self.target(body["task_id"])

    def snapshot(self):
        targets = [t for t in self.store.targets() if self._visible(t.task)]
        summaries = [self._summary(t.task) for t in targets]
        if hasattr(self.runtime, 'saved_failures'):
            summaries += [s for s in self.runtime.saved_failures()
                          if s['task_id'] not in {t['task_id'] for t in summaries}
                          and (not self.active or s['task_id'] != self.active.task.id)]
        with self.lock:
            task = self.active.task if self.active and self._visible(self.active.task) else None
            active = self._summary(task) if task else None
            if active:
                saved = next((t for t in targets if t.task.id == task.id), None)
                if saved:
                    active = self._summary(saved.task)
            failure = FAILURES.get(task.failure, "") if task and task.execution == Execution.FAILED else ""
            return {"workspace": self.workspace, "authority": "READ_ONLY",
                    "runtime": safe_text(self.runtime.provider_id), "active": active,
                    "busy": bool(self.worker and self.worker.is_alive()), "progress": list(self.lines) if task else [],
                    "observation": {"task_id": task.id if task else None,
                        "events": [dict(event) for event in self.events] if task else [],
                        "omitted": max(0, self.event_sequence - len(self.events)) if task else 0,
                        "tool_details": "not_provided", "durable": False},
                    "notice": (self.notice or failure) if task else "", "tasks": summaries}


def make_server(surface, chat=None, work=None, *, port=0, native_codex=None):
    assets = Path(__file__).with_name("static")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log intents, identities, request bodies or provider errors.

        def _reply(self, code, data, mime="application/json; charset=utf-8"):
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass  # A browser disconnect does not touch Core or ReviewStore.

        def _allowed(self, mutation=False):
            host = f"127.0.0.1:{self.server.server_port}"
            origin = "http://" + host
            return (self.client_address[0] == "127.0.0.1" and self.headers.get("Host") == host
                    and self.headers.get("Sec-Fetch-Site", "same-origin") in ("same-origin", "none")
                    and (not mutation or (self.headers.get("Origin") == origin
                         and self.headers.get("X-Companion-UI") == "1"
                         and self.headers.get("Content-Type") == "application/json"
                         and not self.headers.get("Transfer-Encoding"))))

        def do_GET(self):
            if chat is not None and urlsplit(self.path).path == "/auth/callback":
                host = f"127.0.0.1:{self.server.server_port}"
                if self.client_address[0] != "127.0.0.1" or self.headers.get("Host") != host:
                    self._reply(403, {"error": "登入回應來源不符。"})
                    return
                try:
                    if len(self.path) > 16384:
                        raise ValueError()
                    query = parse_qs(urlsplit(self.path).query, keep_blank_values=True, max_num_fields=12)
                    if any(len(v) != 1 for v in query.values()):
                        raise ValueError()
                    chat.auth.callback({k: v[0] for k, v in query.items()})
                    with chat.lock:
                        chat.resources.handoff = None
                    self._reply(200, "登入已完成。請關閉此頁，回到 Companion。".encode("utf-8"), "text/plain; charset=utf-8")
                except Exception:
                    self._reply(400, "登入未完成。請回到 Companion 查看狀態或重新登入。".encode("utf-8"), "text/plain; charset=utf-8")
                return
            if not self._allowed():
                self._reply(403, {"error": "此介面僅供本機同來源使用。"})
                return
            try:
                if self.path == "/api/state":
                    self._reply(200, surface.snapshot())
                elif self.path == "/api/chat/state" and chat is not None:
                    # Keep SIWC callbacks/account selection outside serialization
                    # and emission too, not just outside the database read.
                    with chat.lock, getattr(chat.auth, 'lock', chat.lock):
                        self._reply(200, chat.snapshot())
                elif self.path in ("/", "/surface.js", "/surface.css", "/chat.js", "/chat.css",
                                   "/reading.js", "/nexus.js", "/nexus.css", "/native-codex.js", "/native-codex.css"):
                    name = "index.html" if self.path == "/" else self.path[1:]
                    mime = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}[Path(name).suffix]
                    content = (assets / name).read_bytes()
                    if name == "index.html" and chat is not None:
                        content = content.replace(b'data-chat-enabled="false"', b'data-chat-enabled="true"', 1)
                    if name == "index.html" and work is not None:
                        content = content.replace(b'data-work-enabled="false"', b'data-work-enabled="true"', 1)
                    if name == "index.html" and native_codex is not None:
                        content = content.replace(b'data-native-codex="false"', b'data-native-codex="true"', 1)
                    self._reply(200, content, mime + "; charset=utf-8")
                else:
                    self._reply(404, {"error": "找不到此畫面。"})
            except Exception:
                self._reply(409, {"error": "記錄目前不可確認；未推定接受或取消。"})

        def do_POST(self):
            if not self._allowed(mutation=True):
                self._reply(403, {"error": "此操作需要本機同來源的明確要求。"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                limit = 1_100_000 if self.path == '/api/chat/continuity-save' else 32768
                if not 0 < length <= limit:
                    raise ReviewError()
                def unique_fields(pairs):
                    data = {}
                    for key, value in pairs:
                        if key in data:
                            raise ReviewError()
                        data[key] = value
                    return data
                body = json.loads(self.rfile.read(length),
                    object_pairs_hook=unique_fields if self.path == "/api/cancel" or self.path.startswith("/api/chat/") else None)
                if self.path.startswith("/api/chat/") and chat is not None:
                    from .siwc import ChatError
                    from .chat import sources
                    try:
                        if not isinstance(body, dict):
                            raise ChatError("操作格式不正確。")
                        action = self.path.removeprefix("/api/chat/")
                        if action.startswith('codex-') and native_codex is not None:
                            native_codex.respond(action.removeprefix('codex-'), body,
                                                 lambda data: self._reply(200, data))
                            return
                        elif action in ("login", "logout", "select"):
                            result = chat.auth_action(action, body, f"http://127.0.0.1:{self.server.server_port}")
                        elif action == "models" and not body:
                            result = chat.catalog()
                        elif action in ('continuity-get', 'continuity-save'):
                            with chat.lock, getattr(chat.auth, 'lock', chat.lock):
                                operation = chat.continuity.get if action == 'continuity-get' else chat.continuity.save
                                self._reply(200, operation(body))
                            return
                        elif action == "get" and set(body) == {"chat"}:
                            with chat.lock, getattr(chat.auth, 'lock', chat.lock):
                                self._reply(200, chat.get(body["chat"]))
                            return
                        elif action == 'project-context' and not body and work is not None:
                            with chat.lock:
                                result = chat.project_context()
                                result['work'] = surface.snapshot()
                                if chat.auth.pending or result['account'] != chat.auth.vault.data['active']:
                                    raise ChatError('目前帳戶已變更，請重新讀取專案。')
                        elif action == 'project-get' and set(body) == {'chat'}:
                            result = chat.project_link(body['chat'])
                        elif action == 'project-preview':
                            result = chat.preview_project_link(body)
                        elif action == 'project-confirm':
                            result = chat.confirm_project_link(body)
                        elif action.startswith('resource-'):
                            operations = {'resource-documents': chat.resources.documents,
                                'resource-preview': chat.resources.preview, 'resource-links': chat.resources.links,
                                'resource-link-preview': chat.resources.preview_link,
                                'resource-link-confirm': chat.resources.confirm_link,
                                'resource-link-open': chat.resources.open_link,
                                'resource-source-preview': chat.resources.preview_source,
                                'resource-source-cancel': chat.resources.discard_source}
                            if action not in operations:
                                raise ChatError('找不到指定資源操作。')
                            with chat.lock, getattr(chat.auth, 'lock', chat.lock):
                                self._reply(200, operations[action](body))
                            return
                        elif action == "preview" and set(body) == {"sources"}:
                            result = sources(chat.workspace, body["sources"])
                        elif action == "preview" and set(body) == {"sources", "chat"}:
                            result = chat.selected_sources(body['sources'], body['chat'])
                        elif action.startswith('work-') and work is not None:
                            if action == 'work-state' and set(body) == {'chat'}:
                                result = work.state(body['chat'])
                            elif action == 'work-origin' and set(body) == {'task_id'}:
                                result = work.origin(body['task_id'])
                            elif action == 'work-create':
                                result = work.create(body)
                            elif action == 'work-preview':
                                result = work.preview(body)
                            elif action == 'work-confirm':
                                result = work.confirm(body)
                            else:
                                raise ChatError('工作操作格式不正確。')
                        elif action == "send":
                            result = chat.submit(body)
                        else:
                            raise ChatError("找不到指定對話操作。")
                        self._reply(200, result)
                    except ChatError as exc:
                        self._reply(409, {"error": str(exc)})
                    return
                if self.path == "/api/start" and isinstance(body, dict) and set(body) == {"intent"}:
                    if getattr(surface.runtime, 'requires_proposal', False):
                        raise ReviewError()
                    result = surface.start(body["intent"])
                elif self.path == "/api/target" and isinstance(body, dict) and set(body) == {"task_id"}:
                    result = surface.target(body["task_id"])
                elif self.path == "/api/review":
                    result = surface.decide(body)
                elif self.path == "/api/cancel":
                    result = surface.cancel(body)
                else:
                    raise ReviewError()
                self._reply(200, result)
            except Exception:
                self._reply(409, {"error": "操作未確認成功：請重新讀取指定工作，不會自動重試或選擇其他結果。"})

        def do_OPTIONS(self):
            self._reply(403, {"error": "不提供跨來源存取。"})

    class Server(ThreadingHTTPServer):
        # A fixed preview port must fail if another process already owns it.
        allow_reuse_address = False

        def handle_error(self, request, client_address):
            pass  # No raw exception or request diagnostics on the human surface.

    return Server(("127.0.0.1", port), Handler)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--review-dir")
    args = parser.parse_args()
    if sys.stdin.isatty():
        print("請從既有可信任登入端開啟 Companion；不要輸入或貼上憑證。")
        return 1
    token = sys.stdin.readline().strip()
    if not token or token.startswith("sk-"):
        print("登入授權不可用。")
        return 1
    try:
        store = ReviewStore(args.review_dir, workspace=args.workspace)
        surface = Surface(CodexRuntime(args.codex, args.model, lambda: token), args.workspace, store)
        server = make_server(surface)
    except Exception:
        print("本機介面無法安全啟動。")
        return 1
    print(f"Companion: http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if surface.worker:
            surface.worker.join()  # Closing the host waits; it does not claim cancellation.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

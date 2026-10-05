"""Foreground, single-user loopback UI. The trusted host supplies runtime/login.

Run via the existing OAuth host: python -m src.companion_core.surface --help.
This is separate from the document workbench Web app. No credential HTTP API,
workspace picker, execution queue, running cancellation or publication action.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading

from .codex import CodexRuntime
from .core import Companion
from .domain import Authority, Execution
from .presentation import FAILURES, HumanView, safe_text
from .review import ReviewError, ReviewStore


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
        self.notice = ""
        self.lock = threading.Lock()

    def _progress(self, text):
        with self.lock:
            self.lines.append(text)

    def start(self, intent):
        if not isinstance(intent, str) or not intent.strip() or len(intent) > 4000 or safe_text(intent) != intent:+            raise ReviewError()
        with self.lock:
            if self.worker and self.worker.is_alive():
                raise ReviewError()
            core = Companion(self.runtime, intent.strip(), self.workspace, Authority.READ_ONLY)
            self.active, self.lines, self.notice = core, [], ""
            view = HumanView(self._progress)
            self.worker = threading.Thread(target=self._execute, args=(core, view), daemon=False)
            self.worker.start()
            return {"task_id": core.task.id}

    def _execute(self, core, view):
        task = core.run(view.progress)
        if task.state == "RESULT_PENDING_REVIEW":
            try:
                self.store.publish(task)
            except Exception:
                # Keep the valid Core result; a persistence error isn't acceptance.
                with self.lock:
                    self.notice = "執行已有結果，但未能安全保存待審記錄；請勿視為審查成功。"

    def _scoped(self, target):
        if Path(target.task.workspace).resolve() != Path(self.workspace):
            raise ReviewError()
        return target

    @staticmethod
    def _summary(task):
        return {"task_id": task.id, "intent": safe_text(task.intent), "state": task.state}

    def target(self, task_id):
        target = self._scoped(self.store.get(task_id))
        data = self._summary(target.task)
        data.update(result_id=target.result_id, result=safe_text(target.task.result),
                    authority=target.task.authority.value)
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
        targets = [t for t in self.store.targets() if Path(t.task.workspace).resolve() == Path(self.workspace)]
        with self.lock:
            task = self.active.task if self.active else None
            active = self._summary(task) if task else None
            if active:
                saved = next((t for t in targets if t.task.id == task.id), None)
                if saved:
                    active = self._summary(saved.task)
            failure = FAILURES.get(task.failure, "") if task and task.execution == Execution.FAILED else ""
            return {"workspace": self.workspace, "authority": "READ_ONLY", "active": active,
                    "busy": bool(self.worker and self.worker.is_alive()), "progress": list(self.lines),
                    "notice": self.notice or failure, "tasks": [self._summary(t.task) for t in targets]}


def make_server(surface):
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
            if not self._allowed():
                self._reply(403, {"error": "此介面僅供本機同來源使用。"})
                return
            try:
                if self.path == "/api/state":
                    self._reply(200, surface.snapshot())
                elif self.path in ("/", "/surface.js", "/surface.css"):
                    name = "index.html" if self.path == "/" else self.path[1:]
                    mime = {"index.html": "text/html", "surface.js": "text/javascript", "surface.css": "text/css"}[name]
                    self._reply(200, (assets / name).read_bytes(), mime + "; charset=utf-8")
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
                if not 0 < length <= 32768:
                    raise ReviewError()
                body = json.loads(self.rfile.read(length))
                if self.path == "/api/start" and isinstance(body, dict) and set(body) == {"intent"}:
                    result = surface.start(body["intent"])
                elif self.path == "/api/target" and isinstance(body, dict) and set(body) == {"task_id"}:
                    result = surface.target(body["task_id"])
                elif self.path == "/api/review":
                    result = surface.decide(body)
                else:
                    raise ReviewError()
                self._reply(200, result)
            except Exception:
                self._reply(409, {"error": "操作未確認成功：請重新讀取指定工作，不會自動重試或選擇其他結果。"})

        def do_OPTIONS(self):
            self._reply(403, {"error": "不提供跨來源存取。"})

    class Server(ThreadingHTTPServer):
        def handle_error(self, request, client_address):
            pass  # No raw exception or request diagnostics on the human surface.

    return Server(("127.0.0.1", 0), Handler)


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

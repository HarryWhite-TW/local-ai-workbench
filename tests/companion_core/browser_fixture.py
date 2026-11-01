"""Isolated synthetic browser fixture; no AI, credentials or production state.

Controlled through parent stdin only. Uses the real Surface/Core/ReviewStore.
"""
import argparse
import json
from pathlib import Path
import sys
import threading
import time
import webbrowser
import os
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.companion_core.review import ReviewStore
from src.companion_core.runtime import EventKind, RuntimeEvent
from src.companion_core.surface import Surface, make_server


class SyntheticRuntime:
    provider_id = "synthetic-no-ai"

    def __init__(self, interactive=False):
        self.interactive = interactive
        self.release = threading.Event()
        self.cancel_release = threading.Event()
        self.requests = 0
        self.outcome = "complete"

    def run(self, request):
        self.requests += 1
        yield RuntimeEvent(EventKind.SESSION, session_id=f"synthetic-{self.requests}")
        yield RuntimeEvent(EventKind.INSPECTING)
        started = time.monotonic()
        while not self.release.wait(.02):
            if self.interactive and time.monotonic() - started >= 18:
                break
            if request.cancel_requested.is_set():
                self.cancel_release.wait(3 if self.interactive else 15)
                yield RuntimeEvent(EventKind.FAILED if self.outcome == "failed" else EventKind.CANCELLED)
                return
        if self.outcome == "failed":
            yield RuntimeEvent(EventKind.FAILED)
        else:
            yield RuntimeEvent(EventKind.RECEIVING)
            yield RuntimeEvent(EventKind.COMPLETED, text=("模擬驗證結果（非實際 AI 執行）\n\n公開文件結構摘要\n\n這份合成結果用於驗證 Companion 的選取、檢視與審查流程。\n所有事件均來自 synthetic runtime，沒有讀取專案或呼叫 AI。\n\n可確認：工作身分、成果身分與審查記錄。\n尚未確認：實際 AI 任務品質。\n\n接受這份結果只會保存本機審查決定。\n\n" + "\n\n".join(f"閱讀段落 {i}：這是非敏感的合成文件段落，用來檢查長內容閱讀、內部捲動及返回控制。可確認的是本機工作與成果身分，未驗證實際 AI 分析品質。" for i in range(1, 13))))


class ExperienceRuntime(SyntheticRuntime):
    """Timed, explicitly synthetic scenarios; the real Core owns every state."""

    seeding = False

    def run(self, request):
        self.requests += 1
        failed = request.intent.startswith("合成情境｜失敗")
        duration = 12 if request.intent.startswith("合成情境｜執行觀察") else 5
        started = time.monotonic()
        stages = [(0.6, EventKind.SESSION), (2, EventKind.INSPECTING)]
        if not failed:
            stages.append((duration - 1.5, EventKind.RECEIVING))
        stages.append((duration, EventKind.FAILED if failed else EventKind.COMPLETED))
        for at, kind in stages:
            while not self.seeding and not self.release.is_set() and time.monotonic() - started < at:
                if request.cancel_requested.wait(.025):
                    # The requested state remains distinct from the reconciled state.
                    time.sleep(.6)
                    yield RuntimeEvent(EventKind.CANCELLED)
                    return
            if request.cancel_requested.is_set():
                yield RuntimeEvent(EventKind.CANCELLED)
                return
            text = None
            if kind == EventKind.COMPLETED:
                text = "合成展示成果 · 非實際 AI 執行\n\n" + request.intent + "\n\n"
                text += "這份文件只使用公開的虛構展示文字。沒有讀取 Repository、執行命令、呼叫 AI 或取得工具輸出。\n\n"
                text += "可確認：由本機 Core 產生的 Task ID、已保存的 Result ID，以及獨立的人類審查記錄。\n\n"
                text += "\n\n".join(f"{i:02d} — 閱讀筆記\n工作空間的每一次狀態變化，都應能追溯到可信的資料來源。這是用來體驗長篇閱讀、背景工作切換與精確返回的合成內容；不代表實際分析品質，也不代表任何工具已成功執行。" for i in range(1, 25))
            yield RuntimeEvent(kind, session_id=f"synthetic-{self.requests}" if kind == EventKind.SESSION else None, text=text)


def experience_server(surface):
    """Opt-in fixture assets only. Inherit all HTTP guards and mutation routes."""
    server = make_server(surface)
    handler = server.RequestHandlerClass
    assets = Path(__file__).resolve().parents[2] / "src/companion_core/static"
    page = (assets / "index.html").read_text(encoding="utf-8")
    page = page.replace("<title>Companion — Liquid Ceramic</title>", "<title>Companion — Living Workspace · Synthetic</title>")
    page = page.replace('<body data-theme=', '<body data-experience="true" data-theme=', 1)
    scenario = '''<section class="scenario-bar" aria-label="隔離合成情境">
      <div class="scenario-intro"><span class="tiny-label">SYNTHETIC PLAYGROUND</span><strong>讓工作流動起來。</strong><p>選擇情境，觀看真實 Core 如何處理合成事件。沒有實際 AI 或工具執行。</p></div>
      <div class="scenario-actions">
        <button data-scenario="running"><span class="scenario-icon" aria-hidden="true">↗</span><span><strong>觀察執行</strong><small>執行中 → 等待審查</small></span></button>
        <button data-scenario="reading"><span class="scenario-icon" aria-hidden="true">≡</span><span><strong>長篇成果</strong><small>閱讀、切換與返回</small></span></button>
        <button data-scenario="failed"><span class="scenario-icon" aria-hidden="true">!</span><span><strong>失敗情境</strong><small>階段回報 → 確認失敗</small></span></button>
      </div>
      <p id="scenario-message" role="status">所有情境均為 synthetic。既有成果只等待你的審查。</p>
    </section>'''
    page = page.replace('    <section id="stage"', scenario + '\n    <section id="stage"', 1)
    routes = {
        "/": (page.encode("utf-8"), "text/html; charset=utf-8"),
        "/surface.css": ((assets / "surface.css").read_bytes() + b"\n" + (assets / "experience.css").read_bytes(), "text/css; charset=utf-8"),
        "/surface.js": ((assets / "surface.js").read_bytes() + b"\n" + (assets / "experience.js").read_bytes(), "text/javascript; charset=utf-8"),
    }

    class ExperienceHandler(handler):
        def do_GET(self):
            if self.path in routes:
                if not self._allowed():
                    return self._reply(403, {"error": "此介面僅供本機同來源使用。"})
                data, content_type = routes[self.path]
                return self._reply(200, data, content_type)
            return super().do_GET()

    server.RequestHandlerClass = ExperienceHandler
    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--interactive", action="store_true", help="Automatic synthetic executor; no AI")
    parser.add_argument("--experience", action="store_true", help="Isolated Living Workspace exploration; synthetic only")
    args = parser.parse_args()
    root = Path(args.data).resolve()
    workspace = root / "synthetic-workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    runtime = ExperienceRuntime(args.interactive) if args.experience else SyntheticRuntime(args.interactive)
    surface = Surface(runtime, workspace, ReviewStore(root / "reviews", workspace=str(workspace)))
    if args.experience and not surface.store.targets():
        runtime.seeding = True
        for intent in ("合成展示｜公開文件的閱讀筆記", "合成展示｜設計決策與待確認事項"):
            surface.start(intent)
            surface.worker.join(5)
        runtime.seeding = False
    server = experience_server(surface) if args.experience else make_server(surface)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    def emit(value):
        print(json.dumps(value, ensure_ascii=True), flush=True)
    emit({"url": f"http://127.0.0.1:{server.server_port}", "synthetic": True})
    try:
        if args.interactive:
            print("Synthetic execution only. Real Surface/Core/ReviewStore. No OAuth or AI.", flush=True)
            print("Results remain in: " + str(root / "reviews"), flush=True)
            if args.experience:
                # Foreground fixture lifetime, without opening or controlling a browser.
                thread.join()
                return
            url = f"http://127.0.0.1:{server.server_port}"
            chrome = Path(os.environ.get("ProgramFiles", "")) / "Google/Chrome/Application/chrome.exe"
            if chrome.is_file():
                subprocess.Popen([str(chrome), url])
            else:
                webbrowser.open(url)
            input("Press Enter here to close the test Surface.\n")
            return
        for line in sys.stdin:
            command = json.loads(line)
            action = command["action"]
            if action == "stop":
                break
            if action == "prepare":
                runtime.release.clear()
                runtime.cancel_release.clear()
                runtime.outcome = command.get("outcome", "complete")
            elif action == "release":
                runtime.release.set()
            elif action == "cancel-release":
                runtime.cancel_release.set()
            elif action == "inspect":
                emit({"requests": runtime.requests, "snapshot": surface.snapshot()})
                continue
            emit({"ok": True})
    except KeyboardInterrupt:
        pass
    finally:
        runtime.release.set()
        runtime.cancel_release.set()
        if surface.worker:
            surface.worker.join(5)
        server.shutdown()
        server.server_close()
        thread.join(5)


if __name__ == "__main__":
    main()

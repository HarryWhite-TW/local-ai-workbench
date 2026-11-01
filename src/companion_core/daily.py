"""Foreground daily Companion: python -m src.companion_core.daily --workspace PATH.

Uses only its own SIWC credentials. The incumbent engineering launcher and
ReviewStore remain supported; this entrypoint grants no autonomous tool access.
"""
import argparse
import os
from pathlib import Path
import webbrowser

from .chat import Conversations
from .domain import Failure
from .review import ReviewStore
from .runtime import RuntimeFailure
from .siwc import ChatError, SignIn, Vault
from .surface import Surface, make_server
from .work import ProjectWork
from .native_codex import NativeCodex


class WorkNotConnected:
    provider_id = "工作執行端未連接；可查看與審查既有成果"

    def run(self, request):
        raise RuntimeFailure(Failure.AUTHENTICATION)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--data-dir")
    parser.add_argument("--review-dir")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=0,
                        help="Local preview port (0 chooses an available port).")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    directory = args.data_dir or str(Path(os.environ["LOCALAPPDATA"]) / "LocalAIWorkbench" / "Companion" / "daily")
    vault = server = chat = None
    try:
        workspace = Path(args.workspace).resolve(strict=True)
        if not (workspace / "AGENTS.md").is_file():
            raise ChatError("找不到指定的專案根目錄。")
        vault = Vault(directory, workspace)
        auth = SignIn(vault)
        chat = Conversations(workspace, directory, auth)
        work = ProjectWork(chat)
        surface = Surface(work, workspace, ReviewStore(args.review_dir, workspace=str(workspace)))
        chat.work, work.surface = work, surface
        server = make_server(surface, chat, work, port=args.port, native_codex=NativeCodex(chat))
        url = f"http://127.0.0.1:{server.server_port}/"
        print("Companion: " + url, flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(str(exc) if isinstance(exc, ChatError) else "Companion 無法安全啟動；沒有清除既有資料。", flush=True)
        return 1
    finally:
        if server:
            server.server_close()
        if chat and chat.work and chat.work.surface.worker:
            chat.work.surface.worker.join()
        if chat:
            if chat.worker:
                chat.worker.join()
            chat.auth.http.close()
        if vault:
            vault.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

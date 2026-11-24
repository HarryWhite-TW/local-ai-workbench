"""Foreground daily Companion: python -m src.companion_core.daily --workspace PATH.

SIWC conversations and native Codex diagnosis use separate existing logins.
ReviewStore remains supported; this entrypoint grants no autonomous tool access.
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
from .native_work import NativeWork
from .native_codex import NativeCodex
from .organize import DocumentOrganizer


class WorkNotConnected:
    provider_id = "工作執行端未連接；可查看與審查既有成果"

    def run(self, request):
        raise RuntimeFailure(Failure.AUTHENTICATION)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace")
    parser.add_argument("--data-dir")
    parser.add_argument("--pilot-workspace", help="Fixed non-sensitive isolated engineering sample only.")
    parser.add_argument("--real-git-job", action="store_true", help="Engineering for registered isolated local Git projects.")
    parser.add_argument("--controlled-engineering", action="store_true",
                        help="ENG-01: fixed snapshot-only proposal and host-controlled single-file apply.")
    parser.add_argument("--controlled-worktree", help="Explicit isolated ENG-01 target worktree at the fixed MVP HEAD.")
    parser.add_argument("--codex", help="Existing native codex.exe; uses its own ChatGPT login.")
    parser.add_argument("--review-dir")
    parser.add_argument("--codex-subscription-trial", action="store_true",
                        help="Use the fixed Windows synthetic workspace and existing Codex subscription.")
    parser.add_argument("--real-project-intelligence", action="store_true",
                        help="Use the isolated NEXUS project summary index and existing Codex subscription.")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=0,
                        help="Local preview port (0 chooses an available port).")
    args = parser.parse_args()
    if args.codex_subscription_trial and args.real_project_intelligence:
        parser.error("Choose one isolated mode")
    if args.codex_subscription_trial or args.real_project_intelligence:
        if (os.name != "nt" or args.workspace or args.data_dir or args.review_dir or args.codex
                or args.real_git_job or args.pilot_workspace or args.controlled_engineering):
            parser.error("The isolated Codex mode uses its own workspace and state")
    elif not args.workspace:
        parser.error("--workspace is required")
    if bool(args.controlled_worktree) != args.controlled_engineering:
        parser.error("--controlled-engineering and --controlled-worktree must be supplied together")
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    directory = args.data_dir or str(Path(os.environ["LOCALAPPDATA"]) / "LocalAIWorkbench" / "Companion" / "daily")
    vault = server = chat = None
    stage = "確認工作區"
    try:
        agent = None
        if args.codex_subscription_trial or args.real_project_intelligence:
            from .codex_trial import LocalTrialIdentity, OWNER, prepare_trial, seed_receipts
            from .codex_work_agent import CodexWorkAgent
            if args.real_project_intelligence:
                from .project_knowledge import OWNER, ProjectKnowledge, prepare_project
                workspace, directory = prepare_project()
            else:
                workspace, directory = prepare_trial()
            args.review_dir = str(directory / "reviews")
            agent = CodexWorkAgent(directory / "agent-audit.jsonl")
        else:
            workspace = Path(args.workspace).resolve(strict=True)
        if args.real_git_job:
            isolated = workspace.parent / 'real-git-job'
            if (args.pilot_workspace or args.controlled_engineering or not args.data_dir or not args.review_dir
                    or isolated.resolve(strict=True) != isolated
                    or Path(args.data_dir).resolve() != isolated / 'state'
                    or Path(args.review_dir).resolve() != isolated / 'reviews'):
                raise ChatError('Git 工程只接受指定的隔離狀態及審查目錄。')
        if not (workspace / "AGENTS.md").is_file():
            raise ChatError("找不到指定的專案根目錄。")
        stage = "開啟隔離登入儲存"
        if agent:
            vault = Vault(directory, workspace, local_owner=OWNER)
            notice = ("本機資料限定於 NEXUS 專案摘要。只有核准分享的摘要可被模型查找。"
                      if args.real_project_intelligence else None)
            auth = LocalTrialIdentity(vault, owner=OWNER, notice=notice)
        elif args.controlled_engineering:
            from .controlled_code import ExistingVault, ExistingSignIn
            vault = ExistingVault(directory, workspace)
            auth = ExistingSignIn(vault)
        else:
            vault = Vault(directory, workspace)
            auth = SignIn(vault)
        stage = "初始化隔離對話與工作資料"
        chat = Conversations(workspace, directory, auth, codex_agent=agent)
        if args.real_project_intelligence:
            from .real_git_job import ensure_git_index
            with chat.connect() as db:
                ensure_git_index(db)
            chat.knowledge = ProjectKnowledge(chat)
        elif agent:
            seed_receipts(chat)
        if not (args.pilot_workspace or args.real_git_job or args.controlled_engineering):
            from .web_source import WebSource
            chat.resources.web = WebSource(chat)
            if os.name == "nt":
                from .daily_delegation import DailyDelegation
                from .local_outputs import LocalOutputs, OutputFolder
                folder = OutputFolder(directory / "outputs") if agent else None
                chat.resources.outputs = LocalOutputs(chat, folder)
                chat.delegation = DailyDelegation(chat)
        # Reuse the exact installed runtime that passed the user's N03-01 host run.
        # Never select a different App build merely because its mtime is newer.
        codex = args.codex or str(Path(os.environ.get("APPDATA", "")) /
            "npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe")
        work = NativeWork(chat, executable=codex)
        surface = Surface(work, workspace, ReviewStore(args.review_dir, workspace=str(workspace)))
        chat.work, work.surface = work, surface
        if not agent:
            chat.organizer = DocumentOrganizer(chat, executable=codex)
        if args.pilot_workspace:
            from .engineering_pilot import EngineeringPilot
            chat.engineering_pilot = EngineeringPilot(chat, args.pilot_workspace, codex)
        if args.real_git_job:
            from .real_git_job import RealGitJob
            chat.engineering_pilot = RealGitJob(chat, codex)
        if args.controlled_engineering:
            from .controlled_code import ControlledCode
            chat.controlled_code = ControlledCode(chat, codex, root=args.controlled_worktree)
        stage = "啟動本機 HTTP 服務"
        try:
            server = make_server(surface, chat, work, port=args.port,
                                 native_codex=None if agent else NativeCodex(chat))
        except OSError as exc:
            code = getattr(exc, "winerror", None) or exc.errno
            port = str(args.port) if args.port else "自動選擇"
            hint = ("請清除本次啟動指定的固定連接埠，讓 Windows 選擇可用連接埠。"
                    if args.port else "請檢查 Windows 是否允許本機 loopback 連線。")
            raise ChatError(f"Companion 無法綁定 127.0.0.1（連接埠：{port}，系統錯誤碼：{code}）。{hint}") from None
        url = f"http://127.0.0.1:{server.server_port}/"
        print("Companion: " + url, flush=True)
        if not args.no_browser:
            try:
                opened = webbrowser.open(url)
            except (OSError, webbrowser.Error):
                opened = False
            if not opened:
                print("無法自動開啟瀏覽器；Companion 仍在運作，請在瀏覽器開啟 " + url, flush=True)
        stage = "本機 HTTP 服務運作"
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(str(exc) if isinstance(exc, ChatError) else
              f"Companion 在「{stage}」失敗（{type(exc).__name__}）；請回報此畫面，保留現有資料目錄。", flush=True)
        return 1
    finally:
        if server:
            server.server_close()
        if chat and agent and chat.worker and chat.worker.is_alive() and chat.busy:
            chat.cancel(dict(chat.busy))
        if chat and chat.work and chat.work.surface.worker:
            active = chat.work.surface.active
            if active and active.task.execution.value in ("RUNNING", "CANCEL_REQUESTED"):
                active.cancel()
            chat.work.surface.worker.join()
        if chat:
            if getattr(chat, "controlled_code", None):
                chat.controlled_code.close()
            if getattr(chat, "organizer", None):
                chat.organizer.close()
            if chat.worker:
                chat.worker.join()
            if not agent:
                chat.auth.http.close()
        if vault:
            vault.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

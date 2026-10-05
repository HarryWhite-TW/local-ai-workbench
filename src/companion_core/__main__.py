"""Run: python -m src.companion_core --help.

A trusted OAuth host supplies one validated ChatGPT-plan access token on stdin;
never place credentials in command arguments. Review invocations need no credentials.
"""
import argparse
import sys

from .codex import CodexRuntime
from .core import Companion
from .domain import Authority
from .presentation import HumanView
from .review import ReviewError, ReviewStore, review_interactively, show_review


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", default="run", choices=("run", "pending", "show", "review"))
    parser.add_argument("--codex")
    parser.add_argument("--model")
    parser.add_argument("--workspace")
    parser.add_argument("--intent", help="要執行的唯讀工作；文字不會授予寫入權限")
    parser.add_argument("--review-dir", help="local-only 審查記錄位置；不得放在 repo 或工作目錄內")
    parser.add_argument("--task", help="要查看／審查的完整工作編號；不自動選最新結果")
    parser.add_argument("--details", action="store_true", help="顯示執行端、Session 與工作目錄")
    args = parser.parse_args()
    view = HumanView(lambda text: print(text, flush=True), details=args.details)
    if args.command != "run":
        try:
            store = ReviewStore(args.review_dir)
            if args.command == "pending":
                targets = store.pending()
                view._write("待審工作：" + str(len(targets)))
                for target in targets:
                    view._write(target.task.id + "  " + target.task.intent)
            elif not args.task:
                raise ReviewError()
            elif args.command == "show":
                show_review(view, store.get(args.task))
            else:
                review_interactively(store, args.task, view, sys.stdin.readline)
            return 0 if view.available else 1
        except (ReviewError, OSError, EOFError, KeyboardInterrupt):
            view._write("未確認審查成功：target 不可用、已消耗、記錄不完整或輸入不明確。請重新查看指定工作；不會自動重試。")
            return 1
    if not all((args.codex, args.model, args.workspace, args.intent)):
        view._write("執行需要既有登入端、model、工作目錄及明確工作內容。")
        return 1
    if sys.stdin.isatty():
        view._write("請由既有可信任登入端啟動；不要在終端機貼上憑證。")
        return 1
    token = sys.stdin.readline().strip()
    runtime = CodexRuntime(args.codex, args.model, lambda: token)
    try:
        companion = Companion(runtime, args.intent, args.workspace, Authority.READ_ONLY)
        store = ReviewStore(args.review_dir, workspace=args.workspace)
    except ValueError:
        view._write("無法建立工作：請提供工作內容及存在的工作目錄。")
        return 1
    task = companion.run(view.progress)
    if task.state == "RESULT_PENDING_REVIEW":
        try:
            store.publish(task)
        except (ReviewError, OSError):
            view._write("結果未能安全保存為待審記錄；未接受任何結果。請勿將執行完成視為 durable review 成功。")
            return 1
    view.result(task)
    if task.state == "RESULT_PENDING_REVIEW":
        view._write("待審結果已保存。稍後可用 show 或 review 搭配 --task 工作編號重新查看／審查。")
    return 0 if task.state == "RESULT_PENDING_REVIEW" and view.available else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Run: python -m src.companion_core --help.

A trusted OAuth host supplies one validated ChatGPT-plan access token on stdin;
never place credentials in command arguments. This entrypoint cannot accept results.
"""
import argparse
import sys

from .codex import CodexRuntime
from .core import Companion
from .domain import Authority
from .presentation import HumanView


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--intent", required=True, help="要執行的唯讀工作；文字不會授予寫入權限")
    parser.add_argument("--details", action="store_true", help="顯示執行端、Session 與工作目錄")
    args = parser.parse_args()
    view = HumanView(lambda text: print(text, flush=True), details=args.details)
    if sys.stdin.isatty():
        view._write("請由既有可信任登入端啟動；不要在終端機貼上憑證。")
        return 1
    token = sys.stdin.readline().strip()
    runtime = CodexRuntime(args.codex, args.model, lambda: token)
    try:
        companion = Companion(runtime, args.intent, args.workspace, Authority.READ_ONLY)
    except ValueError:
        view._write("無法建立工作：請提供工作內容及存在的工作目錄。")
        return 1
    task = companion.run(view.progress)
    view.result(task)
    return 0 if task.state == "RESULT_PENDING_REVIEW" and view.available else 1


if __name__ == "__main__":
    raise SystemExit(main())

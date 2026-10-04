"""Run: python -m src.companion_core --help.

A trusted OAuth host supplies one validated ChatGPT-plan access token on stdin;
never place credentials in command arguments. This entrypoint cannot accept results.
"""
import argparse
from dataclasses import asdict
import json
import sys

from .codex import CodexRuntime
from .core import Companion
from .domain import Authority


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--intent", required=True)
    args = parser.parse_args()
    token = sys.stdin.readline().strip()
    runtime = CodexRuntime(args.codex, args.model, lambda: token)
    companion = Companion(runtime, args.intent, args.workspace, Authority.READ_ONLY)
    task = companion.run(lambda event: print(json.dumps(asdict(event)), flush=True))
    print(json.dumps({"task_id": task.id, "provider": task.provider,
        "session_id": task.session_id, "state": task.state, "result": task.result}), flush=True)
    return 0 if task.state == "RESULT_PENDING_REVIEW" else 1


if __name__ == "__main__":
    raise SystemExit(main())

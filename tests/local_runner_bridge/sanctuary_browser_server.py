"""Isolated browser fixture server. Control is stdin, never a product HTTP route.

Used by verify_sanctuary_browser.cjs; no Operator, runner, GitHub, or production
StateDir is invoked. Real assets/HTTP headers come from WorkflowPanelRequestHandler.
"""
import argparse
import copy
import json
import sys
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from sanctuary_cases import CASES, make_case
import test_workflow_panel as base
from local_runner_bridge.workflow_panel import WorkflowPanelRequestHandler
from local_runner_bridge.sanctuary_projection import project_sanctuary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    cases = {name: make_case(name) for name in CASES}
    control = {"case": "test", "offset": 0, "reset": False, "generation": 0}
    lock = threading.Lock()
    session = uuid.uuid4().hex
    sequence = 0

    class Handler(WorkflowPanelRequestHandler):
        def log_message(self, *args):
            pass

        def _handle_get(self, *, head_only):
            nonlocal sequence
            if urlsplit(self.path).path != "/api/sanctuary":
                return super()._handle_get(head_only=head_only)
            with lock:
                selected = dict(control)
                sequence += 1
                delivery = {"session": session, "sequence": sequence}
            case = copy.deepcopy(cases[selected["case"]])
            now = datetime.now(timezone.utc)
            delta = (now-base.NOW).total_seconds()+selected["offset"]
            def shift(value):
                if isinstance(value, dict):
                    return {k: shift(v) for k, v in value.items()}
                if isinstance(value, list):
                    return [shift(v) for v in value]
                if selected["generation"] and isinstance(value, str) and value in {base.REQUEST_ID, base.RUN_ID}:
                    return value + "-" + str(selected["generation"])
                if isinstance(value, str) and value.startswith("2026-09-06T"):
                    try:
                        return datetime.fromtimestamp(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()+delta,
                                                      timezone.utc).isoformat()
                    except ValueError:
                        pass
                return value
            case = shift(case)
            # Same event source across fixture transitions, until explicit reset.
            case["snapshot"]["observability"]["source_id"] = "fixture-reset" if selected["reset"] else "fixture-source"
            case["world"] = project_sanctuary(case["snapshot"], case["events"], now=now)
            case["delivery"] = delivery
            self._write_panel_response(200, json.dumps(case, ensure_ascii=False).encode("utf-8"),
                                       "application/json; charset=utf-8", head_only=head_only)

    with tempfile.TemporaryDirectory(prefix="sanctuary-browser-") as temp:
        state = Path(temp).resolve()
        server = base.create_workflow_panel_server(state, state / "events.jsonl", port=args.port)
        server.RequestHandlerClass = Handler
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(json.dumps({"url": f"http://127.0.0.1:{server.server_address[1]}", "session": session}), flush=True)
        try:
            for line in sys.stdin:
                command = json.loads(line)
                if command.get("stop"):
                    break
                with lock:
                    control.update(command)
                print(json.dumps({"configured": control}), flush=True)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    main()

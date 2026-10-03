"""Deterministic replay inputs built through the existing canonical Panel fixtures.

This module is test-only. It writes temporary fixture state, never the real StateDir.
"""
import copy
import json
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import test_workflow_panel as base
from local_runner_bridge.workflow_observability import execution_started_event
from local_runner_bridge.sanctuary_projection import project_sanctuary

UNSUPPORTED_TEST_COMMANDS = {
    "pytest-funcargs": "pytest --funcargs",
    "pytest-setup-only": "pytest --setup-only",
    "pytest-setuponly": "pytest --setuponly",
    "pytest-setup-plan": "pytest --setup-plan",
    "pytest-setupplan": "pytest --setupplan",
    "pytest-version-repeat": "pytest -VV",
    "pytest-collectonly": "pytest --collectonly",
    "pytest-cache-show": "pytest --cache-show",
    "pytest-cache-show-pattern": "pytest --cache-show=*",
    "ctest-show-only": "ctest --show-only=json-v1",
    "ctest-print-labels": "ctest --print-labels",
    "vitest-list": "vitest list",
    "vitest-standalone": "vitest --standalone",
    "vitest-clear-cache": "vitest --clearCache",
    "jest-show-config": "jest --showConfig",
    "jest-clear-cache": "jest --clearCache",
}
CASES = ("offline", "idle", "request", "execution", "command", "file", "tool", "test",
         "process-completed", "waiting-review", "technical-repair", "accepted", "blocked",
         "failed", "wrong-request", "wrong-run", "stale", "unknown", "candidate-mismatch",
         "short-test-completed", "short-test-failed", "short-test-review", "wrapped-test", "test-discovery", *UNSUPPORTED_TEST_COMMANDS)


def make_case(name):
    assert name in CASES
    now = base.NOW
    with tempfile.TemporaryDirectory(prefix="sanctuary-fixture-") as directory:
        state = Path(directory).resolve()
        store = base.EventStore(state / "events.jsonl")
        if name != "offline":
            base.write_json(state / "state.json", base.operator_state(last_request_id=base.REQUEST_ID))
            base.write_json(state / "heartbeat.json", base.operator_heartbeat(
                scan_result="eligible_request_detected" if name == "request" else "no_eligible_request",
                scan_reason="ready_for_pickup" if name == "request" else "no_eligible_request",
                scan_request=base.observed_request() if name == "request" else None,
            ))
        running = name in {"execution", "command", "file", "tool", "test", "process-completed",
                           "blocked", "failed", "wrong-request", "wrong-run", "stale", "unknown",
                           "short-test-completed", "short-test-failed", "short-test-review", "wrapped-test", "test-discovery", *UNSUPPORTED_TEST_COMMANDS}
        if running:
            in_flight = base.updated_in_flight_payload(
                base.in_flight_payload(), stage=base.DISPATCHED_NOT_LOCALLY_SETTLED,
                dispatcher_invoked=True, terminal_evidence=None,
                updated_at=now-timedelta(seconds=25),
                dispatcher_process_identity={"platform":"windows", "pid":4321,
                    "start_token":"windows-filetime:12345679", "started_at_utc":"2026-09-06T12:08:05Z"},
            )
            # Stale event still belongs to this request, but cannot power current motion.
            if name == "stale":
                in_flight["prepared_at_utc"] = "2026-09-06T12:06:00Z"
            base.write_json(state / "in_flight.json", in_flight)
            store.append(execution_started_event(
                request_id="another-request-001" if name=="wrong-request" else base.REQUEST_ID,
                run_id=base.RUN_ID, process_id=1234,
                observed_at_utc=(now-timedelta(seconds=45 if name=="stale" else 6)).isoformat(),
            ))
        if name in {"command", "test", "file", "tool", "failed", "wrapped-test", "test-discovery", *UNSUPPORTED_TEST_COMMANDS}:
            item={"id":"fixture-item-1", "type":"command_execution", "command":"pytest -q" if name=="test" else "git diff", "status":"in_progress"}
            if name=="wrapped-test":item["command"]='''pwsh.exe -Command "& '.\\.venv-course\\Scripts\\python.exe' -B -m pytest -q"'''
            if name=="test-discovery":item["command"]="pytest --help"
            if name in UNSUPPORTED_TEST_COMMANDS:item["command"]=UNSUPPORTED_TEST_COMMANDS[name]
            if name=="file":item={"id":"fixture-file-1","type":"file_change","changes":[{"path":"src/example.py"}],"status":"completed"}
            if name=="tool":item={"id":"fixture-tool-1","type":"mcp_tool_call","status":"in_progress"}
            if name=="failed":item.update(exit_code=1,status="failed")
            base.add_event(store.path,{"type":"item.completed" if name in {"file","failed"} else "item.started","item":item},observed_at=(now-timedelta(seconds=2)).isoformat())
        if name=="process-completed":
            store.append(base.project_runner_control({"type":"process.completed","exit_code":0,"observed_at_utc":(now-timedelta(seconds=1)).isoformat()},request_id=base.REQUEST_ID,run_id=base.RUN_ID))
        if name=="blocked":base.write_json(state / "last_failure.json",base.current_failure())
        if name=="unknown":base.write_json(state / "in_flight.json",{"protocol":"invalid"})
        if name.startswith("short-test-"):
            # Both events are persisted before the browser's first observation.
            item = {"id":"short-test-1", "type":"command_execution", "status":"in_progress",
                    "command":'''pwsh.exe -Command "& '.\\.venv-course\\Scripts\\python.exe' -B -m pytest -q"'''}
            base.add_event(store.path,{"type":"item.started","item":item},observed_at=(now-timedelta(seconds=2)).isoformat())
            item.update(status="completed", exit_code=1 if name=="short-test-failed" else 0)
            base.add_event(store.path,{"type":"item.completed","item":item},observed_at=(now-timedelta(seconds=1.245)).isoformat())
            if name=="short-test-review":
                store.append(base.project_runner_control({"type":"process.completed","exit_code":0,"observed_at_utc":(now-timedelta(seconds=1)).isoformat()},request_id=base.REQUEST_ID,run_id=base.RUN_ID))
                (state / "in_flight.json").unlink()
        if name in {"waiting-review","technical-repair","accepted","candidate-mismatch", "short-test-review"}:
            record=base.processed_record()
            base.append_processed(state,record)
            base.write_json(state / "review_candidate.json",base.new_review_candidate_payload(
                target_repository=record["target_repository"],target_issue=record["target_issue"],
                dispatch_request_id=record["target_dispatch_request_id"],action=record["requested_action"],
                branch=record["expected_branch"],expected_head=record["expected_head"],
                terminal_result_comment_id="5559170694",review_bundle_comment_id="5559170528",
                candidate_manifest_fingerprint="a"*64,target_repo_root=str(state),recorded_at=now-timedelta(seconds=15),
            ))
            if name in {"technical-repair","accepted","candidate-mismatch"}:
                verdict=base.final_review_verdict(verdict="repair_required" if name=="technical-repair" else "accepted",candidate_acceptance="eligible",candidate_manifest_fingerprint="b"*64 if name=="candidate-mismatch" else "a"*64)
                verdict["reviewed_at_utc"]=(now-timedelta(seconds=5)).isoformat().replace("+00:00","Z")
                base.append_final_review_verdict(state / "final_review_verdicts.jsonl",verdict,trusted_actors=("HarryWhite-TW",))
        snapshot=base.build_workflow_snapshot(state,store,now=now)
        events,_=store.read()
        if name=="wrong-run":
            events=copy.deepcopy(events)
            for event in events:event["run_id"]="unmatched-run-999"
        world=project_sanctuary(snapshot,events,now=now)
        return {"snapshot":snapshot,"events":events,"world":world}


if __name__=="__main__":
    Path(sys.argv[1]).write_text(json.dumps({name:make_case(name) for name in CASES},ensure_ascii=False,indent=2),encoding="utf-8")

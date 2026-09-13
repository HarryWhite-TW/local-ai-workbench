import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from local_runner_bridge.bridge_operator_lifecycle_state import (
    DISPATCHED_NOT_LOCALLY_SETTLED,
    new_in_flight_payload,
    new_review_candidate_payload,
    updated_in_flight_payload,
)
from local_runner_bridge.workflow_observability import (
    EventStore,
    ObservationError,
    project_codex_line,
    project_runner_control,
)
from local_runner_bridge.workflow_panel import (
    PANEL_PROTOCOL,
    build_workflow_snapshot,
    create_workflow_panel_server,
)


REQUEST_ID = "workflow-panel-request-308"
RUN_ID = "workflow-panel-run-308"
NOW = datetime(2026, 9, 6, 12, 8, 30, tzinfo=timezone.utc)


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def in_flight_payload() -> dict:
    return new_in_flight_payload(
        request_id=REQUEST_ID,
        target_repository="HarryWhite-TW/local-ai-workbench",
        target_issue=308,
        dispatch_request_id="workflow-panel-dispatch-308",
        action="run-reviewbundle",
        branch="master",
        expected_head="d8118bd9649f09cf9dc9ec0a20ac5ab8dd81fd7c",
        operator_session_id="a" * 32,
        process_identity={
            "platform": "windows",
            "pid": 1234,
            "start_token": "windows-filetime:12345678",
            "started_at_utc": "2026-09-06T12:08:00Z",
        },
        prepared_at=datetime(2026, 9, 6, 12, 8, tzinfo=timezone.utc),
    )


def add_event(
    store_path: Path,
    source: dict,
    *,
    observed_at: str,
    request_id: str = REQUEST_ID,
    run_id: str = RUN_ID,
) -> dict:
    return EventStore(store_path).append(
        project_codex_line(
            json.dumps(source),
            request_id=request_id,
            run_id=run_id,
            observed_at_utc=observed_at,
        )
    )


def operator_state(
    *, status: str = "running", last_request_id: str | None = None
) -> dict:
    return {
        "protocol": "lawb.bridge_operator_b3_state.v1",
        "status": status,
        "mode": "b3c-run-reviewbundle",
        "repo": "HarryWhite-TW/local-ai-workbench",
        "cycles_completed": 2,
        "last_request_id": last_request_id,
        "updated_at_utc": "2026-09-06T12:08:02Z",
    }


def operator_heartbeat(
    *,
    status: str = "polling",
    request_id: str | None = None,
    target_issue: int = 308,
    updated_at: str = "2026-09-06T12:08:03Z",
    scan_result: str | None = None,
    scan_reason: str = "no_eligible_request",
    scan_request: dict | None = None,
) -> dict:
    value = {
        "protocol": "lawb.bridge_operator_b3_heartbeat.v1",
        "status": status,
        "mode": "b3c-run-reviewbundle",
        "cycle": 2,
        "request_id": request_id,
        "target_issue": target_issue if request_id else None,
        "updated_at_utc": updated_at,
        "configured_poll_interval_seconds": 30.0,
        "configured_timeout_seconds": 600,
    }
    if scan_result is not None:
        value.update(
            {
                "last_inbox_scan_at_utc": updated_at,
                "last_inbox_scan_cycle": 2,
                "last_inbox_scan_result": scan_result,
                "last_inbox_scan_reason": scan_reason,
                "eligible_request_count": 1
                if scan_result == "eligible_request_detected"
                else 0,
                "last_inbox_request": scan_request,
            }
        )
    return value


def observed_request(
    *,
    request_id: str = REQUEST_ID,
    decision: str = "ready_for_pickup",
    reason: str = "ready_for_pickup",
    expires: str = "20260906T121800Z",
) -> dict:
    return {
        "request_id": request_id,
        "target_issue": 308,
        "requested_action": "run-reviewbundle",
        "expires": expires,
        "observed_at_utc": "2026-09-06T12:08:20Z",
        "pickup_decision": decision,
        "reason": reason,
    }


def processed_record(
    *,
    request_id: str = REQUEST_ID,
    action: str = "run-reviewbundle",
    result: str = "success",
    observed_at: str = "2026-09-06T12:08:10Z",
    result_comment_id: str | None = "5559170694",
    target_issue: int = 308,
) -> dict:
    return {
        "protocol": "lawb.bridge_operator_b3_processed_request.v1",
        "processed_at_utc": observed_at,
        "cycle": 2,
        "request_id": request_id,
        "target_repository": "HarryWhite-TW/local-ai-workbench",
        "target_issue": target_issue,
        "target_dispatch_request_id": f"{request_id}-dispatch",
        "requested_action": action,
        "expected_branch": "master",
        "expected_head": "d8118bd9649f09cf9dc9ec0a20ac5ab8dd81fd7c",
        "target_result_comment_id": result_comment_id,
        "target_result_author": "HarryWhite-TW",
        "terminal_result": result,
        "terminal_settlement": (
            "settled_success" if result == "success" else "settled_non_success"
        ),
        "terminal_observed_at_utc": observed_at,
        "dispatcher_invoked": True,
        "result_verified": True,
        "lifecycle_state": "CONSUMED",
    }


def append_processed(state_dir: Path, record: dict) -> None:
    with (state_dir / "processed_requests.jsonl").open(
        "a", encoding="utf-8", newline="\n"
    ) as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")


def current_failure(*, request_id: str = REQUEST_ID) -> dict:
    return {
        "protocol": "lawb.bridge_operator_b3_failure.v1",
        "failed_at_utc": "2026-09-06T12:08:09Z",
        "reason": "task_packet_id_request_id_mismatch",
        "request_id": request_id,
        "current_failure_recorded": True,
        "last_failure_json_applies_to_current_run": True,
        "last_failure_json_status": "current_failure",
    }


def start_panel(state_dir: Path, store_path: Path):
    server = create_workflow_panel_server(state_dir, store_path, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def stop_panel(server, thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def sse_data(body: str) -> list[dict]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


def read_sse_data_frame(response) -> dict:
    while True:
        line = response.readline().decode("utf-8")
        if not line:
            raise AssertionError("SSE stream ended before a data frame")
        if line.startswith("data: "):
            return json.loads(line.removeprefix("data: "))


def test_snapshot_combines_validated_lifecycle_and_matching_observation(tmp_path):
    state_dir = (tmp_path / "state").resolve()
    state_dir.mkdir()
    store_path = (tmp_path / "events.jsonl").resolve()
    write_json(state_dir / "state.json", operator_state(last_request_id=REQUEST_ID))
    write_json(
        state_dir / "heartbeat.json",
        operator_heartbeat(status="running", request_id=REQUEST_ID),
    )
    write_json(state_dir / "in_flight.json", in_flight_payload())
    add_event(
        store_path,
        {"type": "turn.started"},
        observed_at="2026-09-06T12:08:04Z",
    )

    snapshot = build_workflow_snapshot(state_dir, EventStore(store_path))

    assert snapshot["protocol"] == PANEL_PROTOCOL
    assert snapshot["mode"] == "read_only"
    assert snapshot["bind"] == "loopback"
    assert snapshot["current_task"] == {
        "request_id": REQUEST_ID,
        "issue_number": 308,
        "action": "run-reviewbundle",
        "detected_at_utc": "2026-09-06T12:08:00Z",
        "expires_at_utc": None,
        "pickup_decision": "picked_up",
        "pickup_reason": None,
        "lifecycle": {
            "stage": "DISPATCHING",
            "certainty": "verified",
            "basis": "in_flight:PREPARED",
        },
        "updated_at_utc": "2026-09-06T12:08:00Z",
        "terminal_result": None,
    }
    assert snapshot["observability"]["event_count"] == 1
    assert snapshot["observability"]["request_event_count"] == 1
    assert snapshot["observability"]["latest_sequence"] == 1
    assert snapshot["observability"]["run_id"] == RUN_ID
    assert snapshot["observability"]["stream_url"] == "/events?follow=1"
    assert snapshot["review"]["changed_files"] == {
        "status": "unavailable",
        "items": [],
    }
    serialized = json.dumps(snapshot)
    assert "process_identity" not in serialized
    assert "expected_head" not in serialized


def test_invalid_in_flight_fails_closed_instead_of_claiming_completion(tmp_path):
    state_dir = (tmp_path / "state").resolve()
    state_dir.mkdir()
    store_path = (tmp_path / "events.jsonl").resolve()
    (state_dir / "in_flight.json").write_text('{"protocol":"wrong"}', encoding="utf-8")
    add_event(
        store_path,
        {"type": "turn.completed"},
        observed_at="2026-09-06T12:08:05Z",
    )

    snapshot = build_workflow_snapshot(state_dir, EventStore(store_path))

    assert snapshot["current_task"]["lifecycle"] == {
        "stage": "UNKNOWN",
        "certainty": "unknown",
        "basis": "in_flight_evidence_invalid",
    }
    assert snapshot["source_status"]["in_flight"] == "invalid"
    assert snapshot["diagnostics"] == ["in_flight_evidence_invalid"]


def test_process_completion_activity_never_becomes_lifecycle_terminal_truth(tmp_path):
    state_dir = (tmp_path / "state").resolve()
    state_dir.mkdir()
    store_path = (tmp_path / "events.jsonl").resolve()
    add_event(
        store_path,
        {"type": "turn.completed"},
        observed_at="2026-09-06T12:08:05Z",
    )
    EventStore(store_path).append(
        project_runner_control(
            {
                "type": "process.completed",
                "observed_at_utc": "2026-09-06T12:08:06Z",
                "exit_code": 0,
                "timed_out": False,
                "duration_ms": 1000,
            },
            request_id=REQUEST_ID,
            run_id=RUN_ID,
        )
    )

    snapshot = build_workflow_snapshot(state_dir, EventStore(store_path))

    assert snapshot["current_task"]["request_id"] is None
    assert snapshot["current_task"]["lifecycle"] == {
        "stage": "UNKNOWN",
        "certainty": "unknown",
        "basis": "no_current_request_evidence",
    }
    assert snapshot["observability"]["latest_sequence"] == 2


@pytest.mark.parametrize(
    ("action", "result", "expected_stage"),
    [
        ("run-reviewbundle", "success", "WAITING_FOR_CHATGPT_REVIEW"),
        ("read-final-audit", "success", "COMPLETED_OR_LAST_COMPLETED"),
        ("read-final-audit", "blocked", "BLOCKED_OR_FAILED"),
    ],
)
def test_processed_terminal_truth_projects_review_completed_and_blocked(
    tmp_path, action, result, expected_stage
):
    state_dir = (tmp_path / "state").resolve()
    state_dir.mkdir()
    store_path = (tmp_path / "events.jsonl").resolve()
    write_json(state_dir / "state.json", operator_state(last_request_id=REQUEST_ID))
    append_processed(state_dir, processed_record(action=action, result=result))
    add_event(
        store_path,
        {"type": "turn.completed"},
        observed_at="2026-09-06T12:08:11Z",
    )

    snapshot = build_workflow_snapshot(state_dir, EventStore(store_path))

    assert snapshot["current_task"]["lifecycle"]["stage"] == expected_stage
    assert snapshot["current_task"]["lifecycle"]["certainty"] == "verified"
    assert snapshot["current_task"]["lifecycle"]["basis"] == f"processed_request:{result}"
    assert snapshot["current_task"]["terminal_result"] == result


@pytest.mark.parametrize(
    ("new_action", "new_result", "expected_stage"),
    [
        ("run-reviewbundle", "success", "WAITING_FOR_CHATGPT_REVIEW"),
        ("read-final-audit", "failure", "BLOCKED_OR_FAILED"),
    ],
)
def test_newest_terminal_truth_outranks_stale_state_and_review_candidate(
    tmp_path, new_action, new_result, expected_stage
):
    state_dir = (tmp_path / "state").resolve()
    state_dir.mkdir()
    old_request = "minimal-workflow-panel-v1-308-old"
    new_request = "minimal-workflow-panel-live-smoke-310-new"
    write_json(
        state_dir / "state.json",
        operator_state(status="running", last_request_id=old_request),
    )
    write_json(
        state_dir / "heartbeat.json",
        operator_heartbeat(
            status="polling", request_id=new_request, target_issue=310
        ),
    )
    old_record = processed_record(
        request_id=old_request,
        observed_at="2026-09-06T12:08:10Z",
        result_comment_id="5559170694",
        target_issue=308,
    )
    new_record = processed_record(
        request_id=new_request,
        action=new_action,
        result=new_result,
        observed_at="2026-09-07T11:54:17Z",
        result_comment_id="5570230576",
        target_issue=310,
    )
    append_processed(state_dir, old_record)
    append_processed(state_dir, new_record)
    write_json(
        state_dir / "review_candidate.json",
        new_review_candidate_payload(
            target_repository=old_record["target_repository"],
            target_issue=old_record["target_issue"],
            dispatch_request_id=old_record["target_dispatch_request_id"],
            action=old_record["requested_action"],
            branch=old_record["expected_branch"],
            expected_head=old_record["expected_head"],
            terminal_result_comment_id="5559170694",
            review_bundle_comment_id="5559170528",
            candidate_manifest_fingerprint="0" * 64,
            target_repo_root=str(tmp_path.resolve()),
            recorded_at=datetime(2026, 9, 6, 12, 8, tzinfo=timezone.utc),
        ),
    )

    snapshot = build_workflow_snapshot(
        state_dir, EventStore((tmp_path / "events.jsonl").resolve())
    )

    assert snapshot["current_task"] == {
        "request_id": new_request,
        "issue_number": 310,
        "action": new_action,
        "detected_at_utc": "2026-09-07T11:54:17Z",
        "expires_at_utc": None,
        "pickup_decision": "completed",
        "pickup_reason": None,
        "lifecycle": {
            "stage": expected_stage,
            "certainty": "verified",
            "basis": f"processed_request:{new_result}",
        },
        "updated_at_utc": "2026-09-07T11:54:17Z",
        "terminal_result": new_result,
    }
    assert snapshot["review"]["evidence"] == {
        "status": "available",
        "pointer": "issue_comment:5570230576",
        "summary": "Trusted terminal result",
    }
    assert snapshot["source_status"]["review_candidate"] == (
        "historical_or_unmatched"
    )


def test_current_in_flight_outranks_newer_processed_terminal(tmp_path):
    state_dir = (tmp_path / "state").resolve()
    state_dir.mkdir()
    write_json(
        state_dir / "state.json", operator_state(last_request_id="old-request")
    )
    append_processed(
        state_dir,
        processed_record(
            request_id="newer-terminal-request",
            observed_at="2026-09-07T11:54:17Z",
            target_issue=310,
        ),
    )
    write_json(state_dir / "in_flight.json", in_flight_payload())

    snapshot = build_workflow_snapshot(
        state_dir, EventStore((tmp_path / "events.jsonl").resolve())
    )

    assert snapshot["current_task"]["request_id"] == REQUEST_ID
    assert snapshot["current_task"]["lifecycle"] == {
        "stage": "DISPATCHING",
        "certainty": "verified",
        "basis": "in_flight:PREPARED",
    }


def test_dispatched_in_flight_projects_running_request(tmp_path):
    state_dir = (tmp_path / "state").resolve()
    state_dir.mkdir()
    payload = updated_in_flight_payload(
        in_flight_payload(),
        stage=DISPATCHED_NOT_LOCALLY_SETTLED,
        dispatcher_invoked=True,
        terminal_evidence=None,
        updated_at=datetime(2026, 9, 6, 12, 8, 5, tzinfo=timezone.utc),
        dispatcher_process_identity={
            "platform": "windows",
            "pid": 4321,
            "start_token": "windows-filetime:12345679",
            "started_at_utc": "2026-09-06T12:08:05Z",
        },
    )
    write_json(state_dir / "in_flight.json", payload)

    snapshot = build_workflow_snapshot(
        state_dir, EventStore((tmp_path / "events.jsonl").resolve()), now=NOW
    )

    assert snapshot["current_task"]["lifecycle"]["stage"] == "RUNNING"
    assert snapshot["system"]["next_action"] == (
        "Task is running. You do not need to do anything."
    )


def test_current_failure_outranks_in_flight_and_observation_activity(tmp_path):
    state_dir = (tmp_path / "state").resolve()
    state_dir.mkdir()
    store_path = (tmp_path / "events.jsonl").resolve()
    write_json(state_dir / "state.json", operator_state(status="blocked", last_request_id=REQUEST_ID))
    write_json(state_dir / "heartbeat.json", operator_heartbeat(status="blocked", request_id=REQUEST_ID))
    write_json(state_dir / "in_flight.json", in_flight_payload())
    write_json(state_dir / "last_failure.json", current_failure())
    add_event(
        store_path,
        {"type": "turn.completed"},
        observed_at="2026-09-06T12:08:10Z",
    )

    snapshot = build_workflow_snapshot(state_dir, EventStore(store_path))

    assert snapshot["current_task"]["lifecycle"] == {
        "stage": "BLOCKED_OR_FAILED",
        "certainty": "verified",
        "basis": "current_failure",
    }
    assert snapshot["review"]["warning_or_error"] == {
        "status": "available",
        "code": "task_packet_id_request_id_mismatch",
        "source": "current_failure",
        "observed_at_utc": "2026-09-06T12:08:09Z",
    }


def test_missing_scan_observation_does_not_claim_no_request(tmp_path):
    state_dir = (tmp_path / "state").resolve()
    state_dir.mkdir()
    write_json(state_dir / "state.json", operator_state())
    write_json(state_dir / "heartbeat.json", operator_heartbeat())

    snapshot = build_workflow_snapshot(
        state_dir, EventStore((tmp_path / "events.jsonl").resolve())
    )

    assert snapshot["current_task"]["request_id"] is None
    assert snapshot["current_task"]["lifecycle"]["stage"] == "UNKNOWN"
    assert snapshot["operator"]["activity"]["observation_status"] == "missing"


def test_recent_polling_and_empty_scan_projects_ready_no_request(tmp_path):
    state_dir = (tmp_path / "state").resolve()
    state_dir.mkdir()
    write_json(state_dir / "state.json", operator_state())
    write_json(
        state_dir / "heartbeat.json",
        operator_heartbeat(
            status="waiting",
            updated_at="2026-09-06T12:08:20Z",
            scan_result="no_eligible_request",
        ),
    )

    snapshot = build_workflow_snapshot(
        state_dir,
        EventStore((tmp_path / "events.jsonl").resolve()),
        now=NOW,
    )

    assert snapshot["system"] == {
        "readiness": "ready",
        "workflow": "ready",
        "operator": "online",
        "panel": "online",
        "next_action": (
            "Everything is ready. The last check found no request, so you do not "
            "need to do anything."
        ),
    }
    assert snapshot["current_task"]["lifecycle"]["stage"] == "NO_REQUEST_DETECTED"
    assert snapshot["operator"]["activity"] == {
        "health": "online",
        "heartbeat_at_utc": "2026-09-06T12:08:20Z",
        "heartbeat_age_seconds": 10.0,
        "stale_after_seconds": 90.0,
        "last_check_at_utc": "2026-09-06T12:08:20Z",
        "last_check_age_seconds": 10.0,
        "poll_interval_seconds": 30.0,
        "cycle": 2,
        "scan_result": "no_eligible_request",
        "scan_reason": "no_eligible_request",
        "eligible_request_count": 0,
        "observation_status": "available",
    }


def test_stale_heartbeat_makes_operator_effectively_unavailable(tmp_path):
    state_dir = (tmp_path / "state").resolve()
    state_dir.mkdir()
    write_json(state_dir / "state.json", operator_state())
    write_json(
        state_dir / "heartbeat.json",
        operator_heartbeat(
            status="waiting",
            updated_at="2026-09-06T12:06:00Z",
            scan_result="no_eligible_request",
        ),
    )

    snapshot = build_workflow_snapshot(
        state_dir,
        EventStore((tmp_path / "events.jsonl").resolve()),
        now=NOW,
    )

    assert snapshot["system"]["readiness"] == "unavailable"
    assert snapshot["system"]["operator"] == "stale"
    assert snapshot["system"]["next_action"] == (
        "Operator has not checked for work recently."
    )
    assert snapshot["current_task"]["lifecycle"]["stage"] == "UNKNOWN"


def test_detected_request_waiting_for_pickup_exposes_only_safe_identity(tmp_path):
    state_dir = (tmp_path / "state").resolve()
    state_dir.mkdir()
    write_json(state_dir / "state.json", operator_state())
    write_json(
        state_dir / "heartbeat.json",
        operator_heartbeat(
            status="request_detected",
            updated_at="2026-09-06T12:08:20Z",
            scan_result="eligible_request_detected",
            scan_reason="ready_for_pickup",
            scan_request=observed_request(),
        ),
    )

    snapshot = build_workflow_snapshot(
        state_dir,
        EventStore((tmp_path / "events.jsonl").resolve()),
        now=NOW,
    )

    assert snapshot["current_task"]["lifecycle"]["stage"] == "REQUEST_DETECTED"
    assert snapshot["current_task"]["request_id"] == REQUEST_ID
    assert snapshot["current_task"]["issue_number"] == 308
    assert snapshot["current_task"]["action"] == "run-reviewbundle"
    assert snapshot["current_task"]["detected_at_utc"] == "2026-09-06T12:08:20Z"
    assert snapshot["current_task"]["expires_at_utc"] == "2026-09-06T12:18:00Z"
    assert snapshot["system"]["next_action"] == (
        "A request was detected and is waiting to start."
    )


def test_expired_request_observation_is_explicit(tmp_path):
    state_dir = (tmp_path / "state").resolve()
    state_dir.mkdir()
    write_json(state_dir / "state.json", operator_state())
    write_json(
        state_dir / "heartbeat.json",
        operator_heartbeat(
            status="waiting",
            updated_at="2026-09-06T12:08:20Z",
            scan_result="expired_request_observed",
            scan_reason="request_expired",
            scan_request=observed_request(
                decision="expired",
                reason="request_expired",
                expires="2026-09-06T12:07:00Z",
            ),
        ),
    )

    snapshot = build_workflow_snapshot(
        state_dir,
        EventStore((tmp_path / "events.jsonl").resolve()),
        now=NOW,
    )

    assert snapshot["current_task"]["lifecycle"]["stage"] == "EXPIRED"
    assert snapshot["current_task"]["pickup_decision"] == "expired"
    assert snapshot["system"]["next_action"] == (
        "The observed request expired and will not start."
    )


def test_malformed_scan_observation_degrades_to_unknown(tmp_path):
    state_dir = (tmp_path / "state").resolve()
    state_dir.mkdir()
    heartbeat = operator_heartbeat(status="waiting", updated_at="2026-09-06T12:08:20Z")
    heartbeat["last_inbox_scan_result"] = "eligible_request_detected"
    write_json(state_dir / "heartbeat.json", heartbeat)

    snapshot = build_workflow_snapshot(
        state_dir,
        EventStore((tmp_path / "events.jsonl").resolve()),
        now=NOW,
    )

    assert snapshot["current_task"]["lifecycle"]["stage"] == "UNKNOWN"
    assert snapshot["operator"]["activity"]["observation_status"] == "invalid"
    assert "inbox_scan_observation_invalid" in snapshot["diagnostics"]


def test_scan_projection_omits_sensitive_and_arbitrary_fields(tmp_path):
    state_dir = (tmp_path / "state").resolve()
    state_dir.mkdir()
    request = observed_request()
    request.update(
        {
            "prompt": "do not expose prompt text",
            "command": "do not expose command body",
            "token": "do not expose credentials",
        }
    )
    heartbeat = operator_heartbeat(
        status="request_detected",
        updated_at="2026-09-06T12:08:20Z",
        scan_result="eligible_request_detected",
        scan_reason="ready_for_pickup",
        scan_request=request,
    )
    heartbeat["environment"] = {"SECRET": "do not expose environment"}
    write_json(state_dir / "heartbeat.json", heartbeat)

    snapshot = build_workflow_snapshot(
        state_dir,
        EventStore((tmp_path / "events.jsonl").resolve()),
        now=NOW,
    )
    serialized = json.dumps(snapshot)

    assert snapshot["current_task"]["request_id"] == REQUEST_ID
    for secret in (
        "do not expose prompt text",
        "do not expose command body",
        "do not expose credentials",
        "do not expose environment",
    ):
        assert secret not in serialized


def test_trusted_terminal_truth_outranks_same_request_scan_activity(tmp_path):
    state_dir = (tmp_path / "state").resolve()
    state_dir.mkdir()
    append_processed(state_dir, processed_record())
    write_json(
        state_dir / "heartbeat.json",
        operator_heartbeat(
            status="request_detected",
            updated_at="2026-09-06T12:08:20Z",
            scan_result="eligible_request_detected",
            scan_reason="ready_for_pickup",
            scan_request=observed_request(),
        ),
    )

    snapshot = build_workflow_snapshot(
        state_dir,
        EventStore((tmp_path / "events.jsonl").resolve()),
        now=NOW,
    )

    assert snapshot["current_task"]["lifecycle"]["stage"] == (
        "WAITING_FOR_CHATGPT_REVIEW"
    )
    assert snapshot["current_task"]["lifecycle"]["basis"] == (
        "processed_request:success"
    )
    assert snapshot["current_task"]["detected_at_utc"] == "2026-09-06T12:08:20Z"
    assert snapshot["current_task"]["expires_at_utc"] == "2026-09-06T12:18:00Z"
    assert snapshot["current_task"]["pickup_reason"] == "ready_for_pickup"


def test_stale_failure_and_review_candidate_do_not_become_current(tmp_path):
    state_dir = (tmp_path / "state").resolve()
    state_dir.mkdir()
    latest_request = "workflow-panel-final-audit-308"
    write_json(state_dir / "state.json", operator_state(last_request_id=latest_request))
    append_processed(
        state_dir,
        processed_record(
            request_id=latest_request,
            action="read-final-audit",
            result_comment_id=None,
        ),
    )
    write_json(state_dir / "last_failure.json", current_failure(request_id="unrelated-old-request"))
    write_json(
        state_dir / "review_candidate.json",
        new_review_candidate_payload(
            target_repository="HarryWhite-TW/local-ai-workbench",
            target_issue=308,
            dispatch_request_id="unrelated-old-dispatch",
            action="run-reviewbundle",
            branch="master",
            expected_head="d8118bd9649f09cf9dc9ec0a20ac5ab8dd81fd7c",
            terminal_result_comment_id="5559170694",
            review_bundle_comment_id="5559170528",
            candidate_manifest_fingerprint="0" * 64,
            target_repo_root=str(tmp_path.resolve()),
            recorded_at=datetime(2026, 9, 6, 12, 8, tzinfo=timezone.utc),
        ),
    )

    snapshot = build_workflow_snapshot(
        state_dir, EventStore((tmp_path / "events.jsonl").resolve())
    )

    assert snapshot["current_task"]["request_id"] == latest_request
    assert snapshot["current_task"]["lifecycle"]["stage"] == "COMPLETED_OR_LAST_COMPLETED"
    assert snapshot["review"]["warning_or_error"]["status"] == "unavailable"
    assert snapshot["review"]["evidence"]["status"] == "unavailable"
    assert snapshot["source_status"]["last_failure"] == "historical_not_current"
    assert snapshot["source_status"]["review_candidate"] == "historical_or_unmatched"


def test_matching_review_candidate_exposes_only_bounded_trusted_evidence_pointer(tmp_path):
    state_dir = (tmp_path / "state").resolve()
    state_dir.mkdir()
    record = processed_record()
    append_processed(state_dir, record)
    write_json(
        state_dir / "review_candidate.json",
        new_review_candidate_payload(
            target_repository=record["target_repository"],
            target_issue=record["target_issue"],
            dispatch_request_id=record["target_dispatch_request_id"],
            action=record["requested_action"],
            branch=record["expected_branch"],
            expected_head=record["expected_head"],
            terminal_result_comment_id="5559170694",
            review_bundle_comment_id="5559170528",
            candidate_manifest_fingerprint="0" * 64,
            target_repo_root=str(tmp_path.resolve()),
            recorded_at=datetime(2026, 9, 6, 12, 8, tzinfo=timezone.utc),
        ),
    )

    snapshot = build_workflow_snapshot(
        state_dir, EventStore((tmp_path / "events.jsonl").resolve())
    )

    assert snapshot["review"]["changed_files"] == {"status": "unavailable", "items": []}
    assert snapshot["review"]["test_summary"] == {
        "status": "unavailable",
        "summary": None,
    }
    assert snapshot["review"]["evidence"] == {
        "status": "available",
        "pointer": "issue_comment:5559170528",
        "summary": "Trusted review bundle; candidate manifest " + "0" * 64,
    }


def test_malformed_lifecycle_evidence_degrades_without_using_unknown_activity(tmp_path):
    state_dir = (tmp_path / "state").resolve()
    state_dir.mkdir()
    store_path = (tmp_path / "events.jsonl").resolve()
    write_json(
        state_dir / "last_failure.json",
        {"protocol": "lawb.bridge_operator_b3_failure.v1", "reason": "<script>x</script>"},
    )
    warning = add_event(
        store_path,
        {"type": "future.event", "payload": "<img src=x onerror=alert(1)>"},
        observed_at="2026-09-06T12:08:12Z",
    )

    snapshot = build_workflow_snapshot(state_dir, EventStore(store_path))

    assert warning["kind"] == "observability.source_warning"
    assert "<img" not in json.dumps(warning)
    assert snapshot["current_task"]["lifecycle"]["stage"] == "UNKNOWN"
    assert "last_failure_evidence_invalid" in snapshot["diagnostics"]
    assert snapshot["review"]["warning_or_error"]["status"] == "unavailable"
    assert "<script>" not in json.dumps(snapshot)


def test_temporary_fixture_panel_http_static_snapshot_sse_and_read_only_methods(tmp_path):
    state_dir = (tmp_path / "state").resolve()
    state_dir.mkdir()
    store_path = (tmp_path / "events.jsonl").resolve()
    write_json(state_dir / "in_flight.json", in_flight_payload())
    event = add_event(
        store_path,
        {
            "type": "item.completed",
            "item": {
                "id": "command-1",
                "type": "command_execution",
                "command": "python -m pytest secret-argument",
                "aggregated_output": "private output must not be projected",
                "exit_code": 0,
                "status": "completed",
            },
        },
        observed_at="2026-09-06T12:08:06Z",
    )
    server, thread = start_panel(state_dir, store_path)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(f"{base}/", timeout=2) as response:
            html = response.read().decode("utf-8")
            assert response.headers["Content-Security-Policy"].startswith("default-src 'self'")
        assert "Workflow Panel" in html
        assert "approval" not in html.lower()
        assert 'id="readiness"' in html
        assert 'id="operator-health"' in html
        assert 'id="last-check-time"' in html
        assert 'id="poll-cadence"' in html
        assert 'id="request-action"' in html
        assert 'id="pickup-decision"' in html
        assert 'id="warning-or-error"' in html
        assert 'id="changed-files"' in html
        assert 'id="test-summary"' in html
        assert 'id="evidence-summary"' in html

        with urlopen(f"{base}/workflow_panel.js", timeout=2) as response:
            assert response.headers.get_content_type() == "text/javascript"
            javascript = response.read().decode("utf-8")
        assert "EventSource" in javascript
        assert ".innerHTML" not in javascript
        assert "textContent" in javascript
        assert "sessionStorage.getItem(CURSOR_KEY)" in javascript
        assert "setInterval(() => refreshSnapshot(false), SNAPSHOT_POLL_MS)" in javascript
        assert "if (eventSource && connectedStreamUrl === streamUrl) return" in javascript

        with urlopen(f"{base}/api/state", timeout=2) as response:
            snapshot = json.loads(response.read())
        assert snapshot["current_task"]["request_id"] == REQUEST_ID
        assert snapshot["observability"]["latest_sequence"] == event["sequence"]

        with urlopen(
            f"{base}/events?follow=0&request_id={REQUEST_ID}&run_id={RUN_ID}",
            timeout=2,
        ) as response:
            replay = sse_data(response.read().decode("utf-8"))
        assert replay[0]["payload"] == {
            "item_id": "command-1",
            "status": "completed",
            "command_name": "python",
            "exit_code": 0,
        }
        assert "private output" not in json.dumps(replay)
        assert "secret-argument" not in json.dumps(replay)

        with urlopen(f"{base}/health", timeout=2) as response:
            health = json.loads(response.read())
        assert health == {
            "protocol": PANEL_PROTOCOL,
            "status": "ready",
            "mode": "read_only",
            "bind": "loopback",
            "observation_protocol": "lawb.workflow_observation_stream.v1",
        }

        for method in ("POST", "PUT", "DELETE"):
            with pytest.raises(HTTPError) as error:
                urlopen(Request(f"{base}/api/state", method=method), timeout=2)
            assert error.value.code == 405
            assert error.value.headers["Allow"] == "GET, HEAD"
        with pytest.raises(HTTPError) as error:
            urlopen(f"{base}/api/stop", timeout=2)
        assert error.value.code == 404
    finally:
        stop_panel(server, thread)


def test_javascript_cursor_survives_rebind_and_rejects_duplicate_or_reordered_events():
    script_path = ROOT / "src" / "local_runner_bridge" / "workflow_panel.js"
    node_script = """
const panel = require(process.argv[1]);
const base = {sequence: 11, kind: 'codex.turn.started', observed_at_utc: '2026-09-06T12:00:00Z', payload: {}};
let state = panel.mergeEventCache([], base, 10);
const duplicate = panel.mergeEventCache(state.events, base, state.lastSequence);
const reordered = panel.mergeEventCache(state.events, {...base, sequence: 9}, state.lastSequence);
state = panel.mergeEventCache(state.events, {...base, sequence: 12}, state.lastSequence);
process.stdout.write(JSON.stringify({
  firstAccepted: state.events.some((event) => event.sequence === 11),
  duplicateAccepted: duplicate.accepted,
  reorderedAccepted: reordered.accepted,
  sequences: state.events.map((event) => event.sequence),
  cursor: state.lastSequence,
  reconnectUrl: panel.streamUrlWithCursor('/events?follow=1', state.lastSequence),
  lifecycleLabels: ['IDLE', 'CHECKING_FOR_WORK', 'NO_REQUEST_DETECTED', 'REQUEST_DETECTED', 'DISPATCHING', 'RUNNING', 'BLOCKED_OR_FAILED', 'WAITING_FOR_CHATGPT_REVIEW', 'COMPLETED_OR_LAST_COMPLETED', 'EXPIRED', 'UNKNOWN'].map(panel.lifecycleLabel),
  knownLabel: panel.eventLabel('process.completed'),
  unknownLabel: panel.eventLabel('future.kind'),
  ages: [panel.relativeAge(3), panel.relativeAge(18), panel.relativeAge(120)],
  relativeTimes: [
    panel.relativeTimeFrom('2026-09-06T12:08:12Z', Date.parse('2026-09-06T12:08:30Z')),
    panel.relativeTimeFrom('2026-09-06T12:18:30Z', Date.parse('2026-09-06T12:08:30Z')),
  ],
  cadence: panel.cadenceLabel(30),
}));
"""
    completed = subprocess.run(
        ["node", "-e", node_script, str(script_path)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    result = json.loads(completed.stdout)
    assert result == {
        "firstAccepted": True,
        "duplicateAccepted": False,
        "reorderedAccepted": False,
        "sequences": [11, 12],
        "cursor": 12,
        "reconnectUrl": "/events?follow=1&after=12",
        "lifecycleLabels": [
            "No request detected",
            "Checking for work",
            "No request detected",
            "Request detected / waiting for pickup",
            "Dispatching",
            "Running",
            "Blocked / failed",
            "Waiting for ChatGPT review",
            "Completed / last completed",
            "Expired",
            "Unknown",
        ],
        "knownLabel": "Codex process exited (activity only)",
        "unknownLabel": "Observed structured activity",
        "ages": ["just now", "18 seconds ago", "2 minutes ago"],
        "relativeTimes": ["18 seconds ago", "in 10 minutes"],
        "cadence": "Checks for work about every 30 seconds",
    }


def test_real_sse_replay_and_follow_delivers_new_request_without_rebinding(tmp_path):
    state_dir = (tmp_path / "state").resolve()
    state_dir.mkdir()
    store_path = (tmp_path / "events.jsonl").resolve()
    first = add_event(
        store_path,
        {"type": "turn.started"},
        observed_at="2026-09-06T12:08:20Z",
    )
    server, thread = start_panel(state_dir, store_path)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    response = None
    try:
        response = urlopen(f"{base}/events?after=0&follow=1", timeout=3)
        replay = read_sse_data_frame(response)
        assert replay["sequence"] == first["sequence"]
        assert replay["request_id"] == REQUEST_ID

        new_request_id = "workflow-panel-new-request-308"
        second = add_event(
            store_path,
            {"type": "thread.started", "thread_id": "safe-thread-id"},
            observed_at="2026-09-06T12:08:21Z",
            request_id=new_request_id,
            run_id="workflow-panel-new-run-308",
        )
        followed = read_sse_data_frame(response)
        assert followed["sequence"] == second["sequence"]
        assert followed["request_id"] == new_request_id

        payload = in_flight_payload()
        payload["request_id"] = new_request_id
        payload["dispatch_request_id"] = "workflow-panel-new-dispatch-308"
        write_json(state_dir / "in_flight.json", payload)
        with urlopen(f"{base}/api/state", timeout=2) as snapshot_response:
            snapshot = json.loads(snapshot_response.read())
        assert snapshot["current_task"]["request_id"] == new_request_id
        assert snapshot["current_task"]["lifecycle"]["stage"] == "DISPATCHING"
        assert snapshot["observability"]["stream_url"] == "/events?follow=1"
    finally:
        if response is not None:
            response.close()
        stop_panel(server, thread)


def test_panel_rejects_non_loopback_relative_paths_and_missing_assets(tmp_path):
    state_dir = (tmp_path / "state").resolve()
    store_path = (tmp_path / "events.jsonl").resolve()
    with pytest.raises(ObservationError, match="panel_host_must_be_ipv4_loopback"):
        create_workflow_panel_server(state_dir, store_path, host="0.0.0.0")
    with pytest.raises(ObservationError, match="panel_state_dir_must_be_absolute"):
        create_workflow_panel_server("relative-state", store_path)
    with pytest.raises(ObservationError, match="panel_assets_missing"):
        create_workflow_panel_server(
            state_dir,
            store_path,
            asset_dir=(tmp_path / "missing-assets").resolve(),
        )


def test_launcher_is_foreground_loopback_only_and_does_not_invoke_workflow_authority():
    script = (ROOT / "scripts" / "start_workflow_panel.ps1").read_text(encoding="utf-8")

    assert '"-m", "local_runner_bridge.workflow_panel"' in script
    assert '"--host", "127.0.0.1"' in script
    assert '"observability\\events.jsonl"' in script
    assert '"--lifetime-seconds"' in script
    assert "$LifetimeSeconds -gt 0" in script
    assert "Start-Process" not in script
    assert "local_runner.ps1" not in script
    assert "local_runner_v1.ps1" not in script
    assert "start_bridge_operator_b3c.ps1" not in script


def test_cli_panel_stops_itself_after_bounded_lifetime(tmp_path):
    state_dir = (tmp_path / "state").resolve()
    store_path = (tmp_path / "events.jsonl").resolve()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "local_runner_bridge.workflow_panel",
            "--state-dir",
            str(state_dir),
            "--store",
            str(store_path),
            "--host",
            "127.0.0.1",
            "--port",
            "0",
            "--lifetime-seconds",
            "0.1",
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=5,
        check=False,
    )

    assert result.returncode == 0
    ready = json.loads(result.stdout.strip())
    assert ready["protocol"] == PANEL_PROTOCOL
    assert ready["status"] == "ready"

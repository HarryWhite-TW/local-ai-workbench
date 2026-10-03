"""Real Store -> Panel -> Shell boundaries; no runner or remote work is invoked."""
import copy
import json
from datetime import timedelta
from urllib.request import Request, urlopen

import pytest

import test_workflow_panel as base
from sanctuary_cases import make_case
from local_runner_bridge.sanctuary_projection import project_sanctuary
from local_runner_bridge.workflow_observability import execution_started_event


def record(kind="codex.command.started", *, request=base.REQUEST_ID, run=base.RUN_ID):
    value = execution_started_event(request_id=request, run_id=run, process_id=1234,
                                    observed_at_utc="2026-09-06T12:08:29Z")
    if kind != "execution.started":
        value.update(kind=kind, source="runner" if kind == "process.completed" else "codex_exec_jsonl",
                     payload={"item_id": "command-001", "command_name": "pytest", "status": "in_progress"})
    return value


def write_events(path, events):
    path.write_text("".join(json.dumps({**event, "sequence": n})+"\n"
                            for n, event in enumerate(events, 1)), encoding="utf-8")
    return base.EventStore(path)


def running_state(path):
    base.write_json(path / "state.json", base.operator_state(last_request_id=base.REQUEST_ID))
    base.write_json(path / "heartbeat.json", base.operator_heartbeat())
    base.write_json(path / "in_flight.json", base.updated_in_flight_payload(
        base.in_flight_payload(), stage=base.DISPATCHED_NOT_LOCALLY_SETTLED,
        dispatcher_invoked=True, terminal_evidence=None, updated_at=base.NOW,
        dispatcher_process_identity={"platform": "windows", "pid": 4321,
            "start_token": "windows-filetime:12345679", "started_at_utc": "2026-09-06T12:08:05Z"}))


@pytest.mark.parametrize("history", [1001, 2049, 10000])
def test_current_run_survives_large_interleaved_history_and_late_old_run(tmp_path, history):
    running_state(tmp_path)
    foreign = record(request="foreign-request-001", run="foreign-run-001")
    old_start = record("execution.started", run="old-run-001")
    start = record("execution.started")
    events = [foreign]*history + [old_start, record("process.completed", run="old-run-001"), start,
             record(), *([foreign]*2100), record("codex.file.completed", run="old-run-001")]
    store = write_events(tmp_path / "events.jsonl", events)
    observed = []
    snapshot = base.build_workflow_snapshot(tmp_path, store, now=base.NOW, events_out=observed)
    assert snapshot["observability"]["run_id"] == base.RUN_ID
    assert snapshot["observability"]["latest_sequence"] == len(events)
    assert snapshot["observability"]["request_event_count"] == 2
    assert {e["run_id"] for e in observed} == {base.RUN_ID}
    world = project_sanctuary(snapshot, observed, now=base.NOW)
    assert world["identity"] == {"request_id": base.REQUEST_ID, "run_id": base.RUN_ID}
    assert world["activity"] == "test"
    assert world["semantic_motion"]
    assert store.read(limit=1000)[0][-1]["sequence"] == 1000
    assert store.read(after_sequence=history, limit=2)[0][0]["sequence"] == history+1


def test_completion_outside_retained_tail_cannot_resurrect_activity(tmp_path):
    running_state(tmp_path)
    store = write_events(tmp_path / "events.jsonl", [record("execution.started"),
                         record("process.completed"), *([record()]*1100)])
    events = []
    snapshot = base.build_workflow_snapshot(tmp_path, store, now=base.NOW, events_out=events)
    assert len(events) == 1000
    assert not any(e["kind"] == "process.completed" for e in events)
    assert snapshot["observability"]["run_completed"]
    assert not project_sanctuary(snapshot, events, now=base.NOW)["semantic_motion"]


def test_multiple_runs_without_start_are_unknown_and_retired_start_cannot_return(tmp_path):
    path = tmp_path / "events.jsonl"
    store = write_events(path, [record(), record(run="other-run-001")])
    window = store.read_current(base.REQUEST_ID)
    assert window["run_id"] is None and not window["events"]
    assert "current_run_identity_ambiguous" in window["diagnostics"]
    store = write_events(path, [record("execution.started"), record(run="unexplained-run-001")])
    assert store.read_current(base.REQUEST_ID)["run_id"] is None
    store = write_events(path, [record("execution.started", run="old-run-001"),
        record("execution.started"), record(), record("execution.started", run="old-run-001")])
    assert store.read_current(base.REQUEST_ID)["run_id"] == base.RUN_ID
    assert "retired_run_restart_ignored" in store.read_current(base.REQUEST_ID)["diagnostics"]


def test_retired_run_older_late_start_preserves_current_run(tmp_path):
    old_start = record("execution.started", run="old-run-001")
    old_start["observed_at_utc"] = (base.NOW-timedelta(seconds=20)).isoformat()
    current_start = record("execution.started")
    current_start["observed_at_utc"] = (base.NOW-timedelta(seconds=10)).isoformat()
    delayed_old_start = copy.deepcopy(old_start)
    store = write_events(tmp_path / "events.jsonl", [
        old_start, current_start, record(), delayed_old_start,
    ])

    window = store.read_current(base.REQUEST_ID)

    assert window["run_id"] == base.RUN_ID
    assert [event["sequence"] for event in window["events"]] == [2, 3]
    assert "retired_run_restart_ignored" in window["diagnostics"]
    assert "run_start_time_ambiguous" not in window["diagnostics"]
    assert "current_run_identity_ambiguous" not in window["diagnostics"]


def test_source_truncation_and_malformed_or_duplicate_records_fail_closed(tmp_path):
    running_state(tmp_path)
    path = tmp_path / "events.jsonl"
    store = write_events(path, [record("execution.started"), record()])
    initial = store.read_current(base.REQUEST_ID)
    path.write_text("", encoding="utf-8")
    empty = store.read_current(base.REQUEST_ID)
    assert empty["source_id"] != initial["source_id"] and empty["run_id"] is None
    store = write_events(path, [record()])  # A truncated fragment is not a new start.
    events = []
    snapshot = base.build_workflow_snapshot(tmp_path, store, now=base.NOW, events_out=events)
    assert project_sanctuary(snapshot, events, now=base.NOW)["reasons"] == ["run_start_not_observed"]
    store = write_events(path, [record("execution.started"), record()])
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({**record(), "sequence": 2})+"\n{broken\n")
    events = []
    snapshot = base.build_workflow_snapshot(tmp_path, store, now=base.NOW, events_out=events)
    assert not project_sanctuary(snapshot, events, now=base.NOW)["semantic_motion"]
    assert "observation_store:non_monotonic_record_ignored" in snapshot["diagnostics"]


def test_late_historical_start_cannot_reidentify_current_run(tmp_path):
    late = record("execution.started", run="late-old-run-001")
    late["observed_at_utc"] = "2026-09-06T12:08:01Z"
    store = write_events(tmp_path / "events.jsonl", [record("execution.started"), record(), late])
    window = store.read_current(base.REQUEST_ID)
    assert window["run_id"] is None
    assert "run_start_time_ambiguous" in window["diagnostics"]


@pytest.mark.parametrize("fraction", ["1", "113", "1130816"])
def test_windows_runner_fractional_timestamps_keep_real_run_visible(tmp_path, fraction):
    running_state(tmp_path)
    start = record("execution.started")
    start["observed_at_utc"] = f"2026-09-06T12:08:28.{fraction}+00:00"
    path = tmp_path / "events.jsonl"
    store = write_events(path, [start, record()])
    events = []
    snapshot = base.build_workflow_snapshot(tmp_path, store, now=base.NOW, events_out=events)
    assert snapshot["observability"]["run_id"] == base.RUN_ID
    assert project_sanctuary(snapshot, events, now=base.NOW)["semantic_motion"]
    completed = record("process.completed")
    completed["observed_at_utc"] = f"2026-09-06T12:08:29.{fraction}+00:00"
    store = write_events(path, [start, record(), completed])
    events = []
    snapshot = base.build_workflow_snapshot(tmp_path, store, now=base.NOW, events_out=events)
    assert project_sanctuary(snapshot, events, now=base.NOW)["pose"] == "settled"


@pytest.mark.parametrize("observed_at_utc", [
    "0001-01-01T00:00:00+23:59",
    "9999-12-31T23:59:59-23:59",
])
def test_out_of_range_runner_start_time_degrades_to_ambiguous(tmp_path, observed_at_utc):
    start = record("execution.started")
    start["observed_at_utc"] = observed_at_utc
    store = write_events(tmp_path / "events.jsonl", [start])

    window = store.read_current(base.REQUEST_ID)

    assert window["run_id"] is None
    assert window["events"] == []
    assert "run_start_time_ambiguous" in window["diagnostics"]
    assert "current_run_identity_ambiguous" in window["diagnostics"]


def test_failed_overlapping_command_closes_only_that_command(tmp_path):
    running_state(tmp_path)
    start = record("execution.started")
    start["observed_at_utc"] = (base.NOW-timedelta(seconds=4)).isoformat()
    command_a = record()
    command_a["observed_at_utc"] = (base.NOW-timedelta(seconds=3)).isoformat()
    command_a["payload"].update(item_id="command-a", command_name="git")
    command_b = record()
    command_b["observed_at_utc"] = (base.NOW-timedelta(seconds=2)).isoformat()
    command_b["payload"].update(item_id="command-b", command_name="python")
    failed_b = record("codex.command.failed")
    failed_b["observed_at_utc"] = (base.NOW-timedelta(seconds=1)).isoformat()
    failed_b["payload"].update(item_id="command-b", command_name="python", status="failed")
    store = write_events(tmp_path / "events.jsonl", [start, command_a, command_b, failed_b])
    events = []
    snapshot = base.build_workflow_snapshot(tmp_path, store, now=base.NOW, events_out=events)

    world = project_sanctuary(snapshot, events, now=base.NOW)

    assert world["pose"] == "working"
    assert world["activity"] == "command"
    assert world["actor"] == "builder"
    assert world["semantic_motion"] is True


def test_shell_single_read_and_panel_identity_match_and_sse_reconnect(tmp_path, monkeypatch):
    running_state(tmp_path)
    path = tmp_path / "events.jsonl"
    write_events(path, [record(request="old-request-001")]*2050+[record("execution.started"), record()])
    calls = []
    original = base.EventStore.read_current
    def counted(self, request_id):
        calls.append(request_id)
        return original(self, request_id)
    monkeypatch.setattr(base.EventStore, "read_current", counted)
    server, thread = base.start_panel(tmp_path, path)
    origin = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(origin+"/api/sanctuary") as response:
            shell = json.load(response)
        assert calls == [base.REQUEST_ID]
        with urlopen(origin+"/api/snapshot") as response:
            panel = json.load(response)
        assert panel["observability"] == shell["snapshot"]["observability"]
        assert shell["world"]["identity"]["run_id"] == base.RUN_ID
        assert [e["sequence"] for e in shell["events"]] == [2051, 2052]
        with urlopen(Request(origin+"/events?follow=0", headers={"Last-Event-ID": "2051"})) as response:
            body = response.read().decode()
        resumed = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]
        assert [e["sequence"] for e in resumed] == [2052]
        with urlopen(origin+"/api/sanctuary") as response:
            refreshed = json.load(response)
        assert refreshed["delivery"]["session"] == shell["delivery"]["session"]
        assert refreshed["delivery"]["sequence"] > shell["delivery"]["sequence"]
        path.write_text("", encoding="utf-8")
        with urlopen(origin+"/api/sanctuary") as response:
            reset = json.load(response)
        assert reset["snapshot"]["observability"]["source_id"] != shell["snapshot"]["observability"]["source_id"]
        assert reset["world"]["identity"]["run_id"] is None and not reset["events"]
        assert not reset["world"]["semantic_motion"]
        write_events(path, [record("execution.started"), record()])
        with urlopen(Request(origin+"/events?follow=0", headers={"Last-Event-ID": "2051"})) as response:
            assert "data: " not in response.read().decode()
        with urlopen(origin+"/events?follow=0&after=0") as response:
            assert response.read().decode().count("data: ") == 2
    finally:
        base.stop_panel(server, thread)


@pytest.mark.parametrize("name,kind", [("technical-repair", "TECHNICAL_ACTION"),
    ("waiting-review", "CHATGPT_REVIEW"), ("execution", "SYSTEM"), ("unknown", "UNKNOWN")])
def test_next_owner_is_evidence_based_and_fake_human_proposals_are_ignored(name, kind):
    case = make_case(name)
    snapshot = copy.deepcopy(case["snapshot"])
    snapshot["human_decision"] = {"trusted": True, "operation": "approve", "scope": "everything"}
    world = project_sanctuary(snapshot, case["events"], now=base.NOW)
    assert world["human"]["kind"] == kind
    assert not world["human"]["attention"]
    assert world["human"]["proposal_status"] == "unavailable"
    assert world["human"]["write_enabled"] is False


@pytest.mark.parametrize("stage,verdict", [("REPAIR_REQUIRED", "repair_required"),
                                        ("FINAL_REVIEW_BLOCKED", "blocked")])
def test_verified_repair_and_blocked_review_both_remain_technical(stage, verdict):
    case = make_case("technical-repair")
    case["snapshot"]["current_task"]["lifecycle"].update(
        stage=stage, basis=f"final_review_verdict:{verdict}")
    case["snapshot"]["review"]["final_verdict"]["verdict"] = verdict
    world = project_sanctuary(case["snapshot"], case["events"], now=base.NOW)
    assert world["human"]["kind"] == "TECHNICAL_ACTION"
    assert not world["human"]["attention"] and not world["semantic_motion"]

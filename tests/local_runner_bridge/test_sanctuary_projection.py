import copy
import json
from datetime import timedelta
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from sanctuary_cases import make_case
import test_workflow_panel as base
from local_runner_bridge.sanctuary_projection import project_sanctuary


@pytest.mark.parametrize("name,pose,station,activity",[
    ("offline","uncertain","core",None),("idle","idle","core",None),
    ("request","arriving","core",None),("execution","working","workshop","execution"),
    ("command","working","workshop","command"),("file","working","workshop","file"),
    ("tool","working","workshop","tool"),("test","working","test","test"),
    ("process-completed","settled","core",None),("waiting-review","review","review",None),
    ("technical-repair","attention","review",None),("accepted","accepted","review",None),
    ("blocked","blocked","core",None),("failed","settled","core",None),
    ("wrong-request","uncertain","core",None),("wrong-run","uncertain","core",None),
    ("stale","uncertain","core",None),("unknown","uncertain","core",None),
    ("candidate-mismatch","review","review",None),
])
def test_canonical_fixtures_map_to_bounded_world_poses(name,pose,station,activity):
    case=make_case(name)
    world=case["world"]
    assert (world["pose"],world["station"],world["activity"])==(pose,station,activity)
    assert world["source_lifecycle"]==case["snapshot"]["current_task"]["lifecycle"]["stage"]
    assert world["human"]["write_enabled"] is False
    assert world["actor"] in {None,"builder"}


def test_process_completion_and_waiting_review_do_not_become_acceptance_or_human_approval():
    completed=make_case("process-completed")
    assert completed["snapshot"]["current_task"]["lifecycle"]["stage"]=="RUNNING"
    assert completed["world"]["semantic_motion"] is False
    review=make_case("waiting-review")["world"]
    assert review["artifact"]=="candidate"
    assert review["human"]["attention"] is False
    assert "不是等待你批准" in review["human"]["what"]
    attention=make_case("technical-repair")
    assert attention["snapshot"]["current_task"]["lifecycle"]["stage"]=="REPAIR_REQUIRED"
    assert attention["world"]["human"]["attention"] is False
    assert attention["world"]["human"]["kind"] == "TECHNICAL_ACTION"
    assert attention["world"]["human"]["proposal_status"] == "unavailable"


@pytest.mark.parametrize("kind",["accepted_verdict", "snapshot_age", "future_snapshot", "mode", "source_diagnostic", "offline", "stale", "future_event", "duplicate", "event_time_reversal"])
def test_ambiguous_or_stale_evidence_fails_closed(kind):
    case=make_case("accepted" if kind=="accepted_verdict" else "test")
    s,e=case["snapshot"],case["events"]
    if kind=="accepted_verdict":s["review"]["final_verdict"]["verdict"]="blocked"
    elif kind=="snapshot_age":s["observed_at_utc"]=(base.NOW-timedelta(seconds=11)).isoformat()
    elif kind=="future_snapshot":s["observed_at_utc"]=(base.NOW+timedelta(seconds=3)).isoformat()
    elif kind=="mode":s["mode"]="writable"
    elif kind=="source_diagnostic":s["diagnostics"]=["in_flight_evidence_invalid"]
    elif kind in {"offline","stale"}:s["system"]["operator"]=kind
    elif kind=="future_event":e[-1]["observed_at_utc"]=(base.NOW+timedelta(seconds=1)).isoformat()
    elif kind=="duplicate":e.append({**e[-1],"kind":"codex.file.started"})
    elif kind=="event_time_reversal":e[-1]["observed_at_utc"]=(base.NOW-timedelta(seconds=7)).isoformat()
    world=project_sanctuary(s,e,now=base.NOW)
    assert world["pose"]=="uncertain"
    assert not world["semantic_motion"]
    assert world["actor"] is None


def test_replay_duplicates_ordering_and_foreign_activity_cannot_restart_or_change_work():
    case=make_case("test")
    s,e=case["snapshot"],case["events"]
    original=copy.deepcopy(case)
    foreign={**e[-1],"request_id":"other-request-001","run_id":"other-run-001","sequence":999,"kind":"codex.file.started"}
    assert project_sanctuary(s,[foreign,*e,*e],now=base.NOW)==case["world"]
    assert project_sanctuary(s,list(reversed(e)),now=base.NOW)==case["world"]
    assert case==original  # The projection never mutates canonical snapshot or events.
    complete=make_case("process-completed")
    late={**complete["events"][0],"sequence":3,"observed_at_utc":base.NOW.isoformat()}
    complete["snapshot"]["observability"]["latest_sequence"]=3
    assert project_sanctuary(complete["snapshot"],[*complete["events"],late],now=base.NOW)["semantic_motion"] is False


@pytest.mark.parametrize("command",["python", "npm", "powershell.exe", "node", "uv", "go"])
def test_ambiguous_executable_does_not_fabricate_test_activity(command):
    case=make_case("test")
    case["events"][-1]["payload"]["command_name"]=command
    case["events"][-1]["payload"].pop("activity_kind", None)
    case["events"][-1]["payload"].pop("test_framework", None)
    world=project_sanctuary(case["snapshot"],case["events"],now=base.NOW)
    assert world["activity"]=="command"
    assert world["station"]=="workshop"


def test_completed_test_settles_scanner_without_claiming_tests_passed():
    case=make_case("test")
    e=case["events"][-1]
    done={**e,"sequence":3,"kind":"codex.command.completed","observed_at_utc":(base.NOW-timedelta(seconds=1)).isoformat(),"payload":{**e["payload"],"status":"completed","exit_code":0}}
    case["snapshot"]["observability"]["latest_sequence"]=3
    world=project_sanctuary(case["snapshot"],[*case["events"],done],now=base.NOW)
    assert world["activity"]!="test"
    assert world["pose"]!="accepted"
    assert not world["semantic_motion"]
    assert world["station"] == "test"


def test_structured_wrapper_semantics_do_not_require_raw_arguments():
    case = make_case("test")
    case["events"][-1]["payload"]["command_name"] = "pwsh.exe"
    world = project_sanctuary(case["snapshot"], case["events"], now=base.NOW)
    assert world["activity"] == "test" and world["station"] == "test"


def test_explicit_unknown_test_semantics_cannot_fall_back_to_executable_hint():
    case = make_case("test")
    case["events"][-1]["payload"].update(activity_kind="command")
    case["events"][-1]["payload"].pop("test_framework")
    world = project_sanctuary(case["snapshot"], case["events"], now=base.NOW)
    assert world["activity"] == "command" and world["station"] == "workshop"


@pytest.mark.parametrize("framework", [None, [], {}, "arbitrary pytest text"])
def test_unknown_structured_framework_does_not_fabricate_test(framework):
    case = make_case("test")
    case["events"][-1]["payload"].update(command_name="pwsh.exe", test_framework=framework)
    world = project_sanctuary(case["snapshot"], case["events"], now=base.NOW)
    assert world["activity"] == "command"


@pytest.mark.parametrize("name", ["short-test-completed", "short-test-failed", "short-test-review"])
def test_completed_wrapped_test_is_replayable_without_active_sampling(name):
    case = make_case(name)
    test_events = [e for e in case["events"] if e["payload"].get("activity_kind") == "test"]
    assert len(test_events) == 2
    assert test_events[-1]["payload"]["test_framework"] == "pytest"
    assert test_events[-1]["payload"]["exit_code"] == (1 if name == "short-test-failed" else 0)
    assert not case["world"]["semantic_motion"]
    assert case["world"]["activity"] != "test"
    assert not case["world"]["human"]["attention"]
    if name == "short-test-review":
        assert case["world"]["station"] == "review"
        assert case["world"]["human"]["kind"] == "CHATGPT_REVIEW"


@pytest.mark.parametrize("field,value",[("command_name",None),("command_name",42),("item_id",[]),("item_id",None),("item_id","")])
def test_malformed_command_payload_fails_closed_without_crashing(field,value):
    case=make_case("test")
    case["events"][-1]["payload"][field]=value
    world=project_sanctuary(case["snapshot"],case["events"],now=base.NOW)
    assert world["pose"]=="uncertain"
    assert world["reasons"]==["command_evidence_invalid"]


def test_durable_accepted_result_survives_operator_offline_as_static_evidence():
    case=make_case("accepted")
    case["snapshot"]["system"]["operator"]="offline"
    world=project_sanctuary(case["snapshot"],case["events"],now=base.NOW)
    assert world["pose"]=="accepted"
    assert not world["semantic_motion"]


@pytest.mark.parametrize("kind",["source", "interface", "unknown_kind", "second_read_diagnostic", "codex_error"])
def test_activity_requires_known_adapter_and_stops_on_error(kind):
    case=make_case("test")
    if kind=="source":case["events"][-1]["source"]="unknown_adapter"
    elif kind=="interface":case["events"][0]["payload"]["interface"]="unknown_runner"
    elif kind=="unknown_kind":case["events"][-1]["kind"]="codex.command.unknown"
    elif kind=="codex_error":case["events"][-1]["kind"]="codex.error"
    world=project_sanctuary(case["snapshot"],case["events"],now=base.NOW,
                            observation_diagnostics=["invalid_record_ignored"] if kind=="second_read_diagnostic" else [])
    assert world["pose"]==("settled" if kind=="codex_error" else "uncertain")
    assert not world["semantic_motion"]


def test_shell_http_reuses_snapshot_preserves_csp_and_rejects_all_writes(tmp_path):
    state=(tmp_path / "state").resolve();state.mkdir()
    store=(tmp_path / "events.jsonl").resolve()
    before=list(tmp_path.rglob("*"))
    server,thread=base.start_panel(state,store)
    origin=f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(origin+"/api/sanctuary") as response:
            envelope=json.load(response)
            assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
        with urlopen(origin+"/api/state") as response:canonical=json.load(response)
        envelope["snapshot"].pop("observed_at_utc");canonical.pop("observed_at_utc")
        assert envelope["snapshot"]==canonical
        for asset in ["/sanctuary","/sanctuary.css","/sanctuary.js","/sanctuary_world.js","/"]:
            with urlopen(origin+asset) as response:assert response.status==200
        for method in ["POST","PUT","PATCH","DELETE"]:
            with pytest.raises(HTTPError) as caught:urlopen(Request(origin+"/api/sanctuary",data=b"{}",method=method))
            assert caught.value.code==405
        assert list(tmp_path.rglob("*"))==before
    finally:base.stop_panel(server,thread)

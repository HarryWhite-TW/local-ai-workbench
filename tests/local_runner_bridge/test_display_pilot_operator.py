import json,sys
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"src"))
from local_runner_bridge.display_pilot_operator import run_foreground
from local_runner_bridge.display_pilot_transport import *
def fixture():
 body=json.dumps({"protocol":"lawb.local_runner.task_packet.v1.1","packet_id":"p","logical_issue":9,"repository":TARGET_REPOSITORY,"task_mode":"PATCH_ONLY","verification_command_policy":"explicit_only","verification_commands":["python -m pytest -q tests/x.py"]})
 sel={"protocol":PROTOCOL,"repository":SELECTOR_REPOSITORY,"issue":1,"target_repository":TARGET_REPOSITORY,"target_issue":9,"action":"run-reviewbundle","request_id":"req-9","target_body_sha256":body_sha256(body)}; raw="```json hgw.display_pilot.transport.v1\n"+json.dumps(sel)+"\n```";return {"body":raw,"creator":"HarryWhite-TW","body_sha256":body_sha256(raw)},{"repository":TARGET_REPOSITORY,"number":9,"creator":"HarryWhite-TW","state":"open","body":body}
def run(tmp,**over):
 s,t=fixture(); calls=[]; args=dict(state_root=tmp,selector_issue=s,target_reader=lambda n:t,runner=lambda p:calls.append(p) or {"result":"success","changed_files":[]},verifier=lambda c:{"returncode":0},hgw_renderer=lambda e,i,a:{"result":"success","result_surface":{},"reviewer_report":"review","plain_language_zh_TW":"plain"},python_path="python",now=lambda:datetime(2026,1,1,tzinfo=timezone.utc),sleep=lambda _:None);args.update(over);return run_foreground(**args),calls
def test_one_accepted_task_exactly_once(tmp_path): r,c=run(tmp_path);assert r["result"]=="success" and len(c)==1
def test_max_task_exit(tmp_path): assert run(tmp_path)[0]["cycles"]==1
def test_lock(tmp_path): (tmp_path/"operator.lock").write_text("x");assert run(tmp_path)[0]["blocked_reasons"]==["active_lock_present"]
def test_pause(tmp_path): (tmp_path/"pause.flag").write_text("x");assert run(tmp_path)[0]["blocked_reasons"]==["pause_flag_present"]
def test_stop(tmp_path): (tmp_path/"stop.flag").write_text("x");assert run(tmp_path)[0]["blocked_reasons"]==["stop_flag_present"]
def test_uncertain_restart_blocks(tmp_path): (tmp_path/"uncertain_restart.json").write_text("{}");assert run(tmp_path)[0]["blocked_reasons"]==["uncertain_restart_state"]
def test_transport_block_before_runner(tmp_path): s,_=fixture();s["creator"]="bad";r,c=run(tmp_path,selector_issue=s);assert not c and r["result"]=="blocked"
def test_runner_failure(tmp_path): r,c=run(tmp_path,runner=lambda p:{"result":"failure"});assert r["blocked_reasons"]==["runner_failed"]
def test_verification_failure(tmp_path): r,c=run(tmp_path,verifier=lambda c:{"returncode":1});assert r["blocked_reasons"]==["verification_failed"]
def test_result_generation_from_evidence(tmp_path): r,c=run(tmp_path);assert (tmp_path/"req-9"/"result_surface.json").exists()
def test_exactly_one_comment_candidate(tmp_path): assert run(tmp_path)[0]["result_comment_candidate_count"]==1
def test_forbidden_flags_false(tmp_path): r,c=run(tmp_path);assert all(r[x] is False for x in ("github_write_performed","commit_performed","push_performed","issue_closed","label_changed","pr_created","merge_performed"))

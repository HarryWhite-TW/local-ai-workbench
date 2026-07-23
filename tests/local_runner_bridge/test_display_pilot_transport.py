import hashlib, json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"src"))
from local_runner_bridge.display_pilot_transport import *
def selector(**x):
 d={"protocol":PROTOCOL,"repository":SELECTOR_REPOSITORY,"issue":1,"target_repository":TARGET_REPOSITORY,"target_issue":9,"action":"run-reviewbundle","request_id":"req-9","target_body_sha256":"a"*64};d.update(x); return "```json hgw.display_pilot.transport.v1\n"+json.dumps(d)+"\n```"
def call(body,creator="HarryWhite-TW",sha=None): return parse_selector(body=body,creator=creator,expected_body_sha256=sha or body_sha256(body))
def test_valid_strict_selector(): assert call(selector())["result"]=="success"
def test_malformed_json(): assert call("```json hgw.display_pilot.transport.v1\n{\n```")["reason"]=="selector_machine_payload_malformed"
def test_ambiguous_fence(): assert call(selector()+"\n"+selector())["reason"]=="selector_machine_payload_ambiguous_or_missing"
def test_creator_mismatch(): assert call(selector(),"other")["reason"]=="untrusted_selector_creator"
def test_selector_hash_mismatch(): assert call(selector(),sha="0"*64)["reason"]=="selector_body_hash_mismatch"
def test_target_hash_mismatch():
 s=call(selector())["selector"]; assert validate_target(selector=s,issue={"repository":TARGET_REPOSITORY,"number":9,"creator":"HarryWhite-TW","state":"open","body":"{}"})["reason"]=="target_body_hash_mismatch"
def test_wrong_repository_action_and_mode(): assert call(selector(action="other"))["reason"]=="selector_identity_or_action_mismatch"
def test_unknown_field_or_identity(): assert call(selector(extra=True))["reason"]=="selector_unknown_or_missing_field"

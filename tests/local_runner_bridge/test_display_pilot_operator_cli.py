import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"src"))
from local_runner_bridge import display_pilot_operator_cli as cli
def test_invalid_arguments_produce_blocked_json(tmp_path,capsys): assert cli.main([])==2 and json.loads(capsys.readouterr().out)["result"]=="blocked"
def test_setup_idempotence(tmp_path,capsys): assert cli.main(["setup","--state-root",str(tmp_path),"--hgw-root",str(tmp_path)])==0 and cli.main(["setup","--state-root",str(tmp_path),"--hgw-root",str(tmp_path)])==0
def test_verify_no_write_behavior(tmp_path,monkeypatch,capsys):
 state_path=tmp_path/"verify-state"
 assert not state_path.exists()
 monkeypatch.setattr(cli,"verify_hgw_checkout",lambda x:{"result":"success"})
 assert cli.main(["verify","--state-root",str(state_path),"--hgw-root",str(tmp_path)])==0
 output=json.loads(capsys.readouterr().out)
 assert output["result"]=="success"
 assert output["github_write_performed"] is False
 assert output["runner_invoked"] is False
 assert not state_path.exists()
def test_start_routes_to_bounded_block(tmp_path,capsys): assert cli.main(["start","--state-root",str(tmp_path),"--hgw-root",str(tmp_path)])==2
def test_secret_not_printed(tmp_path,monkeypatch,capsys): monkeypatch.setattr(cli,"verify_hgw_checkout",lambda x:{"result":"blocked","reason":"blocked"});cli.main(["verify","--state-root",str(tmp_path),"--hgw-root","secret-value"]);assert "secret-value" not in capsys.readouterr().out
def test_powershell_wrapper_propagates_failure(): assert "exit $LASTEXITCODE" in Path("scripts/display_pilot.ps1").read_text()

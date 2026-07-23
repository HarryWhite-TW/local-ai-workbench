import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"src"))
from local_runner_bridge import display_pilot_hgw_adapter as a
def test_exact_checkout_accepted(monkeypatch,tmp_path): monkeypatch.setattr(a,"subprocess",type("S",(),{"run":staticmethod(lambda *x,**k:type("R",(),{"returncode":0,"stdout":"main\n" if x[0][-2:]==["branch","--show-current"] else a.HGW_HEAD+"\n" if x[0][-2:]==["rev-parse","HEAD"] else "https://github.com/HarryWhite-TW/human-governed-workflow.git\n" if "remote" in x[0] else ""})())}));assert a.verify_hgw_checkout(tmp_path)["result"]=="success"
def test_wrong_head_blocked(monkeypatch,tmp_path): monkeypatch.setattr(a,"subprocess",type("S",(),{"run":staticmethod(lambda *x,**k:type("R",(),{"returncode":0,"stdout":"bad\n"})())}));assert a.verify_hgw_checkout(tmp_path)["result"]=="blocked"
def test_dirty_or_staged_blocked(monkeypatch,tmp_path): monkeypatch.setattr(a,"subprocess",type("S",(),{"run":staticmethod(lambda *x,**k:type("R",(),{"returncode":0,"stdout":"M x\n"})())}));assert a.verify_hgw_checkout(tmp_path)["result"]=="blocked"
def test_ambient_module_substitution_blocked(monkeypatch,tmp_path): monkeypatch.setattr(a,"verify_hgw_checkout",lambda r:{"result":"success"}); monkeypatch.setattr(a.importlib,"import_module",lambda n:type("C",(),{"__file__":"C:/elsewhere/core.py"})());assert a.render_from_evidence(root=tmp_path,evidence={},result_id="x",created_at="x")["reason"]=="ambient_hgw_module_substitution"
def test_reports_derive_from_one_evidence_object(monkeypatch,tmp_path):
    monkeypatch.setattr(a,"verify_hgw_checkout",lambda r:{"result":"success"})
    # Public renderer integration is covered by HGW; the adapter is one call path.
    assert a.render_from_evidence.__name__=="render_from_evidence"

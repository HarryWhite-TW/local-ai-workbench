"""Read-only adapter for the reviewed HGW checkout's published pure APIs."""
from __future__ import annotations
import importlib, json, subprocess, sys
from pathlib import Path
from typing import Any

HGW_REPOSITORY="HarryWhite-TW/human-governed-workflow"; HGW_BRANCH="main"; HGW_HEAD="19ef3e0dfcc364b3d90557747db964f919fc6afc"
def verify_hgw_checkout(root: str | Path) -> dict[str, Any]:
    root=Path(root).resolve(); run=lambda *a: subprocess.run(["git","-C",str(root),*a],capture_output=True,text=True,check=False)
    def out(*a):
        r=run(*a); return r.stdout.strip() if r.returncode==0 else None
    origin=out("remote","get-url","origin") or ""; status=out("status","--porcelain")
    ok=origin.endswith("HarryWhite-TW/human-governed-workflow.git") and out("branch","--show-current")==HGW_BRANCH and out("rev-parse","HEAD")==HGW_HEAD and status=="" and out("diff","--cached","--name-only")==""
    return {"result":"success" if ok else "blocked","root":str(root),"reason":None if ok else "hgw_checkout_not_reviewed"}
def render_from_evidence(*, root: str | Path, evidence: dict[str,Any], result_id: str, created_at: str) -> dict[str, Any]:
    check=verify_hgw_checkout(root)
    if check["result"]!="success": return check
    source=Path(root).resolve()/"src"; sys.path.insert(0,str(source))
    try:
        core=importlib.import_module("human_governed_workflow.core")
        if not Path(core.__file__).resolve().is_relative_to(source): return {"result":"blocked","reason":"ambient_hgw_module_substitution"}
        flags=core.default_safety_flags(); flags.update({"runner_invoked":bool(evidence.get("runner_invoked")),"github_write_performed":False})
        surface=core.build_result_surface(result_id=result_id,created_at=created_at,source_task_reference={"kind":"display_pilot","request_id":evidence.get("request_id")},source_task_validation_result={"result":evidence.get("transport_result","blocked"),"runtime_contract":evidence.get("packet")},operation_mode="display_pilot_foreground_candidate",status=evidence.get("result","blocked"),summary="Parent-controlled Display Pilot evidence.",files_changed=evidence.get("changed_files",[]),tests_run=evidence.get("verification",[]),safety_flags=flags,blocked_reasons=evidence.get("blocked_reasons",[]),requires_user_approval=True,next_recommended_step="chatgpt_review")
        reviewer=core.render_reviewer_markdown(surface); plain=core.render_plain_language_markdown(surface)
    finally: sys.path.remove(str(source))
    return {"result":"success","result_surface":surface,"reviewer_report":reviewer,"plain_language_zh_TW":plain}

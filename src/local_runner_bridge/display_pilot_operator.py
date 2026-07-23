"""Foreground-only, single-request Display Pilot candidate."""
from __future__ import annotations
import json, os, subprocess, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from .display_pilot_transport import parse_selector, validate_target

SUMMARY_PROTOCOL="hgw.display_pilot.operator.v1"
def validate_verification_command(command: str, repo_root: str | Path, python_path: str) -> list[str] | None:
    parts=command.split()
    if len(parts)<4 or parts[:3] != ["python","-m","pytest"] or any(x in command for x in "|;&><$") or any(".." in x or Path(x).is_absolute() for x in parts[3:]): return None
    return [python_path,"-m","pytest",*parts[3:]]
def run_foreground(*, state_root: str|Path, selector_issue: dict[str,Any], target_reader: Callable[[int],dict[str,Any]], runner: Callable[[dict[str,Any]],dict[str,Any]], verifier: Callable[[list[str]],dict[str,Any]], hgw_renderer: Callable[[dict[str,Any],str,str],dict[str,Any]], python_path: str, max_cycles:int=100, poll_interval_seconds:float=5, now:Callable[[],datetime]|None=None, sleep:Callable[[float],None]|None=None) -> dict[str,Any]:
    now=now or (lambda:datetime.now(timezone.utc)); sleep=sleep or time.sleep; root=Path(state_root); root.mkdir(parents=True,exist_ok=True)
    summary={"protocol":SUMMARY_PROTOCOL,"result":"blocked","blocked_reasons":[],"runner_invoked":False,"github_write_performed":False,"commit_performed":False,"push_performed":False,"issue_closed":False,"label_changed":False,"pr_created":False,"merge_performed":False,"broad_issue_scan_performed":False,"latest_next_inference_performed":False,"cycles":0}
    lock=root/"operator.lock"
    if lock.exists(): summary["blocked_reasons"]=["active_lock_present"]; return summary
    if (root/"uncertain_restart.json").exists(): summary["blocked_reasons"]=["uncertain_restart_state"]; return summary
    lock.write_text("active",encoding="utf-8")
    try:
      if (root/"pause.flag").exists(): summary["blocked_reasons"]=["pause_flag_present"]; return summary
      if (root/"stop.flag").exists(): summary["blocked_reasons"]=["stop_flag_present"]; return summary
      summary["cycles"]=1; (root/"heartbeat.json").write_text(json.dumps({"cycle":1,"at":now().isoformat()}),encoding="utf-8")
      sel=parse_selector(body=selector_issue["body"],creator=selector_issue["creator"],expected_body_sha256=selector_issue["body_sha256"])
      if sel["result"]!="success": summary["blocked_reasons"]=[sel["reason"]]; return summary
      target=target_reader(sel["selector"]["target_issue"]); validated=validate_target(selector=sel["selector"],issue=target)
      if validated["result"]!="success": summary["blocked_reasons"]=[validated["reason"]]; return summary
      packet=validated["packet"]; commands=[]
      for command in packet["verification_commands"]:
        parsed=validate_verification_command(command,".",python_path)
        if not parsed: summary["blocked_reasons"]=["verification_command_rejected"]; return summary
        commands.append(parsed)
      summary.update(request_id=sel["selector"]["request_id"],packet=packet,transport_result="success",runner_invoked=True)
      run=runner(packet)
      if run.get("result")!="success": summary["result"]="failure"; summary["blocked_reasons"]=["runner_failed"]; return summary
      verification=[verifier(command) for command in commands]; summary["verification"]=verification
      if any(v.get("returncode")!=0 for v in verification): summary["result"]="failure"; summary["blocked_reasons"]=["verification_failed"]; return summary
      summary["result"]="success"; summary["changed_files"]=run.get("changed_files",[])
      artifacts=hgw_renderer(summary,summary["request_id"],now().isoformat());
      if artifacts.get("result")!="success": summary["result"]="blocked"; summary["blocked_reasons"]=[artifacts.get("reason","hgw_render_failed")]; return summary
      request=root/summary["request_id"]; request.mkdir();
      for name,key in (("result_surface.json","result_surface"),("reviewer_report.md","reviewer_report"),("plain_language_zh_TW.md","plain_language_zh_TW")):
        value=artifacts[key]; (request/name).write_text(json.dumps(value,ensure_ascii=False,sort_keys=True) if isinstance(value,dict) else value,encoding="utf-8")
      (request/"result_comment_candidate.md").write_text(artifacts["reviewer_report"],encoding="utf-8"); (request/"operator_summary.json").write_text(json.dumps(summary,sort_keys=True),encoding="utf-8")
      summary["result_comment_candidate_count"]=1; return summary
    finally:
      lock.unlink(missing_ok=True)

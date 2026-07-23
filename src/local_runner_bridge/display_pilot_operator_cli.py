"""JSON-only command surface for the non-live Display Pilot candidate."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from .display_pilot_hgw_adapter import verify_hgw_checkout

def _summary(result, reasons=()): return {"protocol":"hgw.display_pilot.operator.v1","result":result,"blocked_reasons":list(reasons),"live_start_performed":False,"github_write_performed":False,"runner_invoked":False,"codex_invoked":False}
def main(argv=None):
 p=argparse.ArgumentParser(); p.add_argument("action",choices=("setup","verify","start")); p.add_argument("--state-root",required=True); p.add_argument("--hgw-root",required=True)
 try: a=p.parse_args(argv)
 except SystemExit: print(json.dumps(_summary("blocked",["invalid_arguments"]),sort_keys=True)); return 2
 root=Path(a.state_root)
 if a.action=="setup": root.mkdir(parents=True,exist_ok=True); (root/"artifacts").mkdir(exist_ok=True); print(json.dumps(_summary("success"),sort_keys=True)); return 0
 check=verify_hgw_checkout(a.hgw_root)
 if a.action=="start": print(json.dumps(_summary("blocked",["live_start_not_permitted_in_dp4_b"]),sort_keys=True)); return 2
 out=_summary(check["result"],[] if check["result"]=="success" else [check["reason"]]); out["hgw_checkout"]=check; print(json.dumps(out,sort_keys=True)); return 0 if out["result"]=="success" else 2
if __name__=="__main__": raise SystemExit(main())

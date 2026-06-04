# Local Text File Smoke Evidence (#148)

## 1. Purpose

#148 records local-only smoke evidence for the #146 explicit task surface fetch CLI using `--local-text-file`.

The goal is to prove the local path:

```text
local file -> CLI -> #145 helper -> validation dry-run -> JSON summary
```

No live GitHub fetch was performed. No GitHub token was used.

## 2. Issue Classification

```yaml
issue_number: 148
issue_role: support
risk_lane: standard
alignment: core_support
value_target: run the #146 local smoke CLI with a local task surface file and record stdout JSON evidence without live GitHub fetch, GitHub writeback, Result Packet write, runner, dispatcher, or broad issue scan
```

Manual copy/paste remains fallback only, not the target workflow.

## 3. Command That Was Run

A temporary local task surface file was created outside the repository at:

```text
$env:TEMP\lawb_task_surface_148.txt
```

The smoke command used `--local-text-file` only:

```powershell
$env:PYTHONPATH='src'
python -m local_runner_bridge.explicit_task_surface_fetch_cli --local-text-file $tempFile
```

No `--issue-url` or `--comment-url` option was used.

No GitHub token environment variable was used.

## 4. Input Surface Boundary

The temporary task surface contained one explicit read-only Task Packet.

The Task Packet allowed only this evidence document as the intended repository artifact:

```text
docs/LOCAL_TEXT_FILE_SMOKE_EVIDENCE_148.md
```

The Task Packet explicitly forbade live GitHub fetch, GitHub writeback, Result Packet write, Codex-side action execution, runner behavior, dispatcher behavior, broad issue scan, commit, and push.

The temporary task surface file was deleted after the smoke run and was not committed.

## 5. JSON Output Evidence

The CLI printed JSON to stdout.

Successful stdout JSON:

```json
{
  "bounded_read_performed": true,
  "broad_issue_scan_performed": false,
  "codex_side_action_executed": false,
  "commit_triggered": false,
  "drift_detected": false,
  "errors": [],
  "explicit_input_preserved": true,
  "github_write_performed": false,
  "issue_closed": false,
  "label_changed": false,
  "next_recommended_action": "chatgpt_review",
  "pr_triggered": false,
  "protocol": "lawb.local_runner.explicit_task_surface_fetch_summary.v1",
  "push_triggered": false,
  "reference_type": "local_text",
  "result": "success",
  "result_packet_written": false,
  "validation_summary": {
    "active_task_packet_count": 1,
    "codex_side_action_executed": false,
    "commit_performed": false,
    "errors": [],
    "github_write_performed": false,
    "logical_issue_matches_expected": true,
    "next_recommended_action": "chatgpt_review",
    "phase_matches_expected": true,
    "protocol": "lawb.local_runner.task_surface_validation_summary.v1",
    "push_performed": false,
    "repo_files_modified": false,
    "required_fields_present": true,
    "result": "success",
    "result_packet_written": false,
    "slice_name": "read_only_task_surface_resolver_and_packet_validator",
    "task_packet_boundary_markers_valid": true,
    "task_packet_protocol_valid": true,
    "task_surface_reference_checked": true
  }
}
```

The raw stdout also included `input_reference` and `source_surface_text`. Those fields are review-sensitive task surface readback content and are intentionally omitted from the abbreviated evidence block above.

## 6. Safety Signals Verified

The smoke output verified:

```yaml
github_write_performed: false
result_packet_written: false
codex_side_action_executed: false
broad_issue_scan_performed: false
```

The nested validation summary also verified:

```yaml
validation_summary.result: success
validation_summary.github_write_performed: false
validation_summary.result_packet_written: false
validation_summary.codex_side_action_executed: false
validation_summary.repo_files_modified: false
```

## 7. What This Smoke Does Not Prove

This smoke does not prove GitHub writeback.

This smoke does not prove Result Packet writeback.

This smoke does not prove runner behavior.

This smoke does not prove dispatcher behavior.

This smoke does not prove live GitHub fetch.

This smoke does not prove autonomous execution.

## 8. Still Forbidden Behaviors

The following remain forbidden:

* live GitHub fetch unless separately approved
* GitHub writeback
* Result Packet writeback
* Codex-side action execution
* runner behavior
* dispatcher behavior
* always-on watcher behavior
* broad issue scan
* unscoped GitHub issue scanning
* autonomous task discovery
* autonomous execution
* PR creation
* merge
* issue close
* label change
* GitHub comment write

## 9. Next Candidate Step

The next candidate step should remain bounded and explicit.

It should continue toward Phase 3 bridge evidence without broad automation, broad issue scanning, approval chaining, runner expansion, dispatcher expansion, or writeback behavior unless those capabilities are separately planned and approved.

## 10. Final Boundary Statement

#148 proves only the local text file smoke path for the #146 CLI.

It used `--local-text-file` only, did not use a GitHub token, did not perform live GitHub fetch, and did not write GitHub comments or Result Packets.

This evidence does not authorize broad issue scanning, autonomous execution, runner behavior, dispatcher behavior, GitHub writeback, Result Packet writeback, issue close, label changes, PR creation, or merge.

# Explicit Fetch Smoke Evidence (#147)

## 1. Purpose

#147 records how the #145 read-only explicit task surface fetch helper and the #146 local smoke CLI entry can be safely demonstrated.

This is a docs-only evidence and usage-notes artifact. It does not implement code, run a smoke command, perform live GitHub fetch, write GitHub comments, write Result Packets, execute Codex-side actions, create runner behavior, create dispatcher behavior, or enable broad issue scanning.

## 2. Issue Classification

```yaml
issue_number: 147
issue_role: support
risk_lane: fast
alignment: core_support
value_target: record how #145/#146 can be safely demonstrated with local-text-file smoke input, without adding GitHub writeback, Result Packet write, runner, dispatcher, or broad issue scan
docs_only: true
```

This supports the bridge direction by documenting a safe local evidence path. Manual copy/paste remains fallback only, not the target workflow.

## 3. What #145 Added

#145 added a read-only explicit task surface fetch helper.

The helper accepts one explicit task surface reference, preserves fail-closed behavior for broad or ambiguous inputs, and routes local surface text through the existing validation dry-run path.

The helper does not implement GitHub writeback, Result Packet writeback, Codex-side task action execution, broad issue scanning, runner behavior, dispatcher behavior, watcher behavior, PR creation, merge, issue close, or label changes.

## 4. What #146 Added

#146 added a local smoke CLI entry:

```text
python -m local_runner_bridge.explicit_task_surface_fetch_cli
```

The entry prints a JSON summary to stdout and delegates validation and fetch behavior to the #145 helper. It does not add a parallel validator or a new GitHub client.

## 5. Safe Local Smoke Path

The safest demonstration path is:

```text
--local-text-file
```

This path reads one explicit local task surface text file and avoids live GitHub network access. It is the preferred evidence path when the goal is to show local validation and JSON summary behavior without relying on credentials, network availability, or GitHub API responses.

## 6. Example Local Text File Smoke Command

Example command:

```powershell
python -m local_runner_bridge.explicit_task_surface_fetch_cli --local-text-file path\to\task_surface.txt
```

This document does not claim the command above was run in #147.

## 7. Expected JSON Safety Signals

The smoke entry should print JSON to stdout.

Expected safety signals include:

```yaml
github_write_performed: false
result_packet_written: false
codex_side_action_executed: false
broad_issue_scan_performed: false
```

If `validation_summary` is present, it should be treated as evidence for ChatGPT review, not as approval.

If `source_surface_text` is present in summaries, it is review-sensitive output and should be handled as task-surface readback content.

## 8. What This Evidence Does Not Prove

This evidence does not prove GitHub writeback.

This evidence does not prove Result Packet writeback.

This evidence does not prove runner behavior.

This evidence does not prove dispatcher behavior.

This evidence does not prove live GitHub fetch reliability.

This evidence does not prove autonomous execution.

## 9. Still Forbidden Behaviors

The following remain forbidden:

* live autonomous execution
* GitHub writeback
* Result Packet writeback
* Codex-side task action execution
* runner creation
* dispatcher creation
* always-on watcher behavior
* broad issue scanning
* unscoped GitHub issue scanning
* next issue inference
* latest issue inference
* autonomous task discovery
* PR creation
* merge
* issue close
* label change
* approval chaining

## 10. Next Candidate Step

The next possible step should be bounded and explicit, not broad automation.

A reasonable next candidate is a narrowly approved Phase 3 step that continues toward an auditable bridge path while preserving explicit input, local validation, ChatGPT readback, and user approval through ChatGPT.

## 11. Final Boundary Statement

#147 is docs-only evidence and usage notes.

The safest #145/#146 demonstration path is local text file input because it avoids live GitHub network access.

This document does not authorize GitHub writeback, Result Packet writeback, runner behavior, dispatcher behavior, broad issue scan, autonomous execution, PR creation, merge, issue close, label change, or GitHub comment writing.

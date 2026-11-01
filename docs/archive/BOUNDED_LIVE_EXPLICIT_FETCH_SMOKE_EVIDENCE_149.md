# Bounded Live Explicit Fetch Smoke Evidence (#149)

## 1. Purpose

#149 records a bounded live read-only explicit fetch smoke attempt through the #146 CLI.

The smoke used exactly one explicit GitHub issue comment reference and did not scan, infer, search, or try any other comment.

## 2. Issue Classification

```yaml
issue_number: 149
issue_role: core
risk_lane: strict
alignment: core
value_target: verify one explicitly provided GitHub issue comment reference can be read through the #146 CLI and routed into validation dry-run without writeback, Result Packet write, runner, dispatcher, or broad scan
```

## 3. Explicit Reference Used

Exactly one explicit comment reference was used:

```text
https://github.com/HarryWhite-TW/local-ai-workbench/issues/114#issuecomment-4618242459
```

No other candidate references were tried.

No broad issue scan was performed.

No next/latest issue inference was performed.

## 4. Command That Was Run

```powershell
$env:PYTHONPATH='src'; python -m local_runner_bridge.explicit_task_surface_fetch_cli --comment-url "https://github.com/HarryWhite-TW/local-ai-workbench/issues/114#issuecomment-4618242459"
```

No GitHub token was used.

## 5. JSON Output Evidence

The CLI printed JSON to stdout.

The result was blocked before validation dry-run because the explicit GitHub comment read failed with `HTTPError`.

```json
{
  "bounded_read_performed": false,
  "broad_issue_scan_performed": false,
  "codex_side_action_executed": false,
  "commit_triggered": false,
  "drift_detected": false,
  "errors": [
    "github_fetch_failed",
    "HTTPError"
  ],
  "explicit_input_preserved": true,
  "github_write_performed": false,
  "input_reference": "https://github.com/HarryWhite-TW/local-ai-workbench/issues/114#issuecomment-4618242459",
  "issue_closed": false,
  "label_changed": false,
  "next_recommended_action": "chatgpt_review",
  "pr_triggered": false,
  "protocol": "lawb.local_runner.explicit_task_surface_fetch_summary.v1",
  "push_triggered": false,
  "reference_type": "issue_comment_url",
  "result": "blocked",
  "result_packet_written": false
}
```

`source_surface_text` was not present in this blocked summary. If present in future summaries, it is review-sensitive output.

## 6. Safety Signals Verified

The JSON safety signals included:

```yaml
github_write_performed: false
result_packet_written: false
codex_side_action_executed: false
broad_issue_scan_performed: false
```

The output also reported:

```yaml
bounded_read_performed: false
result: blocked
reference_type: issue_comment_url
```

## 7. What This Smoke Proves

This smoke proves the #146 CLI accepted the single explicit comment URL and returned a bounded JSON summary.

This smoke proves the blocked error path preserves read-only safety signals when the explicit GitHub comment read fails.

## 8. What This Smoke Does Not Prove

This smoke does not prove a successful live GitHub fetch.

This smoke does not prove validation dry-run on fetched GitHub content.

This smoke does not prove GitHub writeback.

This smoke does not prove Result Packet writeback.

This smoke does not prove runner behavior.

This smoke does not prove dispatcher behavior.

This smoke does not authorize live autonomous execution.

This smoke does not authorize writeback.

## 9. Still Forbidden Behaviors

The following remain forbidden:

* broad issue scan
* next/latest issue inference
* fetching a second reference
* GitHub writeback
* Result Packet writeback
* Codex-side action execution
* runner behavior
* dispatcher behavior
* watcher behavior
* PR creation
* merge
* issue close
* label change
* GitHub comment write
* autonomous execution

## 10. Risk Notes

The explicit reference may be inaccessible through the unauthenticated GitHub API path used by the helper, or the API request may require credentials or encounter a GitHub-side access condition.

No token was used in this smoke.

Manual copy/paste remains fallback only, not the target workflow.

## 11. Next Candidate Step

The next candidate step should remain bounded and explicit.

A future retry may use the same explicit reference with a separately approved token environment variable, or a separately approved explicit reference, but must not scan or infer another target.

## 12. Final Boundary Statement

#149 used exactly one explicit GitHub issue comment reference.

The live read-only smoke returned blocked JSON with safe no-write signals.

No broad issue scan, next/latest issue inference, GitHub writeback, Result Packet write, Codex-side action execution, runner, dispatcher, watcher, PR, merge, issue close, label change, or GitHub comment write was performed.

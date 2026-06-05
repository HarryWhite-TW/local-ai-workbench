# Local Result Surface Draft and Readback Plan (#159)

## 1. Purpose

This document defines a local-only Result Surface draft and readback boundary.

It is a planning and sample artifact only. It does not implement a Result Surface generator, write to GitHub, write a Result Packet, or create runner / dispatcher behavior.

## 2. Issue Classification

```yaml
issue_number: 159
issue_role: support
risk_lane: fast
alignment: core_support
value_target: define a local-only sample Result Surface and readback boundary that can later be produced by local tools without GitHub writeback, Result Packet write, runner, dispatcher, or automation
```

## 3. Direction Lock

The long-term target remains:

```text
ChatGPT
-> explicit auditable Task Surface
-> local read-only fetch
-> validation dry-run
-> bounded Codex-side work
-> bounded Result Surface
-> ChatGPT readback and review
-> user approval decisions through ChatGPT
```

Manual copy/paste remains fallback only, not the final target workflow.

## 4. Relationship To #156 / #157 / #158

#156 proved controlled valid Task Surface live fetch and validation success.

#157 recorded the Phase 3 controlled fetch success.

#158 defined the bounded Result Surface concept.

#159 defines a local-only Result Surface draft and readback plan.

## 5. Local-Only Result Surface Definition

A Result Surface is an outbound review artifact.

A Result Surface is not a Result Packet writeback yet.

A Result Surface is not GitHub writeback.

A Result Surface is not automatic approval.

The local-only Result Surface should be safe to output as stdout or a temporary/local review file in a future issue. It must not be automatically posted to GitHub.

## 6. Minimum Result Surface Fields

The minimum local Result Surface shape should include:

- `result_surface_version`
- `result_id`
- `source_task_reference`
- `source_task_validation_result`
- `operation_mode`
- `status`
- `summary`
- `files_changed`
- `tests_run`
- `safety_flags`
- `blocked_reasons`
- `requires_user_approval`
- `next_recommended_step`
- `created_at`

Required safety flags should include explicit booleans:

- `github_write_performed=false`
- `result_packet_written=false`
- `codex_side_action_executed=false`
- `runner_invoked=false`
- `dispatcher_invoked=false`
- `watcher_invoked=false`
- `broad_scan_performed=false`
- `commit_performed=false`
- `push_performed=false`
- `pr_created=false`
- `merge_performed=false`
- `issue_closed=false`
- `label_changed=false`

## 7. Sample Result Surface

This sample is harmless and local-only. It represents a read-only validation result, not an executed code change.

```json
{
  "result_surface_version": "lawb.local_result_surface.v0.draft",
  "result_id": "result-159-local-readback-sample",
  "source_task_reference": {
    "kind": "local_sample",
    "issue_number": 159,
    "description": "Local-only Result Surface draft and readback sample"
  },
  "source_task_validation_result": {
    "result": "success",
    "validation_dry_run_reached": true,
    "task_packet_protocol_valid": true,
    "required_fields_present": true
  },
  "operation_mode": "local_read_only_review",
  "status": "success",
  "summary": "Sample local-only Result Surface for ChatGPT readback review. No code changes or external writes were performed.",
  "files_changed": [],
  "tests_run": [
    {
      "command": "not_run",
      "result": "not_run",
      "reason": "docs-only sample; no code or tests changed"
    }
  ],
  "safety_flags": {
    "github_write_performed": false,
    "result_packet_written": false,
    "codex_side_action_executed": false,
    "runner_invoked": false,
    "dispatcher_invoked": false,
    "watcher_invoked": false,
    "broad_scan_performed": false,
    "commit_performed": false,
    "push_performed": false,
    "pr_created": false,
    "merge_performed": false,
    "issue_closed": false,
    "label_changed": false
  },
  "blocked_reasons": [],
  "requires_user_approval": true,
  "next_recommended_step": "chatgpt_review_then_user_decides_next_boundary",
  "created_at": "example-timestamp"
}
```

## 8. ChatGPT Readback Requirements

A local Result Surface should be reviewable by ChatGPT before the user approves any follow-up action.

For readback, ChatGPT should be able to identify:

- the source task reference
- whether validation succeeded or blocked
- whether files changed
- which tests ran
- which safety flags are false
- whether follow-up requires user approval
- the next recommended step

The Result Surface should be structured enough for ChatGPT review, but it should not itself authorize follow-up work.

## 9. User Approval Boundary

A Result Surface is not automatic approval.

It may recommend a next step, but it must preserve a separate user approval boundary for high-risk actions such as commit, push, GitHub writeback, Result Packet write, issue close, label change, PR, merge, runner, dispatcher, watcher, or Codex-side action.

## 10. Local-Only Storage / Output Boundary

For future smoke work, the local-only Result Surface may be emitted to stdout or a temporary/local review file.

It must not be automatically posted to GitHub.

It must not trigger commit, push, issue close, label change, PR, merge, runner, dispatcher, watcher, or Codex-side action.

Any future persistent repository sample must be separately scoped as docs-only or test-only by an explicit task.

## 11. Forbidden Behaviors

Still forbidden in this planning/sample task:

- live GitHub fetch
- GitHub writeback
- GitHub issue body update
- GitHub comment write
- Result Packet write
- Codex-side action execution
- runner
- dispatcher
- watcher
- broad issue scan
- autonomous execution
- commit as an automatic Result Surface effect
- push as an automatic Result Surface effect
- PR / merge
- issue close
- label change
- dependency changes
- code changes
- test changes

## 12. Next Candidate Step

The next candidate issue should be:

```text
#160 Local Result Surface Stdout Smoke
```

#160 should be described as:

```text
Produce a local-only sample Result Surface to stdout or a temporary local file from known safe evidence, then have ChatGPT review it. Do not write to GitHub. Do not write Result Packet. Do not implement runner or dispatcher.
```

#160 should be Standard Lane if it creates or exercises a local helper, or Fast Lane if it remains docs-only.

This task does not implement #160.

## 13. Final Boundary Statement

This document defines a local-only Result Surface draft and readback plan only.

It does not implement code, modify tests, run live GitHub fetch, write GitHub comments, update GitHub issue bodies, close issues, change labels, create PRs, merge, write Result Packets, implement GitHub writeback, execute Codex-side actions, create runner behavior, create dispatcher behavior, create watcher behavior, enable broad scans, enable autonomous execution, add dependencies, or authorize high-risk operations.

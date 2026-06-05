# Bounded Writeback Target Contract Plan (#169)

## 1. Purpose

This document defines #169 Bounded Writeback Target Contract Plan.

The purpose is to define the exact bounded writeback target contract for a future Result Surface writeback path, including allowed target types, approval gates, forbidden actions, and audit shape.

This is a docs-only planning document.

This task does not implement writeback.

This task does not write GitHub comments.

This task does not write Result Packets.

This task does not implement runner, dispatcher, watcher, or automation behavior.

## 2. Issue Classification

```yaml
issue_number: 169
issue_role: support
risk_lane: fast
alignment: core_support
value_target: define the exact bounded writeback target contract for a future Result Surface writeback path, including allowed target types, approval gates, forbidden actions, and audit shape, without implementing GitHub writeback or Result Packet write
```

## 3. Direction Lock

The current proven direction remains:

```text
ChatGPT
-> explicit auditable Task Surface reference
-> local authenticated read-only fetch
-> validation dry-run
-> Result Surface stdout/readback
-> ChatGPT review
-> user approval decision
```

Manual copy/paste remains fallback only, not the target workflow.

#169 does not change the project direction from readback-first evidence to automatic writeback.

## 4. Current Proven Path

#166 proved authenticated live fetch to Result Surface stdout/readback.

#167 recorded that success as a Phase 3 decision note.

#168 defined bounded Result Surface writeback planning.

The current proven path is:

```text
ChatGPT
-> explicit auditable Task Surface reference
-> local authenticated read-only fetch
-> validation dry-run
-> Result Surface stdout/readback
-> ChatGPT review
-> user approval decision
```

The current proven path does not include GitHub writeback, Result Packet write, Codex-side action execution, runner behavior, dispatcher behavior, watcher behavior, broad issue scan, or autonomous execution.

## 5. Why A Writeback Target Contract Is Needed

A writeback target is an explicit destination approved before any external side effect.

Without a target contract, a future writeback implementation could accidentally infer where to write, write to more than one target, rely on broad issue scanning, or confuse local readback evidence with external write permission.

The target contract exists to keep writeback single-target, reviewable, approval-gated, auditable, and fail-closed.

GitHub writeback is an external side effect and must be Strict Lane.

Result Packet write is also a side effect and must be Strict Lane.

## 6. Contract Scope

#169 defines a future writeback target contract only.

The contract covers:

- allowed target types
- forbidden target types
- required target fields
- required Result Surface fields before writeback
- ChatGPT readback gate
- user approval gate
- safety flags required before writeback
- failure and abort conditions
- future writeback audit shape

The contract does not implement GitHub writeback.

The contract does not implement Result Packet write.

The contract does not implement runner, dispatcher, watcher, or automation behavior.

## 7. Allowed Future Target Types

Future allowed target types may include:

- one explicit GitHub issue comment target
- one local review file target

An allowed target must be explicit, singular, and approved before writeback.

An allowed target must not be inferred from issue history, latest issue, next issue, labels, search results, or open issue scans.

## 8. Forbidden Target Types

Future disallowed targets must include:

- broad issue scan results
- inferred latest issue
- inferred next issue
- multiple issue targets
- PR targets
- merge targets
- label change targets
- issue close targets
- commit targets
- push targets
- runner targets
- dispatcher targets
- watcher targets

If a future task requires a target not listed as allowed, it must define a separate bounded planning task before implementation.

## 9. Required Target Fields

A future writeback target contract should require fields such as:

```yaml
writeback_target_contract:
  writeback_target_type: github_issue_comment | local_review_file
  writeback_target_reference: string
  source_result_surface_id: string
  source_task_reference: string
  approved_by_user: boolean
  approval_timestamp: string
  chatgpt_readback_completed: boolean
  dry_run_required: boolean
  write_mode: preview_only | approved_single_write
  forbidden_actions:
    - broad_issue_scan
    - next_latest_issue_inference
    - issue_close
    - label_change
    - pr_creation
    - merge
    - approval_chaining
```

The target reference must identify exactly one destination.

The target contract must fail closed if any required field is missing, ambiguous, or conflicts with the requested write mode.

## 10. Required Result Surface Fields Before Writeback

Before future writeback can be considered, the source Result Surface must include:

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

The source Result Surface must be read back by ChatGPT before user approval.

The source Result Surface is evidence only.

The source Result Surface is not approval.

## 11. ChatGPT Readback Gate

Future writeback must require ChatGPT readback before write.

ChatGPT readback must show:

- the exact writeback target type
- the exact writeback target reference
- the source Result Surface ID
- the source task reference
- the proposed content or safe preview
- the required safety flags
- the forbidden actions
- whether dry-run is required
- whether user approval has been granted for this exact target

Writeback must not proceed if ChatGPT readback is missing.

## 12. User Approval Gate

Future writeback must require explicit user approval before write.

Approval must be scoped to:

- exactly one target
- exactly one content preview
- exactly one write mode
- exactly one use

Approval must not chain into GitHub writeback for other targets, Result Packet write, Codex-side action execution, runner behavior, dispatcher behavior, watcher behavior, commit, push, PR creation, merge, issue close, or label change.

## 13. Safety Flags Required Before Writeback

Future writeback must require these safety flags before any write:

```yaml
safety_flags_before_writeback:
  exact_single_target_confirmed: true
  chatgpt_readback_completed: true
  explicit_user_approval_present: true
  safe_preview_completed: true
  token_value_printed: false
  token_value_written: false
  broad_issue_scan_performed: false
  next_latest_issue_inference_performed: false
  automatic_issue_close_performed: false
  automatic_label_change_performed: false
  pr_created: false
  merge_performed: false
  approval_chaining_attempted: false
```

If any required safety flag is missing or false when it must be true, the future writeback must abort.

## 14. Failure And Abort Conditions

The future writeback path must abort if:

- the target type is missing
- the target reference is missing
- the target is ambiguous
- more than one target is present
- the target is inferred from latest or next issue
- the target comes from broad issue scan results
- ChatGPT readback is missing
- safe preview is missing
- explicit user approval is missing
- approval is not scoped to the exact target and content
- dry-run is required but not completed
- token value would be printed or written
- PR creation is requested
- merge is requested
- issue close is requested
- label change is requested
- approval chaining is attempted

Abort means no writeback, no Result Packet write, no GitHub comment write, no Codex-side action execution, no runner, no dispatcher, no watcher, no commit, no push, no PR, no merge, no issue close, and no label change.

## 15. Audit Shape For Future Writeback

A future writeback audit should include fields such as:

```yaml
writeback_audit:
  protocol: lawb.writeback_target_audit.v1
  result: success | blocked | failed
  writeback_target_type: github_issue_comment | local_review_file
  writeback_target_reference: string
  explicit_target_count: 1
  source_result_surface_id: string
  source_task_reference: string
  chatgpt_readback_completed: boolean
  explicit_user_approval_present: boolean
  safe_preview_completed: boolean
  dry_run_completed: boolean
  github_write_performed: boolean
  result_packet_written: boolean
  codex_side_action_executed: false
  runner_invoked: false
  dispatcher_invoked: false
  watcher_invoked: false
  broad_scan_performed: false
  next_latest_issue_inference_performed: false
  pr_created: false
  merge_performed: false
  issue_closed: false
  label_changed: false
  approval_chaining_attempted: false
  failure_reason: string | null
```

The audit must distinguish success, blocked, and failed outcomes.

The audit must preserve evidence-versus-approval semantics.

## 16. Still Forbidden Behaviors

The following behaviors remain forbidden:

```text
GitHub writeback implementation
Result Packet write implementation
Codex-side action execution
runner behavior
dispatcher behavior
watcher behavior
broad issue scan
next/latest issue inference
autonomous execution
automatic commit
automatic push
PR creation
merge
issue close
label change
approval chaining
```

#169 does not implement any of these behaviors.

## 17. Next Candidate Step

The next candidate issue should be:

```text
#170 Writeback Target Contract Sample
```

#170 should create a docs-only or local-only sample writeback target contract.

#170 should not yet implement GitHub writeback unless explicitly approved later.

#170 must not perform GitHub writeback.

#170 must not write a Result Packet.

#170 must not implement runner, dispatcher, or watcher behavior.

## 18. Final Boundary Statement

#169 defines the writeback target contract boundary only.

It preserves the current proven path from explicit Task Surface reference to authenticated read-only fetch, validation dry-run, Result Surface stdout/readback, ChatGPT review, and user approval decision.

It does not implement GitHub writeback, Result Packet write, Codex-side action execution, runner behavior, dispatcher behavior, watcher behavior, broad issue scan, next/latest issue inference, autonomous execution, automatic commit, automatic push, PR creation, merge, issue close, label change, or approval chaining.

A future writeback path must remain single-target, previewed, ChatGPT-readback-gated, explicitly user-approved, Strict Lane when external side effects are involved, and auditable.

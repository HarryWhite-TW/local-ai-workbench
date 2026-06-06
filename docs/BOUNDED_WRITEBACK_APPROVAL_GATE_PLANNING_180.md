# Bounded Writeback Approval Gate Planning (#180)

## 1. Purpose

This document defines #180 Bounded Writeback Approval Gate Planning.

The purpose is to define how explicit user approval should be represented before any future bounded writeback.

This is a docs-only Fast Lane planning document.

#180 only plans a future approval gate.

#180 does not implement approval gate code.

#180 does not implement GitHub writeback.

#180 does not write GitHub comments.

#180 does not update GitHub issue bodies.

#180 does not write Result Packets.

#180 does not implement runner, dispatcher, watcher, or automation behavior.

#180 does not authorize real write mode.

## 2. Issue Classification

```yaml
issue_number: 180
issue_role: support
risk_lane: fast
alignment: core_support
value_target: define a bounded approval gate for future writeback after local dry-run preview readback, without implementing GitHub writeback, Result Packet write, runner, dispatcher, watcher, or automation
```

## 3. Direction Lock

The current long-term direction remains:

```text
ChatGPT
-> explicit auditable Task Surface
-> local authenticated read-only fetch
-> validation dry-run
-> Result Surface stdout/readback
-> Writeback Target Contract validation
-> local dry-run preview
-> ChatGPT readback
-> explicit user approval
-> only then future bounded writeback planning/implementation
```

Manual copy/paste remains fallback only, not the target workflow.

#180 does not change the project direction from readback-first evidence to automatic writeback.

## 4. Source Documents

This plan is based on:

- `docs/LOCAL_WRITEBACK_DRY_RUN_PREVIEW_SUCCESS_DECISION_NOTE_179.md`
- `docs/LOCAL_WRITEBACK_DRY_RUN_PREVIEW_SMOKE_EVIDENCE_178.md`
- `docs/LOCAL_WRITEBACK_DRY_RUN_PREVIEW_BUILDER_PLAN_176.md`
- `docs/LOCAL_WRITEBACK_DRY_RUN_PREVIEW_PLANNING_174.md`
- `docs/WRITEBACK_TARGET_CONTRACT_VALIDATOR_SUCCESS_DECISION_NOTE_173.md`

#178 proved the committed local dry-run preview builder can emit valid preview JSON to stdout.

#179 recorded the dry-run preview success.

#176 planned the local-only preview builder.

#174 planned the local-only dry-run preview artifact.

#173 recorded the local-only Writeback Target Contract validator success.

## 5. Why An Approval Gate Is Needed

An approval gate is needed because dry-run preview success is evidence only.

Dry-run preview success does not approve GitHub writeback.

Dry-run preview success does not approve Result Packet write.

Dry-run preview success does not approve runner, dispatcher, watcher, or automation behavior.

Approval must happen only after:

- successful Writeback Target Contract validation
- successful dry-run preview generation
- ChatGPT readback completed
- user explicitly approves the exact preview

The approval gate exists to prevent approval from being inferred from previous conversation, commit success, push success, dry-run preview success, or any other evidence artifact.

## 6. Current Proven Path

The currently proven path is:

```text
ChatGPT
-> explicit auditable Task Surface
-> local authenticated read-only fetch
-> validation dry-run
-> Result Surface stdout/readback
-> Writeback Target Contract validation
-> local dry-run preview stdout/readback
-> ChatGPT review
-> user decision
```

#178 proved local dry-run preview stdout evidence.

#178 did not prove GitHub writeback.

#178 did not prove Result Packet write.

#178 did not prove real write mode.

#178 did not prove approval automation.

## 7. Approval Gate Scope

A future approval gate should be bounded to exactly one explicit writeback decision.

Approval must be bound to exactly one explicit target.

Approval must be bound to exactly one preview artifact.

Approval must be bound to exactly one source Result Surface.

Approval must be bound to exactly one source task reference.

Approval must not be inferred from previous conversation.

Approval must not be inferred from commit success.

Approval must not be inferred from push success.

Approval must not be inferred from dry-run preview success.

Approval must not enable automatic writeback by itself.

For now, the approval gate remains planning-only and must preserve:

```text
approved_write_mode=dry_run_only
external_side_effect_allowed=false
```

## 8. Required Approval Preconditions

A future approval record may be considered valid only after these preconditions are satisfied:

- successful Writeback Target Contract validation
- successful local dry-run preview generation
- exactly one explicit target is present
- exactly one preview artifact is present
- ChatGPT readback is completed
- user explicitly approves the exact preview
- approval is scoped to one target, one preview, one content body, one write mode, and one use
- no token-like values appear
- no Authorization headers appear
- no hidden environment variables appear
- no broad issue scan appears
- no inferred latest issue appears
- no inferred next issue appears

If any precondition is missing, the approval gate must fail closed.

## 9. Approval Record Shape

A future approval record should include fields such as:

```yaml
approval_record_version: lawb.writeback_approval_record.v1
approval_id: string
source_preview_id: string
source_result_surface_id: string
source_task_reference: string
writeback_target_type: github_issue_comment | local_review_file
writeback_target_reference: string
chatgpt_readback_completed: true
approved_by_user: true
approval_timestamp: string
approved_write_mode: dry_run_only
allowed_next_step: bounded_writeback_planning
forbidden_actions:
  - github_writeback_implementation
  - github_comment_write
  - github_issue_body_update
  - result_packet_write_implementation
  - codex_side_action_execution
  - runner_behavior
  - dispatcher_behavior
  - watcher_behavior
  - broad_issue_scan
  - next_latest_issue_inference
  - autonomous_execution
  - automatic_commit
  - automatic_push
  - pr_creation
  - merge
  - issue_close
  - label_change
  - approval_chaining
  - real_write_mode
external_side_effect_allowed: false
created_at: string
```

For now, `approved_write_mode` should remain:

```text
dry_run_only
```

For now, `external_side_effect_allowed` must remain:

```text
false
```

Real writeback mode must remain forbidden until a later explicit Strict Lane issue.

## 10. Valid Approval States

A future approval record may be valid only when:

- one valid preview exists
- the preview is the exact preview being approved
- ChatGPT readback is completed
- user approval is explicit
- user approval is scoped to one target
- user approval is scoped to one preview artifact
- `approved_write_mode=dry_run_only`
- `external_side_effect_allowed=false`
- forbidden actions remain listed
- no automatic writeback is triggered

The valid approval state is still a planning and authorization artifact only.

The valid approval state does not itself perform a write.

## 11. Blocked Approval States

A future approval gate must fail closed if:

- no preview exists
- preview is invalid
- ChatGPT readback is not completed
- user approval is missing
- approval references multiple targets
- approval references inferred target
- approval tries to approve GitHub writeback directly
- approval tries to approve Result Packet write directly
- approval tries to approve runner / dispatcher / watcher behavior
- approval tries to approve issue close / label change / PR / merge
- token-like values appear

Blocked means no writeback planning may treat the approval record as valid.

Blocked means no external side effect may occur.

## 12. Abort Conditions

A future approval gate path must abort when:

- source preview ID is missing
- source preview cannot be matched
- preview result is not valid
- target type is missing
- target reference is missing
- target is ambiguous
- more than one target is present
- target is inferred from latest or next issue
- target comes from broad issue scan output
- ChatGPT readback is missing
- explicit user approval is missing
- approved write mode is not `dry_run_only`
- external side effect is requested
- token values would be printed or written
- GitHub writeback is approved directly
- Result Packet write is approved directly
- Codex-side action execution is approved directly
- runner, dispatcher, or watcher behavior is approved directly
- PR creation is approved directly
- merge is approved directly
- issue close is approved directly
- label change is approved directly
- approval chaining is attempted

Abort means no GitHub writeback, no Result Packet write, no Codex-side action execution, no runner, no dispatcher, no watcher, no commit, no push, no PR, no merge, no issue close, and no label change.

## 13. ChatGPT Readback Requirement

ChatGPT readback must happen before a user approval decision can be represented.

ChatGPT readback should show:

- preview ID
- source Result Surface ID
- source task reference
- writeback target type
- writeback target reference
- contract validation result
- write mode
- preview content
- safe preview summary
- forbidden actions
- safety flags
- whether external side effects remain forbidden
- exact approval scope being requested

`chatgpt_readback_completed=true` may be recorded only after ChatGPT review.

ChatGPT readback is evidence.

ChatGPT readback is not approval by itself.

## 14. User Approval Boundary

User approval must remain explicit, scoped, and separate.

User approval must approve the exact preview.

User approval must not be inferred from previous conversation.

User approval must not be inferred from commit success.

User approval must not be inferred from push success.

User approval must not be inferred from dry-run preview success.

User approval must not enable automatic writeback by itself.

Any later writeback approval must be scoped to:

- one target
- one preview artifact
- one content body
- one write mode
- one use

Real writeback remains forbidden until a later explicit Strict Lane issue.

## 15. Still Forbidden Behaviors

The following behaviors remain forbidden:

```text
GitHub writeback implementation
GitHub comment write
GitHub issue body update
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
real write mode
```

These behaviors require separate planning and explicit approval before implementation.

## 16. Next Candidate Step

The next candidate issue should be:

```text
#181 Bounded Writeback Approval Record Sample
```

#181 should create a docs-only sample approval record.

#181 must not implement approval code.

#181 must not perform GitHub writeback.

#181 must not write Result Packets.

#181 must not implement runner, dispatcher, or watcher behavior.

#181 should preserve `external_side_effect_allowed=false`.

## 17. Final Boundary Statement

#180 defines bounded Writeback Approval Gate planning only.

#180 does not implement approval gate code.

#180 does not implement GitHub writeback.

#180 does not write GitHub comments.

#180 does not update GitHub issue bodies.

#180 does not write Result Packets.

#180 does not implement Codex-side action execution.

#180 does not implement runner, dispatcher, watcher, or automation behavior.

#180 does not authorize real write mode.

A future approval gate should represent explicit user approval only after successful Writeback Target Contract validation, successful local dry-run preview generation, ChatGPT readback, and user approval of the exact preview.

The safe next step is #181 Bounded Writeback Approval Record Sample.

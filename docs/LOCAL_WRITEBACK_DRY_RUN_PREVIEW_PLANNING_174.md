# Local Writeback Dry-Run Preview Planning (#174)

## 1. Purpose

This document defines #174 Local Writeback Dry-Run Preview Planning.

The purpose is to plan a future local-only writeback dry-run preview artifact after Writeback Target Contract validation and before any real writeback.

This is a docs-only Fast Lane planning document.

#174 only plans a future dry-run preview artifact.

#174 does not implement dry-run preview code.

#174 does not implement GitHub writeback.

#174 does not write GitHub comments.

#174 does not write Result Packets.

#174 does not implement runner, dispatcher, watcher, or automation behavior.

## 2. Issue Classification

```yaml
issue_number: 174
issue_role: support
risk_lane: fast
alignment: core_support
value_target: plan a local-only writeback dry-run preview artifact after Writeback Target Contract validation, without implementing GitHub writeback, Result Packet write, runner, dispatcher, watcher, or automation
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
-> ChatGPT review
-> explicit user approval
-> only then future bounded writeback
```

Manual copy/paste remains fallback only, not the target workflow.

#174 does not change the project direction from readback-first evidence to automatic writeback.

## 4. Source Documents

This plan is based on:

- `docs/WRITEBACK_TARGET_CONTRACT_VALIDATOR_SUCCESS_DECISION_NOTE_173.md`
- `docs/WRITEBACK_TARGET_CONTRACT_LOCAL_VALIDATION_PLAN_171.md`
- `docs/WRITEBACK_TARGET_CONTRACT_SAMPLE_170.md`
- `docs/BOUNDED_WRITEBACK_TARGET_CONTRACT_PLAN_169.md`
- `docs/BOUNDED_RESULT_SURFACE_WRITEBACK_PLANNING_168.md`

#172 implemented a local-only Writeback Target Contract validator.

#173 recorded validator success.

#169, #170, #171, and #168 remain the source of truth for writeback target boundaries, sample contract shape, local validation gates, and external side-effect limits.

## 5. Why A Dry-Run Preview Is Needed

A dry-run preview is needed because Writeback Target Contract validation proves that a target contract is locally valid, but it does not show the exact content that would be written.

A dry-run preview is a local review artifact shown before any external side effect.

A dry-run preview is not proof of approval by itself.

A dry-run preview must be generated only after a Writeback Target Contract validates successfully.

A dry-run preview exists to let ChatGPT read back the exact proposed target, proposed content, safety flags, forbidden actions, and approval requirements before a user decides whether any later bounded writeback should be planned.

## 6. Current Proven Path

The currently proven path is:

```text
ChatGPT
-> explicit auditable Task Surface
-> local authenticated read-only fetch
-> validation dry-run
-> Result Surface stdout/readback
-> Writeback Target Contract validation
-> local validation summary stdout/readback
-> ChatGPT review
-> user decision
```

#172 proved local Writeback Target Contract validation.

#172 did not prove dry-run preview artifact creation.

#172 did not prove GitHub writeback.

#172 did not prove Result Packet write.

#172 did not prove real write mode.

## 7. Preview Artifact Scope

A future dry-run preview artifact should be local-only.

It should describe what would be written if a later, separately approved bounded writeback issue authorizes a write.

It should not perform the write.

It should not write GitHub comments.

It should not write Result Packets.

It should not update issue bodies.

It should not close issues.

It should not change labels.

It should not create PRs.

It should not merge.

It should not invoke runner, dispatcher, watcher, or automation behavior.

It should preserve:

```text
external_side_effect_allowed=false
write_mode=dry_run_only
approved_by_user=false unless explicitly approved later
chatgpt_readback_completed=true only after ChatGPT review
```

## 8. Preview Artifact Input Requirements

A future dry-run preview artifact should require:

- a successful Writeback Target Contract validation summary
- exactly one explicit writeback target type
- exactly one explicit writeback target reference
- one source Result Surface ID
- one source task reference
- `write_mode=dry_run_only`
- `external_side_effect_allowed=false`
- forbidden actions list
- safety flags
- safe preview content
- no token values
- no Authorization headers
- no hidden environment variables
- no broad scan output
- no inferred latest issue
- no inferred next issue

If the contract validation result is not success, preview creation must fail closed.

If the target is missing, ambiguous, multiple, or inferred, preview creation must fail closed.

## 9. Preview Artifact Output Shape

A future dry-run preview artifact should include fields such as:

```yaml
preview_version: lawb.writeback_dry_run_preview.v1
preview_id: string
source_result_surface_id: string
source_task_reference: string
writeback_target_type: github_issue_comment | local_review_file
writeback_target_reference: string
contract_validation_result: success
write_mode: dry_run_only
preview_content: string
safe_preview_summary: string
forbidden_actions:
  - string
safety_flags:
  external_side_effect_allowed: false
  token_value_printed: false
  token_value_written: false
  broad_issue_scan_performed: false
  next_latest_issue_inference_performed: false
  github_write_performed: false
  result_packet_written: false
  codex_side_action_executed: false
  runner_invoked: false
  dispatcher_invoked: false
  watcher_invoked: false
  pr_created: false
  merge_performed: false
  issue_closed: false
  label_changed: false
  approval_chaining_attempted: false
requires_chatgpt_readback: true
requires_user_approval: true
external_side_effect_allowed: false
blocked_reasons:
  - string
next_recommended_step: chatgpt_readback_then_user_decision
created_at: string
```

The preview content must not include:

- token values
- Authorization headers
- hidden environment variables
- secrets
- broad scan output
- inferred latest issue
- inferred next issue

## 10. Required Gates Before Preview

Before a future dry-run preview is created, these gates must pass:

- Writeback Target Contract validation succeeded
- exactly one target is present
- the target is explicit
- required fields are present
- `write_mode=dry_run_only`
- forbidden actions are present
- `external_side_effect_allowed=false`
- no token-like values are present
- no broad scan is requested
- no next/latest issue inference is requested
- no GitHub writeback is requested
- no Result Packet write is requested
- no runner, dispatcher, or watcher behavior is requested
- no issue close, label change, PR creation, or merge is requested

If any gate fails, preview creation must fail closed.

## 11. Required Gates Before Real Writeback

Real writeback remains forbidden after preview until a later explicit approval issue.

A dry-run preview does not authorize real writeback.

A successful preview does not authorize GitHub writeback.

A successful preview does not authorize Result Packet write.

A successful preview does not authorize runner, dispatcher, watcher, or automation behavior.

Before any future real writeback can be considered, a separate bounded issue must define and approve:

- the exact target
- the exact content
- the exact write mode
- ChatGPT readback evidence
- explicit user approval
- token non-exposure evidence
- rollback boundary
- audit shape
- failure behavior

## 12. Valid Preview States

A future dry-run preview may be valid only when:

- contract validation result is success
- one explicit target is present
- `write_mode=dry_run_only`
- `external_side_effect_allowed=false`
- preview content is safe for local readback
- no token values appear
- no forbidden external side effect is requested
- `requires_chatgpt_readback=true`
- `requires_user_approval=true`
- `next_recommended_step=chatgpt_readback_then_user_decision`

The preview is evidence only.

The preview is not approval.

## 13. Blocked Preview States

A future dry-run preview must fail closed if:

- contract validation failed
- required fields are missing
- multiple targets are present
- target is inferred
- `write_mode` is not `dry_run_only`
- forbidden actions are missing
- GitHub writeback is requested
- Result Packet write is requested
- runner, dispatcher, or watcher behavior is requested
- issue close, label change, PR creation, or merge is requested
- token-like values appear
- Authorization headers appear
- hidden environment variables appear
- broad scan output is included
- inferred latest issue is included
- inferred next issue is included

Blocked means no preview artifact should be treated as valid and no external side effect may occur.

## 14. Abort Conditions

A future dry-run preview path must abort when:

- contract validation summary is missing
- contract validation result is not success
- target type is missing
- target reference is missing
- target is ambiguous
- more than one target is present
- target is inferred from latest or next issue
- target comes from broad issue scan output
- required source references are missing
- safe preview content is missing
- forbidden actions are missing
- safety flags are missing
- write mode is not `dry_run_only`
- token values would be printed or written
- GitHub writeback is attempted
- Result Packet write is attempted
- Codex-side action execution is attempted
- runner, dispatcher, or watcher behavior is attempted
- PR creation is requested
- merge is requested
- issue close is requested
- label change is requested
- approval chaining is attempted

Abort means no GitHub writeback, no Result Packet write, no Codex-side action execution, no runner, no dispatcher, no watcher, no commit, no push, no PR, no merge, no issue close, and no label change.

## 15. ChatGPT Readback Requirements

ChatGPT readback must happen after a future dry-run preview is created and before any user approval decision.

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
- blocked reasons, if any
- whether external side effects remain forbidden
- the next recommended step

`chatgpt_readback_completed=true` may be recorded only after ChatGPT review.

ChatGPT readback is evidence.

ChatGPT readback is not approval by itself.

## 16. User Approval Boundary

User approval must remain explicit, scoped, and separate.

A dry-run preview must not imply approval.

A dry-run preview must not chain approval into writeback, Result Packet write, Codex-side action execution, runner behavior, dispatcher behavior, watcher behavior, commit, push, PR creation, merge, issue close, or label change.

`approved_by_user=false` must remain preserved unless a later explicit approval issue changes it for one exact target and one exact preview.

Any later writeback approval must be scoped to:

- one target
- one preview artifact
- one content body
- one write mode
- one use

## 17. Still Forbidden Behaviors

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
real write mode
```

These behaviors require separate planning and explicit approval before implementation.

## 18. Next Candidate Step

The next candidate issue should be:

```text
#175 Local Writeback Dry-Run Preview Sample
```

#175 should create a docs-only or local-only sample dry-run preview artifact.

#175 must not perform GitHub writeback.

#175 must not write Result Packets.

#175 must not implement runner, dispatcher, or watcher behavior.

#175 should not implement real writeback.

#175 should preserve `external_side_effect_allowed=false`.

## 19. Final Boundary Statement

#174 defines local Writeback Dry-Run Preview Planning only.

#174 does not implement dry-run preview code.

#174 does not implement GitHub writeback.

#174 does not write GitHub comments.

#174 does not write Result Packets.

#174 does not implement Codex-side action execution.

#174 does not implement runner, dispatcher, watcher, or automation behavior.

#174 does not authorize real write mode.

A future dry-run preview should be a local review artifact created only after successful Writeback Target Contract validation.

The safe next step is #175 Local Writeback Dry-Run Preview Sample.

# Local Approval Record Validation Plan (#182)

## 1. Purpose

This document defines #182 Local Approval Record Validation Plan.

The purpose is to define how a future local-only validator should validate bounded writeback approval records before any future writeback implementation.

This is a docs-only Fast Lane planning document.

#182 defines local approval record validation planning only.

#182 does not implement approval validation code.

#182 does not implement approval gate code.

#182 does not implement GitHub writeback.

#182 does not write GitHub comments.

#182 does not update GitHub issue bodies.

#182 does not write Result Packets.

#182 does not implement runner, dispatcher, watcher, or automation behavior.

## 2. Issue Classification

```yaml
issue_number: 182
issue_role: support
risk_lane: fast
alignment: core_support
value_target: define local validation rules for bounded writeback approval records before any future writeback implementation, without implementing approval validation code, GitHub writeback, Result Packet write, runner, dispatcher, watcher, or automation
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

#182 does not change the project direction from readback-first evidence to automatic writeback.

## 4. Source Documents

This plan is based on:

- `docs/BOUNDED_WRITEBACK_APPROVAL_RECORD_SAMPLE_181.md`
- `docs/BOUNDED_WRITEBACK_APPROVAL_GATE_PLANNING_180.md`
- `docs/LOCAL_WRITEBACK_DRY_RUN_PREVIEW_SUCCESS_DECISION_NOTE_179.md`
- `docs/LOCAL_WRITEBACK_DRY_RUN_PREVIEW_SMOKE_EVIDENCE_178.md`
- `docs/WRITEBACK_TARGET_CONTRACT_VALIDATOR_SUCCESS_DECISION_NOTE_173.md`

#180 planned the bounded writeback approval gate.

#181 created sample approval records only.

#179 recorded the local dry-run preview success decision.

#178 proved local dry-run preview stdout evidence.

#173 recorded local Writeback Target Contract validator success.

## 5. Why Approval Record Validation Is Needed

Approval record validation is needed because approval records are safety-critical review artifacts.

A future approval record validator must validate approval records before any future writeback.

An approval record must not be treated as valid merely because it exists.

An approval record must not be treated as valid because a previous conversation implied approval.

An approval record must not be treated as valid because commit, push, validation, or dry-run preview succeeded.

Validation exists to fail closed before any future bounded writeback planning or implementation can rely on an approval record.

## 6. Validation Scope

A future approval record validator should be local-only.

The validator should:

- read one local approval record JSON input
- validate required fields
- validate one explicit target
- validate one source preview
- validate ChatGPT readback gate
- validate user approval gate
- validate approved write mode
- validate external side-effect boundary
- validate forbidden actions
- emit one local validation summary

The future validator must not write files unless explicitly scoped later.

The future validator must not call GitHub.

The future validator must not write GitHub comments.

The future validator must not update GitHub issue bodies.

The future validator must not write Result Packets.

The future validator must not invoke runner, dispatcher, or watcher.

## 7. Required Approval Record Fields

A future approval record validator should require fields such as:

- `approval_record_version`
- `approval_id`
- `source_preview_id`
- `source_result_surface_id`
- `source_task_reference`
- `writeback_target_type`
- `writeback_target_reference`
- `chatgpt_readback_completed`
- `approved_by_user`
- `approval_timestamp`
- `approved_write_mode`
- `allowed_next_step`
- `forbidden_actions`
- `external_side_effect_allowed`
- `created_at`

A future validator must fail closed when required fields are missing.

`source_preview_id` must be present.

`writeback_target_reference` must be present.

For now, the only locally valid approved write mode should remain:

```text
dry_run_only
```

For now, `external_side_effect_allowed` must remain:

```text
false
```

Real write modes must remain forbidden until a later explicit Strict Lane issue.

## 8. Required Preconditions

A future approval record validator should require:

- successful Writeback Target Contract validation happened before the approval record was prepared
- successful dry-run preview generation happened before the approval record was prepared
- ChatGPT readback was completed
- user explicitly approved the exact preview
- approval is bound to one source preview
- approval is bound to one source Result Surface
- approval is bound to one source task reference
- approval is bound to one explicit writeback target
- approval is not inferred from previous conversation
- approval is not inferred from commit success
- approval is not inferred from push success
- approval is not inferred from validation success
- approval is not inferred from dry-run preview success

If any precondition is missing or contradicted, validation must fail closed.

## 9. Valid Approval States

A future approval record may validate successfully only when:

- all required fields are present
- `chatgpt_readback_completed=true`
- `approved_by_user=true`
- `source_preview_id` is present
- `writeback_target_reference` is present
- approval references exactly one target
- approval references an explicit target
- `approved_write_mode=dry_run_only`
- `external_side_effect_allowed=false`
- forbidden actions are present
- no token-like values appear
- no Authorization headers appear
- no hidden environment variables appear
- no broad scan output appears
- no inferred latest issue appears
- no inferred next issue appears

The valid approval state is still local validation proof only.

The valid approval state does not itself write anything.

## 10. Blocked Approval States

A future validator must fail closed when:

- required fields are missing
- approval references multiple targets
- approval references an inferred target
- approval is inferred from previous conversation
- approval is inferred from commit success
- approval is inferred from push success
- approval is inferred from validation success
- approval is inferred from dry-run preview success
- `chatgpt_readback_completed=false`
- `approved_by_user=false`
- `source_preview_id` is missing
- `writeback_target_reference` is missing
- `approved_write_mode` is not `dry_run_only`
- `external_side_effect_allowed=true`
- approval tries to approve GitHub writeback directly
- approval tries to approve Result Packet write directly
- approval tries to approve runner / dispatcher / watcher behavior
- approval tries to approve issue close / label change / PR / merge
- token-like values appear

Blocked means no future writeback planning may treat the approval record as valid.

Blocked means no external side effect may occur.

## 11. Abort Conditions

A future validation path must abort when:

- approval JSON cannot be read
- approval JSON cannot be parsed
- approval record is not an object
- required fields are missing
- source preview ID is missing
- target type is missing
- target reference is missing
- target is ambiguous
- more than one target is present
- target is inferred from latest or next issue
- target comes from broad issue scan output
- ChatGPT readback is missing
- explicit user approval is missing
- approval is inferred from prior conversation or prior command success
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

## 12. Expected Validation Summary

A future validation summary should include fields such as:

```yaml
validation_result: success | blocked
approval_record_version: string
approval_id: string
source_preview_id: string
source_result_surface_id: string
source_task_reference: string
writeback_target_type: string
writeback_target_reference: string
chatgpt_readback_gate_satisfied: boolean
user_approval_gate_satisfied: boolean
approved_write_mode: dry_run_only
external_side_effect_allowed: false
blocked_reasons:
  - string
next_recommended_step: chatgpt_review | bounded_writeback_planning
```

The summary should be local stdout/readback evidence only.

The summary should not write Result Packets.

The summary should not write GitHub comments.

The summary should not perform external side effects.

## 13. Future Validator Input And Output Shape

A future validator input should be one local approval record JSON document.

A future validator output should be one local validation summary JSON object.

The future validator may support a command shape such as:

```powershell
$env:PYTHONPATH='src'; python -m local_runner_bridge.approval_record_validator_cli --approval-record-file <path>
```

The future validator must:

- read local files only
- print validation summary JSON to stdout
- not write files unless explicitly scoped later
- not call GitHub
- not print tokens
- not inspect hidden environment values
- not execute tasks
- not commit
- not push
- not create PRs
- not merge
- not close issues
- not change labels
- not invoke runner, dispatcher, watcher, or automation behavior

## 14. ChatGPT Readback Requirement

ChatGPT readback must happen before a user approval decision can be treated as valid.

ChatGPT readback should show:

- approval ID
- source preview ID
- source Result Surface ID
- source task reference
- writeback target type
- writeback target reference
- approved write mode
- external side-effect boundary
- forbidden actions
- validation result
- blocked reasons, if any

ChatGPT readback is evidence.

ChatGPT readback is not approval by itself.

## 15. User Approval Boundary

User approval must remain explicit, scoped, and separate.

User approval must approve the exact preview.

User approval must not be inferred from previous conversation.

User approval must not be inferred from commit success.

User approval must not be inferred from push success.

User approval must not be inferred from validation success.

User approval must not be inferred from dry-run preview success.

User approval must not enable automatic writeback by itself.

Any later writeback approval must be scoped to:

- one target
- one preview artifact
- one content body
- one write mode
- one use

Real writeback remains forbidden until a later explicit Strict Lane issue.

## 16. Still Forbidden Behaviors

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

## 17. Next Candidate Step

The next candidate issue should be:

```text
#183 Local Approval Record Validator Candidate
```

#183 may be a Standard Lane local-only implementation candidate.

#183 should validate local approval record JSON only and return a local validation summary.

#183 must not implement real GitHub writeback.

#183 must not write Result Packets.

#183 must not invoke runner / dispatcher / watcher.

#183 should preserve `external_side_effect_allowed=false`.

## 18. Final Boundary Statement

#182 defines local approval record validation planning only.

#182 does not implement approval validation code.

#182 does not implement approval gate code.

#182 does not implement GitHub writeback.

#182 does not write GitHub comments.

#182 does not update GitHub issue bodies.

#182 does not write Result Packets.

#182 does not implement Codex-side action execution.

#182 does not implement runner, dispatcher, watcher, or automation behavior.

#182 does not authorize real write mode.

A future approval record validator must validate local approval record JSON only and return a local validation summary before any future writeback planning may rely on an approval record.

The safe next step is #183 Local Approval Record Validator Candidate.

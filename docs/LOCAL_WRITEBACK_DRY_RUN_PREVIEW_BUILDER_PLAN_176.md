# Local Writeback Dry-Run Preview Builder Plan (#176)

## 1. Purpose

This document defines #176 Local Writeback Dry-Run Preview Builder Plan.

The purpose is to plan how a future local-only Writeback Dry-Run Preview builder should be implemented after the #175 preview samples.

This is a docs-only Fast Lane planning document.

#176 plans a future local-only builder only.

#176 does not implement builder code.

#176 does not implement GitHub writeback.

#176 does not write GitHub comments.

#176 does not write Result Packets.

#176 does not implement runner, dispatcher, watcher, or automation behavior.

## 2. Issue Classification

```yaml
issue_number: 176
issue_role: support
risk_lane: fast
alignment: core_support
value_target: plan how a future local-only Writeback Dry-Run Preview builder should be implemented after preview samples, without implementing GitHub writeback, Result Packet write, runner, dispatcher, watcher, or automation
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

#176 does not change the project direction from readback-first evidence to automatic writeback.

## 4. Source Documents

This plan is based on:

- `docs/LOCAL_WRITEBACK_DRY_RUN_PREVIEW_SAMPLE_175.md`
- `docs/LOCAL_WRITEBACK_DRY_RUN_PREVIEW_PLANNING_174.md`
- `docs/WRITEBACK_TARGET_CONTRACT_VALIDATOR_SUCCESS_DECISION_NOTE_173.md`
- `docs/WRITEBACK_TARGET_CONTRACT_LOCAL_VALIDATION_PLAN_171.md`
- `docs/WRITEBACK_TARGET_CONTRACT_SAMPLE_170.md`
- `docs/BOUNDED_WRITEBACK_TARGET_CONTRACT_PLAN_169.md`

#174 planned a local-only writeback dry-run preview artifact.

#175 provided sample preview artifacts only.

#173 recorded the local-only Writeback Target Contract validator success.

#171 defined the local contract validation gates.

#170 provided sample Writeback Target Contracts.

#169 defined the bounded writeback target contract plan.

## 5. Why A Builder Is Needed

A builder is needed because a validated Writeback Target Contract and a source Result Surface summary must be transformed into a consistent local dry-run preview artifact before ChatGPT readback.

A future builder should produce a local dry-run preview artifact from validated local inputs.

A future builder should make the proposed target, content, safety flags, forbidden actions, and approval requirements visible as local stdout JSON.

A future builder must not perform the write.

A future builder must not infer targets.

A future builder must not perform external side effects.

## 6. Builder Scope

The future builder scope should be local-only.

The future builder should:

- accept local input files only
- require a successful Writeback Target Contract validation summary
- require one explicit target
- combine the validated contract, source Result Surface summary, source task reference, and safe preview content
- produce one local dry-run preview JSON object
- print that preview JSON to stdout
- preserve fail-closed behavior

The future builder must preserve:

```text
external_side_effect_allowed=false
write_mode=dry_run_only
requires_chatgpt_readback=true
requires_user_approval=true
```

The future builder must not:

- write files unless explicitly scoped later
- call GitHub
- write GitHub comments
- update GitHub issue bodies
- write Result Packets
- execute tasks
- commit
- push
- create PRs
- merge
- close issues
- change labels
- invoke runner, dispatcher, watcher, or automation behavior

## 7. Builder Inputs

A future builder input should include:

- validated Writeback Target Contract
- validation summary
- source Result Surface summary
- source task reference
- safe preview content

The validated Writeback Target Contract should provide:

- `writeback_target_type`
- `writeback_target_reference`
- `source_result_surface_id`
- `source_task_reference`
- `write_mode`
- `forbidden_actions`
- `required_safety_flags`

The validation summary should provide:

- `validation_result`
- `required_fields_present`
- `approval_gate_satisfied`
- `chatgpt_readback_gate_satisfied`
- `dry_run_required`
- `forbidden_actions_present`
- `blocked_reasons`
- `external_side_effect_allowed`

The source Result Surface summary should provide enough local review context to build a safe preview without fetching GitHub or writing a Result Packet.

## 8. Builder Output Shape

A future builder output should include:

- `preview_version`
- `preview_id`
- `source_result_surface_id`
- `source_task_reference`
- `writeback_target_type`
- `writeback_target_reference`
- `contract_validation_result`
- `write_mode`
- `preview_content`
- `safe_preview_summary`
- `forbidden_actions`
- `safety_flags`
- `requires_chatgpt_readback`
- `requires_user_approval`
- `external_side_effect_allowed`
- `blocked_reasons`
- `next_recommended_step`
- `created_at`

The output should be one JSON object printed to stdout.

The output should be evidence only.

The output should not be approval.

## 9. Required Validation Gates

A future builder must require these validation gates:

- contract validation summary is present
- contract validation result is success
- exactly one target is present
- target is explicit
- source Result Surface summary is present
- source task reference is present
- safe preview content is present
- `write_mode=dry_run_only`
- forbidden actions are present
- safety flags are present
- `external_side_effect_allowed=false`
- no token-like values are present
- no Authorization headers are present
- no hidden environment variables are present
- no broad scan output is present
- no inferred latest issue is present
- no inferred next issue is present

If any gate fails, the future builder must fail closed and emit a blocked local summary instead of a valid preview.

## 10. Required Safety Flags

A future builder output must preserve safety flags such as:

```yaml
safety_flags:
  external_side_effect_allowed: false
  token_value_printed: false
  token_value_written: false
  authorization_header_included: false
  hidden_environment_value_included: false
  secret_value_included: false
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
```

Safety flags must not be inferred from broad issue scans.

Safety flags must not weaken the approval boundary.

## 11. Valid Builder States

A future builder may return a valid preview only when:

- contract validation result is success
- one explicit target is present
- source Result Surface summary is present
- safe preview content is local and token-free
- `write_mode=dry_run_only`
- `requires_chatgpt_readback=true`
- `requires_user_approval=true`
- `external_side_effect_allowed=false`
- forbidden actions remain listed
- no external write behavior is requested

The valid builder result is still a local dry-run preview only.

The valid builder result is not approval.

The valid builder result does not authorize real writeback.

## 12. Blocked Builder States

A future builder must fail closed if:

- contract validation failed
- contract validation summary is missing
- required inputs are missing
- multiple targets are present
- target is inferred
- `write_mode` is not `dry_run_only`
- GitHub writeback is requested
- Result Packet write is requested
- runner, dispatcher, or watcher behavior is requested
- issue close, label change, PR creation, or merge is requested
- approval chaining is requested
- token-like values appear
- Authorization headers appear
- hidden environment variables appear
- broad scan output appears
- inferred latest issue appears
- inferred next issue appears

Blocked means no valid preview artifact is produced and no external side effect may occur.

## 13. Abort Conditions

A future builder path must abort when:

- local input cannot be read
- input JSON cannot be parsed
- contract validation summary is missing
- contract validation result is not success
- target type is missing
- target reference is missing
- target is ambiguous
- more than one target is present
- target is inferred from latest or next issue
- target comes from broad issue scan output
- source Result Surface summary is missing
- source task reference is missing
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

## 14. CLI Boundary For Future Implementation

The future CLI should be local-only.

It may support a command shape such as:

```powershell
$env:PYTHONPATH='src'; python -m local_runner_bridge.writeback_dry_run_preview_cli --contract-file <path> --result-surface-file <path>
```

The future CLI must:

- read local files only
- print preview JSON to stdout
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

If future stdin mode is added, it must remain local-only and single-input-bounded.

## 15. ChatGPT Readback Boundary

ChatGPT readback must happen after a future builder emits the dry-run preview JSON and before any user approval decision.

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
- next recommended step

ChatGPT readback is evidence.

ChatGPT readback is not approval by itself.

## 16. User Approval Boundary

User approval must remain explicit, scoped, and separate.

A builder success must not imply approval.

A dry-run preview must not imply approval.

A dry-run preview must not chain approval into GitHub writeback, Result Packet write, Codex-side action execution, runner behavior, dispatcher behavior, watcher behavior, commit, push, PR creation, merge, issue close, or label change.

Any later approval must be scoped to:

- one target
- one preview artifact
- one content body
- one write mode
- one use

Real writeback remains forbidden after preview until a later explicit approval issue.

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
#177 Local Writeback Dry-Run Preview Builder Candidate
```

#177 may be a Standard Lane local-only implementation candidate.

#177 must not perform GitHub writeback.

#177 must not write Result Packets.

#177 must not invoke runner, dispatcher, or watcher behavior.

#177 should produce local stdout preview JSON only.

## 19. Final Boundary Statement

#176 defines local Writeback Dry-Run Preview Builder planning only.

#176 does not implement builder code.

#176 does not implement GitHub writeback.

#176 does not write GitHub comments.

#176 does not write Result Packets.

#176 does not implement Codex-side action execution.

#176 does not implement runner, dispatcher, watcher, or automation behavior.

#176 does not authorize real write mode.

A future builder should produce local dry-run preview JSON only after successful Writeback Target Contract validation and local source Result Surface input.

The safe next step is #177 Local Writeback Dry-Run Preview Builder Candidate.

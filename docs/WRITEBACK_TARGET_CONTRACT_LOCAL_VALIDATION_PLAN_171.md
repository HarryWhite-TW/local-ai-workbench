# Writeback Target Contract Local Validation Plan (#171)

## 1. Purpose

This document defines #171 Writeback Target Contract Local Validation Plan.

The purpose is to define how a future local-only validator should check Writeback Target Contracts before any external side effect.

#171 defines local validation planning only.

#171 does not implement validation code.

#171 does not implement GitHub writeback.

#171 does not write Result Packets.

#171 does not write GitHub comments.

#171 does not implement runner, dispatcher, watcher, or automation behavior.

## 2. Issue Classification

```yaml
issue_number: 171
issue_role: support
risk_lane: fast
alignment: core_support
value_target: define how a future local validator should check Writeback Target Contracts before any external side effect, without implementing GitHub writeback, Result Packet write, runner, dispatcher, watcher, or automation
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

A future local validator must validate a contract before any external side effect.

For now, external side effects remain forbidden.

## 4. Source Documents

This plan is based on:

- `docs/BOUNDED_WRITEBACK_TARGET_CONTRACT_PLAN_169.md`
- `docs/WRITEBACK_TARGET_CONTRACT_SAMPLE_170.md`
- `docs/BOUNDED_RESULT_SURFACE_WRITEBACK_PLANNING_168.md`
- `docs/PHASE3_LIVE_FETCH_TO_RESULT_SURFACE_SUCCESS_DECISION_NOTE_167.md`

#169 defined the bounded writeback target contract.

#170 provided sample contracts only.

## 5. Why Local Validation Is Needed

Writeback target contracts introduce a future external side-effect boundary.

Local validation is needed before any future writeback implementation so that contract shape, target explicitness, approval gates, readback gates, dry-run requirements, forbidden actions, and safety flags can be checked without performing GitHub writeback or Result Packet write.

A local validator should make unsafe or ambiguous contracts fail closed before they can reach any external write path.

## 6. Validation Scope

The future local validator should validate local sample contract text or JSON only.

The future validator must not fetch GitHub.

The future validator must not write GitHub comments.

The future validator must not write Result Packets.

The future validator must not write files unless explicitly scoped later.

The future validator must not invoke runner, dispatcher, or watcher behavior.

The future validator must return a local validation summary.

## 7. Required Contract Fields

A future local validator should require:

- `contract_version`
- `writeback_target_type`
- `writeback_target_reference`
- `source_result_surface_id`
- `source_task_reference`
- `approved_by_user`
- `approval_timestamp`
- `chatgpt_readback_completed`
- `dry_run_required`
- `write_mode`
- `safe_preview_required`
- `forbidden_actions`
- `required_safety_flags`
- `abort_conditions`
- `next_recommended_step`

The validator must fail closed when required fields are missing.

The validator must fail closed when multiple targets are present.

The validator must fail closed when the target is inferred rather than explicit.

## 8. Required Safety Fields

Required safety fields should include:

- `exact_single_target_confirmed`
- `chatgpt_readback_completed`
- `explicit_user_approval_present`
- `safe_preview_completed`
- `token_value_printed`
- `token_value_written`
- `broad_issue_scan_performed`
- `next_latest_issue_inference_performed`
- `automatic_issue_close_performed`
- `automatic_label_change_performed`
- `pr_created`
- `merge_performed`
- `approval_chaining_attempted`

The validator must block contracts that request broad scan, next/latest issue inference, issue close, label change, PR creation, merge, or approval chaining.

The validator must block contracts that contain token values, secrets, Authorization headers, or hidden environment values in contract fields.

## 9. Valid States

The only initially valid write mode should be:

```text
dry_run_only
```

The future validator may consider a contract locally valid only when:

- exactly one explicit target is present
- `dry_run_required=true`
- `write_mode="dry_run_only"`
- forbidden actions are present
- no broad scan is requested
- no next/latest issue inference is requested
- no issue close is requested
- no label change is requested
- no PR creation is requested
- no merge is requested
- no token values appear in contract fields
- `external_side_effect_allowed=false`

Real write modes must remain forbidden until explicitly approved in a later issue.

## 10. Blocked States

The future validator must fail closed if:

- `approved_by_user=false`
- `chatgpt_readback_completed=false`
- `dry_run_required` is missing
- `write_mode` is missing
- `write_mode` is not allowed
- forbidden actions are missing
- required safety fields are missing
- broad scan is requested
- next/latest issue inference is requested
- issue close is requested
- label change is requested
- PR creation is requested
- merge is requested
- approval chaining is requested
- token values appear in contract fields

For #171 planning, `approved_by_user=false` and `chatgpt_readback_completed=false` are intentionally blocked states for any real write path. They may still appear in docs-only samples to demonstrate that no write is approved.

## 11. Abort Conditions

The future local validator should abort validation and return blocked when:

- contract JSON or text cannot be parsed
- the target type is missing
- the target reference is missing
- more than one target is present
- the target is inferred
- required fields are missing
- required safety fields are missing
- forbidden actions are missing
- dry-run is not required
- write mode is not `dry_run_only`
- broad scan is requested
- next/latest issue inference is requested
- issue close is requested
- label change is requested
- PR creation is requested
- merge is requested
- token values appear in fields

Abort means no GitHub writeback, no Result Packet write, no file write unless explicitly scoped later, no Codex-side action execution, no runner, no dispatcher, no watcher, no commit, no push, no PR, no merge, no issue close, and no label change.

## 12. Expected Local Validation Summary

A future local validation summary should include fields such as:

```yaml
local_writeback_target_contract_validation_summary:
  validation_result: success | blocked | failed
  contract_version: string | null
  writeback_target_type: github_issue_comment | local_review_file | null
  writeback_target_reference: string | null
  required_fields_present: boolean
  approval_gate_satisfied: boolean
  chatgpt_readback_gate_satisfied: boolean
  dry_run_required: boolean
  forbidden_actions_present: boolean
  blocked_reasons:
    - string
  external_side_effect_allowed: false
```

For now, `external_side_effect_allowed` must remain false.

The summary is evidence only.

The summary is not approval.

## 13. Future Validator Input And Output Shape

Future validator input should be local-only:

```yaml
validator_input:
  source_kind: local_text | local_json
  contract_text_or_json: string
  expected_contract_version: lawb.writeback_target_contract.v0.sample
```

Future validator output should be local-only:

```yaml
validator_output:
  protocol: lawb.writeback_target_contract_local_validation_summary.v1
  validation_result: success | blocked | failed
  external_side_effect_allowed: false
  blocked_reasons:
    - string
  next_recommended_step: chatgpt_review
```

The future validator must not write files unless explicitly scoped later.

The future validator must not write GitHub comments.

The future validator must not write Result Packets.

The future validator must not invoke runner, dispatcher, or watcher behavior.

## 14. Still Forbidden Behaviors

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

#171 does not implement any of these behaviors.

## 15. Next Candidate Step

The next candidate issue should be:

```text
#172 Local Writeback Target Contract Validator Candidate
```

#172 may be a Standard Lane local-only implementation candidate.

#172 must still not implement real GitHub writeback.

#172 must still not write Result Packets.

#172 must still not invoke runner, dispatcher, or watcher behavior.

#172 should validate local sample contract text or JSON only and return a local validation summary.

## 16. Final Boundary Statement

#171 is a docs-only local validation plan.

It does not implement a validator.

It does not run live GitHub fetch.

It does not write GitHub comments.

It does not update GitHub issue bodies.

It does not implement writeback.

It does not write Result Packets.

It does not touch code or tests.

It preserves the boundary that external side effects remain disallowed until a later explicitly approved issue defines and authorizes them.

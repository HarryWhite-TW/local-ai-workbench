# Approval-only End-to-end Smoke Example

## Purpose

This file provides examples for #134 Approval-only End-to-end Smoke.

These examples are documentation only.

These examples do not authorize implementation.

These examples do not authorize runner code.

These examples do not authorize scripts.

These examples do not authorize tests.

These examples do not authorize automatic commit.

These examples do not authorize automatic push.

These examples do not authorize automatic issue close.

These examples do not authorize background watcher behavior.

These examples do not authorize Lv5 full automation.

These examples do not create real task surfaces.

These examples do not create real result surfaces.

These examples do not create GitHub issues.

These examples do not write real Task Packets.

These examples do not write real Result Packets.

These examples do not execute real approval-only smoke.

These examples do not claim approval-only end-to-end execution is already implemented.

## Example 1: valid approval-only end-to-end smoke path

```yaml
approval_only_end_to_end_smoke:
  logical_issue: 134
  mode: proof_only
  user_interaction:
    via_chatgpt_only: true
    user_relayed_long_form_task_content: false
    user_relayed_long_form_result_content: false
    user_issued_direct_long_form_codex_prompt: false
    user_decision_type: approve_reviewbundle
    approval_scope: null
  task_surface:
    role: task_surface
    kind: github_comment
    issue: 134
    comment_id: 1
    active_packet_count: 1
    fallback: false
    fallback_reason: null
  result_surface:
    role: result_surface
    kind: github_comment
    issue: 134
    comment_id: 2
    active_packet_count: 1
    fallback: false
    fallback_reason: null
  checks:
    task_packet_read_from_surface: true
    relay_fetch_valid: true
    bounded_action_respected: true
    result_packet_written_to_result_surface: true
    chatgpt_readback_valid: true
    evidence_not_approval: true
    approval_chaining_attempted: false
  validation:
    expected_result: success
```

This is a valid approval-only smoke path example.

It is not an active smoke run.

## Example 2: valid scoped commit approval metadata

```yaml
approval_scope:
  approval_id: approval-134-example-commit
  source: user_via_chatgpt
  decision: approve_commit
  logical_issue: 134
  phase: approval_only_end_to_end_smoke
  allowed_operation: commit
  allowed_commit_message: "docs: add approval-only end-to-end smoke"
  allowed_files:
    - docs/APPROVAL_ONLY_END_TO_END_SMOKE_134.md
    - docs/examples/approval_only_end_to_end_smoke.example.md
  expires_after_use: true
  approval_chaining_allowed: false
validation:
  expected_result: success
```

This approval only applies to the scoped commit.

It does not approve push.

## Example 3: blocked because user relayed long-form task

```yaml
approval_only_end_to_end_smoke:
  logical_issue: 134
  mode: target_path
  user_interaction:
    via_chatgpt_only: false
    user_relayed_long_form_task_content: true
    user_relayed_long_form_result_content: false
    user_issued_direct_long_form_codex_prompt: true
  validation:
    expected_result: blocked
    failure_reason: "user_relayed_long_form_task_content"
```

The smoke must be blocked because the target path requires task delivery through approved task surface, not user long-form relay.

## Example 4: blocked because user relayed long-form result

```yaml
approval_only_end_to_end_smoke:
  logical_issue: 134
  mode: target_path
  user_interaction:
    via_chatgpt_only: true
    user_relayed_long_form_task_content: false
    user_relayed_long_form_result_content: true
    user_issued_direct_long_form_codex_prompt: false
  validation:
    expected_result: blocked
    failure_reason: "user_relayed_long_form_result_content"
```

The smoke must be blocked because the target path requires result readback from an approved result surface.

## Example 5: blocked because approval is missing

```yaml
approval_required_action:
  logical_issue: 134
  operation: commit
  approval:
    required: true
    present: false
    scope: null
validation:
  expected_result: blocked
  failure_reason: "approval_required_but_missing"
```

High-risk operations require explicit scoped approval.

## Example 6: blocked because approval is reused

```yaml
approval_reuse_attempt:
  approval_id: approval-134-example-commit
  original_operation: commit
  attempted_second_operation: push
  consumed: true
validation:
  expected_result: blocked
  failure_reason: "approval_reuse_attempted"
```

A consumed approval must not be reused.

Commit approval does not approve push.

## Example 7: blocked because approval chaining is attempted

```yaml
approval_chaining_attempt:
  first_decision: approve_commit
  attempted_implied_decision: approve_push
  approval_chaining_allowed: false
validation:
  expected_result: blocked
  failure_reason: "approval_chaining_attempted"
```

Approval chaining is forbidden.

## Example 8: approval-only smoke result summary

```yaml
approval_only_end_to_end_smoke_result:
  protocol: lawb.local_runner.approval_only_end_to_end_smoke_result.v1
  logical_issue: 134
  result: success
  mode: proof_only
  user_interaction:
    via_chatgpt_only: true
    user_relayed_long_form_task_content: false
    user_relayed_long_form_result_content: false
    user_issued_direct_long_form_codex_prompt: false
    user_decision_type: approve_reviewbundle
  task_surface:
    role: task_surface
    kind: github_comment
    issue: 134
    comment_id: 1
  result_surface:
    role: result_surface
    kind: github_comment
    issue: 134
    comment_id: 2
  checks:
    - name: user_only_made_scoped_decision
      passed: true
    - name: task_packet_read_from_surface
      passed: true
    - name: result_packet_read_from_surface
      passed: true
    - name: evidence_not_approval
      passed: true
    - name: approval_chaining_not_attempted
      passed: true
  remaining_bridge_gaps:
    - no_real_runner_implemented
    - no_real_task_surface_publication_performed
    - no_real_result_packet_writeback_performed
    - no_real_approval_only_execution_performed
  stop_condition_reached: true
  next_recommended_action: chatgpt_review
```

This summary proves smoke only.

It is not approval.

It is not a Result Packet v1 replacement.

## Example 9: invalid smoke success treated as approval

```yaml
validation:
  expected_result: failure
  failure_reason: "approval_only_smoke_success_is_not_approval"
invalid_claim:
  smoke_success_approves_commit: true
  smoke_success_approves_push: true
  smoke_success_approves_issue_close: true
```

Smoke success is evidence.

Smoke success is not approval.

## Safety notes

These examples are schema examples.

They are not active task packets.

They are not active result packets.

They are not active smoke runs.

Approval-only end-to-end smoke is not execution.

Approval-only end-to-end smoke is not approval.

A task surface is not approval.

A result surface is not approval.

A successful future result packet is evidence, not approval.

High-risk phases still require explicit user approval through ChatGPT.

Manual fallback must remain labeled.

Manual foreground start must remain labeled as transitional when applicable.

Task and result copy/paste should be reduced by the bridge.

Approval-only End-to-end Smoke does not authorize Lv5 full automation.

# No-copy / No-paste Bridge Smoke Example

## Purpose

This file provides examples for #133 No-copy / No-paste Bridge Smoke.

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

These examples do not claim no-copy / no-paste execution is already implemented.

## Example 1: valid no-copy / no-paste smoke path

```yaml
no_copy_no_paste_smoke:
  logical_issue: 133
  mode: proof_only
  user_relayed_long_form_task_content: false
  user_relayed_long_form_result_content: false
  task_surface:
    role: task_surface
    kind: github_comment
    issue: 133
    comment_id: 1
    active_packet_count: 1
    fallback: false
    fallback_reason: null
  result_surface:
    role: result_surface
    kind: github_comment
    issue: 133
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
  validation:
    expected_result: success
```

This is a valid no-copy / no-paste smoke path example.

It is not an active smoke run.

## Example 2: blocked because user relayed long-form result

```yaml
no_copy_no_paste_smoke:
  logical_issue: 133
  mode: target_path
  user_relayed_long_form_task_content: false
  user_relayed_long_form_result_content: true
  validation:
    expected_result: blocked
    failure_reason: "user_relayed_long_form_result_content"
```

The smoke must be blocked because the target path requires result readback from a result surface.

## Example 3: blocked because task surface is missing

```yaml
no_copy_no_paste_smoke:
  logical_issue: 133
  task_surface: null
  result_surface:
    role: result_surface
    kind: github_comment
    issue: 133
    comment_id: 2
  validation:
    expected_result: blocked
    failure_reason: "task_surface_required"
```

The smoke must fail closed.

## Example 4: blocked because result surface is missing

```yaml
no_copy_no_paste_smoke:
  logical_issue: 133
  task_surface:
    role: task_surface
    kind: github_comment
    issue: 133
    comment_id: 1
  result_surface: null
  validation:
    expected_result: blocked
    failure_reason: "result_surface_required"
```

The smoke must fail closed.

## Example 5: blocked because #114 is primary result sink

```yaml
no_copy_no_paste_smoke:
  logical_issue: 133
  result_surface:
    role: result_surface
    kind: github_issue
    issue: 114
    comment_id: null
    fallback: false
    fallback_reason: null
  validation:
    expected_result: blocked
    failure_reason: "roadmap_anchor_used_as_primary_result_surface_without_fallback_permission"
```

#114 should remain roadmap anchor, fallback, or pointer surface during transition.

It should not become the primary long-term result packet sink.

## Example 6: blocked because fallback lacks reason

```yaml
no_copy_no_paste_smoke:
  logical_issue: 133
  task_surface:
    role: task_surface
    kind: local_file
    path: ".bridge/tasks/task-133.md"
    fallback: true
    fallback_reason: null
  validation:
    expected_result: blocked
    failure_reason: "fallback_reason_required"
```

Fallback must remain explicit.

## Example 7: smoke result summary

```yaml
no_copy_no_paste_bridge_smoke_result:
  protocol: lawb.local_runner.no_copy_no_paste_bridge_smoke_result.v1
  logical_issue: 133
  result: success
  mode: proof_only
  user_relayed_long_form_task_content: false
  user_relayed_long_form_result_content: false
  task_surface:
    role: task_surface
    kind: github_comment
    issue: 133
    comment_id: 1
  result_surface:
    role: result_surface
    kind: github_comment
    issue: 133
    comment_id: 2
  checks:
    - name: task_packet_read_from_surface
      passed: true
    - name: result_packet_read_from_surface
      passed: true
    - name: evidence_not_approval
      passed: true
    - name: user_not_long_form_relay
      passed: true
  remaining_bridge_gaps:
    - no_real_runner_implemented
    - no_real_task_surface_publication_performed
    - no_real_result_packet_writeback_performed
  stop_condition_reached: true
  next_recommended_action: chatgpt_review
```

This summary proves smoke only.

It is not approval.

It is not a Result Packet v1 replacement.

## Example 8: invalid smoke success treated as approval

```yaml
validation:
  expected_result: failure
  failure_reason: "smoke_success_is_not_approval"
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

No-copy / no-paste smoke is not execution.

No-copy / no-paste smoke is not approval.

A task surface is not approval.

A result surface is not approval.

A successful future result packet is evidence, not approval.

High-risk phases still require explicit user approval through ChatGPT.

Manual fallback must remain labeled.

Manual foreground start must remain labeled as transitional when applicable.

Task and result copy/paste should be reduced by the bridge.

No-copy / No-paste Bridge Smoke does not authorize Lv5 full automation.
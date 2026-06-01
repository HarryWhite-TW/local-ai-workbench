# Result Packet Writeback Example

## Purpose

This file provides examples for #132 Result Packet Writeback Proof.

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

These examples do not write real Result Packets.

## Example 1: valid result surface input

```yaml
result_surface_reference:
  role: result_surface
  kind: github_comment
  url: "https://github.com/HarryWhite-TW/local-ai-workbench/issues/132#issuecomment-0000000002"
  issue: 132
  comment_id: 2
  path: null
  sha: null
  active_packet_count: 0
  fallback: false
  fallback_reason: null
task_packet_reference:
  protocol: lawb.local_runner.task_packet.v1
  packet_id: task-132-result-packet-writeback-proof
  logical_issue: 132
  phase: result_packet_writeback_proof
  action_type: docs_only_writeback_proof
  risk_level: medium
validation:
  expected_result: success
```

This is a valid result surface input example.

It is not an active result surface.

## Example 2: active Result Packet inside result surface

```yaml
LOCAL-RUNNER-RESULT-PACKET-V1
BEGIN_RESULT_PACKET
protocol: lawb.local_runner.result_packet.v1
packet_id: result-132-result-packet-writeback-proof
logical_issue: 132
phase: result_packet_writeback_proof
result: success
executor:
  kind: codex_side_process
  mode: proof_only
  runner_code_executed: false
  scripts_created: false
  tests_created: false
task_surface:
  role: task_surface
  kind: github_comment
  url: "https://github.com/HarryWhite-TW/local-ai-workbench/issues/132#issuecomment-0000000001"
  issue: 132
  comment_id: 1
result_surface:
  role: result_surface
  kind: github_comment
  url: "https://github.com/HarryWhite-TW/local-ai-workbench/issues/132#issuecomment-0000000002"
  issue: 132
  comment_id: 2
task_packet:
  protocol: lawb.local_runner.task_packet.v1
  packet_id: task-132-result-packet-writeback-proof
  logical_issue: 132
  phase: result_packet_writeback_proof
  action_type: docs_only_writeback_proof
  risk_level: medium
changed_files:
  - docs/RESULT_PACKET_WRITEBACK_PROOF_132.md
  - docs/examples/result_packet_writeback.example.md
validation:
  expected_changed_files_match: true
  forbidden_operations_attempted: false
  stop_condition_reached: true
high_risk_flags:
  approval_required: false
  approval_consumed: false
  commit_performed: false
  push_performed: false
  issue_closed: false
approval:
  required: false
  consumed: false
  phrase: null
  scope: null
evidence:
  summary: "Result Packet writeback proof candidate produced."
  evidence_not_approval: true
failure:
  reason: null
  blocked_by: null
remaining_bridge_gaps:
  - no_real_writeback_performed
  - no_runner_implemented
next_recommended_action: chatgpt_review
stop_condition:
  reached: true
  next_requires_chatgpt_review: true
  next_requires_user_approval: true
END_RESULT_PACKET
```

The reader should parse only content between BEGIN_RESULT_PACKET and END_RESULT_PACKET.

This result packet is evidence.

It is not approval.

## Example 3: successful ChatGPT readback check

```yaml
chatgpt_readback:
  expected_result: success
  result_surface:
    role: result_surface
    kind: github_comment
    issue: 132
    comment_id: 2
  parsed_result_packet:
    protocol: lawb.local_runner.result_packet.v1
    packet_id: result-132-result-packet-writeback-proof
    logical_issue: 132
    phase: result_packet_writeback_proof
    result: success
  checks:
    - name: protocol_is_result_packet_v1
      passed: true
    - name: evidence_not_approval_true
      passed: true
    - name: stop_condition_reached_true
      passed: true
  next_recommended_action: chatgpt_review
```

This proves readback only.

It does not approve the next phase.

## Example 4: invalid result packet that claims approval

```yaml
validation:
  expected_result: failure
  failure_reason: "result_packet_is_not_approval"
invalid_claim:
  result_packet_approves_commit: true
  result_packet_approves_push: true
  result_packet_approves_issue_close: true
```

A Result Packet is evidence.

A Result Packet is not approval.

## Example 5: invalid missing result target

```yaml
result_writeback_attempt:
  task_packet_reference:
    packet_id: task-132-result-packet-writeback-proof
  result_surface_reference: null
validation:
  expected_result: failure
  failure_reason: "result_surface_required"
```

The writeback must fail closed.

## Example 6: invalid roadmap anchor as primary result surface

```yaml
result_surface_reference:
  role: result_surface
  kind: github_issue
  url: "https://github.com/HarryWhite-TW/local-ai-workbench/issues/114"
  issue: 114
  comment_id: null
  path: null
  sha: null
  active_packet_count: 1
  fallback: false
  fallback_reason: null
validation:
  expected_result: failure
  failure_reason: "roadmap_anchor_used_as_primary_result_surface_without_fallback_permission"
```

#114 should not be used as the primary long-term result packet sink.

If #114 is used during transition, it must be labeled fallback or pointer-only.

## Example 7: invalid writeback success treated as next-phase approval

```yaml
validation:
  expected_result: failure
  failure_reason: "writeback_success_is_not_next_phase_approval"
invalid_claim:
  writeback_success_approves_next_phase: true
  writeback_success_approves_commit: true
  writeback_success_approves_push: true
```

Writeback success is not approval.

## Safety notes

These examples are schema examples.

They are not active result packets unless placed in an approved active result surface.

Result Packet writeback is not execution.

Result Packet writeback is not approval.

A task surface is not approval.

A result surface is not approval.

A successful future result packet is evidence, not approval.

High-risk phases still require explicit user approval through ChatGPT.

Manual fallback must remain labeled.

Manual foreground start must remain labeled as transitional when applicable.

Task and result copy/paste should be reduced by the bridge.

Result Packet Writeback Proof does not authorize Lv5 full automation.
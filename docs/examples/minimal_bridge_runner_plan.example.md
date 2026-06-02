# Minimal Bridge Runner Plan Example

## Purpose

This file provides examples for #136 Minimal Bridge Runner Plan.

These examples are documentation only.

These examples do not authorize implementation.

These examples do not authorize runner code.

These examples do not authorize scripts.

These examples do not authorize tests.

These examples do not authorize Codex-side action.

These examples do not authorize Result Packet writeback.

These examples do not authorize GitHub writes.

These examples do not authorize commit.

These examples do not authorize push.

These examples do not authorize full automation.

These examples do not authorize Lv5.

These examples do not authorize always-on watcher behavior.

These examples are not active runner tasks.

## Example 1: valid read-only task surface resolver input

```yaml
input:
  task_surface_reference:
    role: task_surface
    kind: github_comment
    repository: HarryWhite-TW/local-ai-workbench
    issue: 136
    comment_id: 1
    url: "https://github.com/HarryWhite-TW/local-ai-workbench/issues/136#issuecomment-0000000001"
    active_packet_count: 1
    fallback: false
    fallback_reason: null
  expected:
    protocol: lawb.local_runner.task_packet.v1
    logical_issue: 136
    phase: minimal_bridge_runner_plan
validation:
  expected_result: valid_input
```

This input is explicit and single-surface.

It is not an active runner task.

## Example 2: valid local validation summary

```yaml
local_validation_summary:
  protocol: lawb.local_runner.task_surface_validation_summary.v1
  result: success
  slice_name: read_only_task_surface_resolver_and_packet_validator
  task_surface_reference_checked: true
  active_task_packet_count: 1
  task_packet_protocol_valid: true
  task_packet_boundary_markers_valid: true
  logical_issue_matches_expected: true
  phase_matches_expected: true
  required_fields_present: true
  codex_side_action_executed: false
  result_packet_written: false
  github_write_performed: false
  commit_performed: false
  push_performed: false
  next_recommended_action: chatgpt_review
validation:
  expected_result: valid_summary
```

The summary is evidence only.

It is not approval.

## Example 3: blocked because task surface reference is missing

```yaml
input:
  task_surface_reference: null
validation:
  expected_result: blocked
  failure_reason: task_surface_reference_missing
```

The slice must fail closed.

## Example 4: blocked because multiple active task packets exist

```yaml
input:
  task_surface_reference:
    role: task_surface
    active_packet_count: 2
validation:
  expected_result: blocked
  failure_reason: multiple_active_task_packets
```

The slice must validate exactly one active Task Packet v1.

## Example 5: blocked because Task Packet boundary markers are missing

```yaml
task_packet_surface:
  contains_begin_task_packet: false
  contains_end_task_packet: false
validation:
  expected_result: blocked
  failure_reason: task_packet_boundary_markers_missing
```

The slice must parse only content inside valid Task Packet v1 boundary markers.

## Example 6: blocked because protocol is invalid

```yaml
parsed_task_packet:
  protocol: lawb.local_runner.task_packet.v0
validation:
  expected_result: blocked
  failure_reason: invalid_task_packet_protocol
```

The protocol must be Task Packet v1.

## Example 7: blocked because approval object is missing

```yaml
parsed_task_packet:
  approval: null
validation:
  expected_result: blocked
  failure_reason: approval_object_missing
```

The approval object must exist even when approval is not consumed.

## Example 8: blocked because result_target is missing

```yaml
parsed_task_packet:
  result_target: null
validation:
  expected_result: blocked
  failure_reason: result_target_missing
```

The result target must exist before any future bounded action can be considered.

## Example 9: invalid claim that #136 planning authorizes implementation

```yaml
invalid_claim:
  planning_authorizes_runner_implementation: true
  planning_authorizes_scripts: true
  planning_authorizes_tests: true
validation:
  expected_result: failure
  failure_reason: planning_is_not_implementation_approval
```

#136 planning does not authorize implementation.

## Example 10: invalid claim that validation success authorizes commit or push

```yaml
invalid_claim:
  validation_success_authorizes_commit: true
  validation_success_authorizes_push: true
validation:
  expected_result: failure
  failure_reason: validation_success_is_not_approval
```

Validation success is evidence.

Validation success is not approval.

## Safety notes

These examples are schema examples.

They are not active task packets.

They are not active result packets.

They are not active runner tasks.

They do not authorize Codex-side action.

They do not authorize Result Packet writeback.

They do not authorize GitHub writes.

They do not authorize commit.

They do not authorize push.

They do not authorize full automation.

They do not authorize Lv5.

They do not authorize always-on watcher behavior.

# Read-only Validator Implementation Plan Example

## Purpose

This file provides examples for #137 Read-only Validator Implementation Plan.

These examples are documentation only.

These examples do not authorize implementation.

These examples do not authorize validator code.

These examples do not authorize runner code.

These examples do not authorize scripts.

These examples do not authorize tests.

These examples do not authorize Codex-side action.

These examples do not authorize Result Packet writeback.

These examples do not authorize GitHub writes.

These examples do not authorize commit.

These examples do not authorize push.

These examples are not active runner tasks.

## Example 1: proposed explicit task surface reference input

```yaml
validator_input:
  task_surface_reference:
    role: task_surface
    kind: github_comment
    repository: HarryWhite-TW/local-ai-workbench
    issue: 137
    comment_id: 1
    url: "https://github.com/HarryWhite-TW/local-ai-workbench/issues/137#issuecomment-0000000001"
    active_packet_count: 1
    fallback: false
    fallback_reason: null
  expected:
    protocol: lawb.local_runner.task_packet.v1
    logical_issue: 137
    phase: read_only_validator_implementation_plan
validation:
  expected_result: valid_input
```

This input is a proposed schema example.

It is not an active runner task.

## Example 2: proposed local validation summary success

```yaml
local_validation_summary:
  protocol: lawb.local_runner.task_surface_validation_summary.v1
  result: success
  slice_name: read_only_task_surface_resolver_and_packet_validator
  task_surface_reference_checked: true
  active_task_packet_count: 1
  task_packet_boundary_markers_valid: true
  task_packet_protocol_valid: true
  logical_issue_matches_expected: true
  phase_matches_expected: true
  required_fields_present: true
  codex_side_action_executed: false
  repo_files_modified: false
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

## Example 3: blocked missing task surface reference

```yaml
validator_input:
  task_surface_reference: null
validation:
  expected_result: blocked
  failure_reason: task_surface_reference_missing
```

The validator must fail closed.

## Example 4: blocked multiple active packets

```yaml
validator_input:
  task_surface_reference:
    role: task_surface
    active_packet_count: 2
validation:
  expected_result: blocked
  failure_reason: multiple_active_task_packets
```

Exactly one active Task Packet v1 is required.

## Example 5: blocked missing Task Packet boundary markers

```yaml
task_packet_surface:
  contains_begin_task_packet: false
  contains_end_task_packet: false
validation:
  expected_result: blocked
  failure_reason: task_packet_boundary_markers_missing
```

Task Packet boundary markers are required.

## Example 6: blocked invalid protocol

```yaml
parsed_task_packet:
  protocol: lawb.local_runner.task_packet.v0
validation:
  expected_result: blocked
  failure_reason: invalid_task_packet_protocol
```

The protocol must be Task Packet v1.

## Example 7: blocked missing required fields

```yaml
parsed_task_packet:
  allowed_files: null
  forbidden_operations: null
  approval: null
  result_target: null
  stop_condition: null
validation:
  expected_result: blocked
  failure_reason: required_fields_missing
```

Required fields must be present.

## Example 8: invalid claim that #137 planning authorizes implementation

```yaml
invalid_claim:
  planning_authorizes_validator_implementation: true
  planning_authorizes_runner_code: true
  planning_authorizes_tests: true
validation:
  expected_result: failure
  failure_reason: planning_is_not_implementation_approval
```

#137 planning does not authorize implementation.

## Example 9: invalid claim that validation success authorizes execution / commit / push

```yaml
invalid_claim:
  validation_success_authorizes_execution: true
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

They do not authorize validator implementation.

They do not authorize runner code.

They do not authorize scripts.

They do not authorize tests.

They do not authorize Codex-side action.

They do not authorize Result Packet writeback.

They do not authorize GitHub writes.

They do not authorize commit.

They do not authorize push.

# Read-only Validator Implementation Plan 137

## Purpose

This document defines #137 Read-only Validator Implementation Plan.

The purpose is to plan a future implementation for the first read-only validator slice:

```text
read_only_task_surface_resolver_and_packet_validator
```

This is an implementation plan.

This is not implementation.

This document does not create validator code.

This document does not create runner code.

This document does not create scripts.

This document does not create tests.

This document does not execute a runner.

This document does not execute a dispatcher.

This document does not execute runtime smoke.

This document does not execute Codex-side action.

This document does not write a Result Packet.

This document does not perform GitHub writes except the required #114 ReviewBundle audit comment.

This document does not authorize commit.

This document does not authorize push.

This document does not authorize always-on watcher behavior.

This document does not authorize Lv5.

This document does not authorize full automation.

## Relationship to #136

#136 defined the minimal bridge runner plan for `read_only_task_surface_resolver_and_packet_validator`.

#136 was planning-only.

#136 set `implementation_allowed_in_136=false`.

#136 defined the input as one explicit task surface reference.

#136 defined the output as a local validation summary.

#136 forbids Codex-side action, Result Packet write, GitHub write, commit, push, unrelated issue scan, always-on watcher behavior, Lv5, and full automation.

#137 carries that slice forward into implementation planning only.

#137 does not authorize implementation.

## Proposed implementation files

The proposed implementation files for a future approved implementation package are:

```yaml
proposed_files:
  - src/local_runner_bridge/task_surface_resolver.py
  - src/local_runner_bridge/task_packet_validator.py
  - tests/local_runner_bridge/test_task_packet_validator.py
```

These files are proposed only.

These files are not created in #137.

These files must not be created without a separate user-approved implementation task.

## Forbidden files and operations

#137 must not create or modify implementation files.

Forbidden files in #137 include:

```yaml
forbidden_files_in_137:
  - src/local_runner_bridge/task_surface_resolver.py
  - src/local_runner_bridge/task_packet_validator.py
  - tests/local_runner_bridge/test_task_packet_validator.py
  - scripts/local_runner_bridge_v0.py
```

Forbidden operations in #137 include:

```yaml
forbidden_operations_in_137:
  - create_validator_code
  - create_runner_code
  - create_scripts
  - create_tests
  - execute_runner
  - execute_dispatcher
  - execute_runtime_smoke
  - execute_codex_side_action
  - write_result_packet
  - create_github_comment_except_114_audit
  - create_github_issue
  - commit
  - push
  - scan_unrelated_issues
  - start_always_on_watcher
  - enable_lv5
  - enable_full_automation
```

## Input contract

The proposed validator input is an explicit task surface reference.

Recommended shape:

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
```

The validator must not infer task surfaces from broad issue history.

The validator must not scan unrelated issues.

The validator must not use #114 as a primary task packet sink unless a future approved implementation package explicitly labels fallback behavior.

## Output contract

The proposed validator output is a local validation summary.

Recommended shape:

```yaml
local_validation_summary:
  protocol: lawb.local_runner.task_surface_validation_summary.v1
  result: success | blocked | failure
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
```

The local validation summary is evidence only.

The local validation summary is not approval.

The local validation summary is not a Result Packet.

## Validation responsibilities

The proposed validator should perform read-only Task Packet v1 validation.

Validation responsibilities:

```yaml
validation_responsibilities:
  - task_surface_reference_present
  - task_surface_reference_explicit
  - task_surface_role_is_task_surface
  - active_packet_count_is_one
  - task_packet_boundary_markers_present
  - task_packet_boundary_markers_well_formed
  - protocol_is_task_packet_v1
  - logical_issue_matches_expected
  - phase_matches_expected
  - allowed_files_present
  - forbidden_operations_present
  - approval_object_present
  - result_target_present
  - stop_condition_present
```

The validator may parse and validate.

The validator must not execute.

The validator must not mutate.

The validator must not approve.

## Failure behavior

The proposed validator must fail closed when:

* task surface reference is missing
* task surface reference is ambiguous
* task surface role is not `task_surface`
* active task packet count is zero
* active task packet count is greater than one
* Task Packet boundary markers are missing
* Task Packet boundary markers are malformed
* protocol is missing
* protocol is not Task Packet v1
* logical_issue does not match expected value
* phase does not match expected value
* allowed_files is missing
* forbidden_operations is missing
* approval object is missing
* result_target is missing
* stop_condition is missing
* unrelated issue scan would be required
* validation success is treated as execution approval
* validation success is treated as commit approval
* validation success is treated as push approval

## Minimal tests to implement later

A future approved implementation package should add tests for:

```yaml
future_test_cases:
  - valid_explicit_task_surface_reference
  - valid_local_validation_summary
  - blocked_missing_task_surface_reference
  - blocked_multiple_active_packets
  - blocked_missing_task_packet_boundary_markers
  - blocked_invalid_protocol
  - blocked_missing_required_fields
  - validation_success_does_not_authorize_execution
  - validation_success_does_not_authorize_commit_or_push
```

These tests are not created in #137.

## Non-goals

#137 is not validator implementation.

#137 is not runner implementation.

#137 is not script creation.

#137 is not test creation.

#137 is not runtime smoke.

#137 is not Codex-side action execution.

#137 is not Result Packet writeback.

#137 is not GitHub issue creation.

#137 is not broad issue scanning.

#137 is not always-on watcher behavior.

#137 is not Lv5.

#137 is not full automation.

## Implementation approval boundary

#137 planning does not authorize implementation.

#137 planning does not authorize creating the proposed files.

#137 planning does not authorize commit.

#137 planning does not authorize push.

#137 planning does not authorize Codex-side action.

#137 planning does not authorize Result Packet writeback.

Implementation requires a separate user-approved implementation package.

Validation success is evidence.

Validation success is not approval.

## Completion criteria

#137 is complete when this document defines:

* purpose
* relationship to #136
* proposed implementation files
* forbidden files and operations
* input contract
* output contract
* validation responsibilities
* failure behavior
* minimal tests to implement later
* non-goals
* implementation approval boundary
* completion criteria
* current status

#137 is not complete if it creates validator code.

#137 is not complete if it creates runner code.

#137 is not complete if it creates scripts.

#137 is not complete if it creates tests.

#137 is not complete if it executes Codex-side action.

#137 is not complete if it writes a Result Packet.

#137 is not complete if it authorizes always-on watcher behavior, Lv5, or full automation.

## Current status

Read-only Validator Implementation Plan is defined as a docs-only implementation planning artifact.

The proposed slice is `read_only_task_surface_resolver_and_packet_validator`.

The current status is implementation_plan_only.

Implementation is not authorized in #137.

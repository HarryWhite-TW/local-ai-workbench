# Implementation Readiness Gate Example

## Purpose

This file provides examples for #135 Implementation Readiness Gate.

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

## Example 1: current readiness decision

```yaml
readiness_decision:
  ready_for_full_automation: false
  ready_for_lv5: false
  ready_for_always_on_watcher: false
  ready_for_broad_issue_scan: false
  ready_for_runner_implementation_now: false
  ready_for_minimal_implementation_planning: true
  recommended_next_issue: 136
  recommended_next_issue_title: "Minimal Bridge Runner Plan"
validation:
  expected_result: ready_for_minimal_planning
```

This means the next step is planning, not implementation.

## Example 2: valid minimal first slice candidate

```yaml
minimal_first_slice_candidate:
  name: read_only_task_surface_resolver_and_packet_validator
  implementation_allowed_in_135: false
  planning_allowed_in_136: true
  inputs:
    - one_explicit_task_surface_reference
  outputs:
    - local_validation_summary
  allowed_behavior:
    - validate_task_packet_boundary_markers
    - validate_task_packet_protocol
    - validate_logical_issue_and_phase
    - validate_allowed_files_and_forbidden_operations
    - validate_approval_object_exists
    - validate_result_target_exists
  forbidden_behavior:
    - execute_codex_side_action
    - modify_repo_files
    - write_result_packet
    - create_github_comments
    - create_github_issues
    - commit
    - push
    - scan_unrelated_issues
    - run_always_on_watcher
validation:
  expected_result: valid_planning_candidate
```

This is a planning candidate only.

## Example 3: blocked because implementation starts in #135

```yaml
readiness_gate_violation:
  logical_issue: 135
  runner_code_created: true
  scripts_created: true
validation:
  expected_result: blocked
  failure_reason: "implementation_started_in_readiness_gate"
```

#135 must not implement the runner.

## Example 4: blocked because full automation is authorized

```yaml
readiness_gate_violation:
  ready_for_full_automation: true
  ready_for_lv5: true
  always_on_watcher_authorized: true
validation:
  expected_result: blocked
  failure_reason: "full_automation_not_authorized"
```

Full automation is not authorized.

## Example 5: Tier 0 must block

```yaml
review_issue:
  tier: 0
  name: push_without_approval
  description: "A push was performed without explicit user approval."
validation:
  expected_result: blocked
  repair_strategy: stop_and_escalate_to_chatgpt
```

Tier 0 issues must block.

## Example 6: Tier 1 minimal repair

```yaml
review_issue:
  tier: 1
  name: missing_h1_when_h1_is_acceptance_criteria
  description: "A required H1 marker is missing from a machine-read document."
validation:
  expected_result: minimal_repair_allowed
  repair_strategy: repair_only_the_missing_marker
```

Tier 1 may block, but repair must be minimal.

## Example 7: Tier 2 non-blocking

```yaml
review_issue:
  tier: 2
  name: wording_can_be_clearer
  description: "The wording could be clearer, but protocol and safety boundaries are intact."
validation:
  expected_result: non_blocking
  repair_strategy: do_not_open_standalone_repair_cycle
```

Tier 2 must not block progress.

## Example 8: invalid readiness as implementation approval

```yaml
invalid_claim:
  readiness_gate_approves_implementation: true
  readiness_gate_approves_commit: true
  readiness_gate_approves_push: true
validation:
  expected_result: failure
  failure_reason: "readiness_is_not_approval"
```

Readiness is not approval.

## Safety notes

These examples are schema examples.

They are not active implementation tasks.

They are not active runner plans.

They are not active task packets.

They are not active result packets.

Implementation readiness is not implementation.

Implementation readiness is not approval.

A readiness gate does not authorize commit.

A readiness gate does not authorize push.

A readiness gate does not authorize full automation.

High-risk phases still require explicit user approval through ChatGPT.

Tier 2 issues must not block the mainline.

Implementation Readiness Gate does not authorize Lv5 full automation.

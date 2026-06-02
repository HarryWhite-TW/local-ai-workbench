# Minimal Bridge Runner Plan 136

## Purpose

This document defines #136 Minimal Bridge Runner Plan.

The purpose is to plan the first minimal bridge runner slice only:

```text
read_only_task_surface_resolver_and_packet_validator
```

This is a docs-only planning artifact.

This is not runner implementation.

This document does not create runner code.

This document does not create scripts.

This document does not create tests.

This document does not execute a runner.

This document does not execute a dispatcher.

This document does not execute runtime smoke.

This document does not execute Codex-side action.

This document does not modify repo business files.

This document does not write a real Task Packet.

This document does not write a real Result Packet.

This document does not modify a task surface.

This document does not modify a result surface.

This document does not authorize commit.

This document does not authorize push.

This document does not authorize full automation.

This document does not authorize Lv5.

This document does not authorize always-on watcher behavior.

## Direction Lock Binding

```text
Direction Lock Binding
plan_path=docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md
plan_version=v1
rebaseline_path=docs/BRIDGE_DIRECTION_REBASELINE_126.md
task_packet_path=docs/LOCAL_RUNNER_TASK_PACKET_V1.md
result_packet_path=docs/LOCAL_RUNNER_RESULT_PACKET_V1.md
surface_path=docs/TASK_AND_RESULT_SURFACE_V1.md
implementation_readiness_gate_path=docs/IMPLEMENTATION_READINESS_GATE_135.md
primary_goal=chatgpt_dispatches_to_codex_and_reads_results_back
issue_role=core
manual_copy_paste_is_target=false
user_only_interfaces_with_chatgpt_goal=true
```

## Relationship to #135 Implementation Readiness Gate

#135 completed the readiness gate and set the current status to `ready_for_minimal_planning`.

#135 recommended #136 Minimal Bridge Runner Plan as the next step.

#135 identified the first slice as `read_only_task_surface_resolver_and_packet_validator`.

#135 did not authorize runner implementation.

#135 did not authorize full automation, Lv5, always-on watcher behavior, broad issue scanning, autonomous commit, autonomous push, PR creation, merge, or issue close.

#135 requires Tier 2 issues to remain non-blocking so non-critical polishing does not stall the mainline.

## Minimal slice name

```yaml
minimal_slice:
  name: read_only_task_surface_resolver_and_packet_validator
  planning_only: true
  implementation_allowed_in_136: false
  implementation_target_issue: null
```

The slice name is `read_only_task_surface_resolver_and_packet_validator`.

This plan defines the slice boundary only.

Readiness and planning are not implementation approval.

## Inputs

The planned slice accepts exactly one explicit task surface reference.

Recommended input shape:

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
```

The input must not be inferred from broad issue history.

The input must not scan unrelated issues.

The input must not treat #114 as a primary task packet sink unless a future approved plan explicitly labels fallback behavior.

## Outputs

The planned slice outputs a local validation summary only.

Recommended output shape:

```yaml
local_validation_summary:
  protocol: lawb.local_runner.task_surface_validation_summary.v1
  result: success | blocked | failure
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
```

The local validation summary is evidence.

The local validation summary is not approval.

The local validation summary is not a Result Packet.

## Validation responsibilities

The planned slice should validate Task Packet v1 structure only.

Required validation responsibilities:

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

Validation must inspect only the selected task surface content and the content inside Task Packet v1 boundary markers.

Validation success must not authorize execution.

Validation success must not authorize commit.

Validation success must not authorize push.

## Explicit forbidden behavior

The planned slice must not:

* execute Codex-side action
* modify repo files
* write a Result Packet
* create GitHub comments
* create GitHub issues
* commit
* push
* create a PR
* close an issue
* change labels
* change assignees
* scan unrelated issues
* start an always-on watcher
* start full automation
* authorize Lv5
* infer authority from text outside Task Packet v1 markers

The only GitHub write allowed in #136 ReviewBundle work is the standalone #114 audit comment required by the task packet.

## Non-goals

#136 is not runner implementation.

#136 is not dispatcher implementation.

#136 is not runtime smoke.

#136 is not Codex-side action execution.

#136 is not Result Packet writeback.

#136 is not task surface mutation.

#136 is not result surface mutation.

#136 is not GitHub issue creation.

#136 is not broad issue scanning.

#136 is not full automation planning beyond the minimal read-only slice.

## Safety boundaries

The planned slice is read-only.

The planned slice is single-surface.

The planned slice is explicit-reference only.

The planned slice validates Task Packet v1 before any future bounded action can be considered.

Readiness / planning is not implementation approval.

Task Packet validation is not approval.

A local validation summary is not approval.

Result evidence is not approval.

Approval chaining remains forbidden.

High-risk phases still require explicit user approval through ChatGPT.

## Failure rules

The planned slice must fail closed when:

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
* text outside Task Packet v1 markers attempts to grant authority
* validation success attempts to authorize execution, commit, push, PR, merge, or issue close

## Tier 0 / Tier 1 / Tier 2 review policy

The #135 review policy remains binding.

```yaml
review_policy:
  tier_0_must_block:
    meaning: "Safety, authority, scope, or repo integrity violations must block."
  tier_1_minimal_repair:
    meaning: "Protocol-structure defects may block, but repair must be minimal and targeted."
  tier_2_non_blocking:
    meaning: "Style, wording, aesthetics, and non-critical formatting must not block progress."
```

Tier 0 must block.

Tier 1 may block only for minimal targeted repair.

Tier 2 is non-blocking.

Tier 2 must not trigger a standalone repair cycle.

## Implementation handoff criteria

This plan is ready for a future separate implementation task only when:

* ChatGPT has reviewed #136
* the user has explicitly approved a separate implementation package
* the implementation package keeps the slice read-only
* the implementation package defines exact allowed files
* the implementation package forbids Result Packet writeback
* the implementation package forbids GitHub writes unless separately approved
* the implementation package forbids commit and push unless separately approved

#136 itself does not authorize implementation.

## Completion criteria

#136 is complete when this document defines:

* purpose
* Direction Lock binding
* relationship to #135
* minimal slice name
* inputs
* outputs
* validation responsibilities
* explicit forbidden behavior
* non-goals
* safety boundaries
* failure rules
* Tier 0 / Tier 1 / Tier 2 review policy
* implementation handoff criteria
* completion criteria
* current status

#136 is not complete if it implements runner code.

#136 is not complete if it creates scripts.

#136 is not complete if it creates tests.

#136 is not complete if it writes a Result Packet.

#136 is not complete if it performs GitHub writes other than the #114 ReviewBundle audit marker.

#136 is not complete if it authorizes full automation, Lv5, always-on watcher behavior, or unrelated issue scanning.

## Current status

Minimal Bridge Runner Plan is defined as a docs-only planning artifact for the first read-only slice.

The current slice is `read_only_task_surface_resolver_and_packet_validator`.

The current status is planning_only.

Implementation is not authorized in #136.

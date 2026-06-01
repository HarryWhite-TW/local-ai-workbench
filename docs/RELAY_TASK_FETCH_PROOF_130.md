# Relay Task Fetch Proof 130

## Purpose

This document defines #130 Relay Task Fetch Proof.

The purpose is to prove, at the protocol and documentation level, that a future relay, runner, or Codex-side process can read a Task Packet v1 from an approved Task Surface v1 location and validate it before any bounded action occurs.

This proof is a bridge design artifact.

This proof does not implement a runner.

This proof does not execute a runner.

This proof does not create scripts.

This proof does not create tests.

This proof does not create a GitHub issue.

This proof does not create a GitHub comment.

This proof does not modify a real task surface.

This proof does not modify a real result surface.

This proof does not authorize automatic commit.

This proof does not authorize automatic push.

This proof does not authorize automatic issue close.

This proof does not authorize automatic PR creation.

This proof does not authorize automatic merge.

This proof does not authorize background watcher behavior.

This proof does not authorize always-on polling.

This proof does not authorize broad issue scanning.

This proof does not authorize Lv5 full automation.

## Direction Lock Binding

```text
Direction Lock Binding
plan_path=docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md
plan_version=v1
rebaseline_path=docs/BRIDGE_DIRECTION_REBASELINE_126.md
task_packet_path=docs/LOCAL_RUNNER_TASK_PACKET_V1.md
result_packet_path=docs/LOCAL_RUNNER_RESULT_PACKET_V1.md
surface_path=docs/TASK_AND_RESULT_SURFACE_V1.md
publication_proof_path=docs/CHATGPT_TASK_PACKET_PUBLICATION_PROOF_129.md
primary_goal=chatgpt_dispatches_to_codex_and_reads_results_back
issue_role=core
manual_copy_paste_is_target=false
must_emit_plan_read_audit=true
```

## Relationship to the bridge

The target bridge direction is:

```text
User
-> ChatGPT
-> approved task surface containing Task Packet v1
-> relay / runner / Codex-side process fetches and validates task packet
-> bounded Codex or bounded executor action
-> approved result surface containing Result Packet v1
-> ChatGPT readback and review
-> user key approval decisions through ChatGPT
```

The user should not be the long-form task relay.

The user should not be the long-form result relay.

Manual copy/paste is fallback.

Manual foreground start may remain transitional.

This proof exists to reduce manual task relay by defining how a relay can read the task packet from an approved surface.

## Relationship to Task Packet v1

Task Packet v1 defines the structured task input.

Relay Task Fetch Proof verifies that a future relay can read and validate:

* protocol marker
* boundary markers
* packet ID
* logical issue
* phase
* action type
* risk level
* repository
* branch
* surface binding
* result target
* allowed files
* forbidden operations
* approval object
* payload object
* validation object
* stop condition

This proof does not broaden Task Packet v1 authority.

Natural language outside the active packet must not create execution authority.

## Relationship to Result Packet v1

Result Packet v1 defines the structured output that should be written after a bounded task packet is executed.

Relay task fetch must verify that the task packet contains a result target compatible with Result Packet v1.

Relay task fetch does not write the result packet.

Relay task fetch does not approve the result.

Relay task fetch does not authorize the next phase.

A successful future result packet is evidence, not approval.

## Relationship to Task and Result Surface v1

Task and Result Surface v1 defines where task packets and result packets live.

Relay task fetch must read from exactly one approved task surface.

Relay task fetch must not treat the roadmap anchor as a primary task packet sink unless explicitly marked as fallback.

Relay task fetch must fail closed when active_packet_count is greater than 1.

Relay task fetch must fail closed when fallback is true but fallback_reason is missing.

Relay task fetch must preserve surface role boundaries.

## Relationship to #129 Publication Proof

#129 proves ChatGPT can author a publication-ready task packet candidate.

#130 proves that a future relay can fetch and validate such a task packet from an approved surface.

#129 is task publication proof.

#130 is task fetch proof.

#130 does not execute the task.

#130 does not create a real task surface.

#130 does not create a real result surface.

## Proof target

The proof target is a relay-readable task packet fetch process.

A valid relay task fetch proof must show that a future relay can:

1. locate an approved task surface
2. read the task surface content
3. find exactly one active Task Packet v1
4. parse only content between Task Packet v1 boundary markers
5. verify the Task Packet v1 protocol
6. verify the surface binding object
7. verify the result target object
8. verify logical issue / phase / action type / risk level
9. verify allowed files and forbidden operations
10. verify approval semantics
11. verify validation expectations
12. verify stop condition
13. fail closed on ambiguity or invalid packet structure
14. emit a task fetch result summary for ChatGPT review

## Non-goals

#130 is not runner implementation.

#130 is not script implementation.

#130 is not test implementation.

#130 is not Codex-side action execution.

#130 is not GitHub result writeback.

#130 is not no-copy/no-paste smoke.

#130 is not approval-only end-to-end smoke.

#130 does not create a real task issue.

#130 does not create a real result issue.

#130 does not close #114.

#130 does not change labels.

#130 does not authorize implementation.

## Relay task fetch stages

A future relay task fetch should follow these conceptual stages:

```text
receive task surface reference
-> read surface metadata
-> read surface content
-> validate surface role and kind
-> count active task packets
-> parse active task packet boundaries
-> validate Task Packet v1 protocol
-> validate task packet fields
-> validate risk and approval constraints
-> validate result target
-> emit fetch proof summary
-> stop before execution
```

This proof stops before any bounded action.

## Fetch input contract

A future relay task fetch should receive a task surface binding.

Recommended shape:

```yaml
task_surface_reference:
  role: task_surface
  kind: github_comment
  url: "https://github.com/HarryWhite-TW/local-ai-workbench/issues/130#issuecomment-0000000001"
  issue: 130
  comment_id: 1
  path: null
  sha: null
  active_packet_count: 1
  fallback: false
  fallback_reason: null
expected:
  repository: HarryWhite-TW/local-ai-workbench
  branch: master
  logical_issue: 130
  phase: relay_task_fetch_proof
  action_type: docs_only_fetch_proof
  risk_level: medium
```

This input contract is a design example only.

It is not an active task surface.

## Active packet detection

A future relay must search for Task Packet v1 markers:

```text
LOCAL-RUNNER-TASK-PACKET-V1
BEGIN_TASK_PACKET
...
END_TASK_PACKET
```

The relay must parse only content between BEGIN_TASK_PACKET and END_TASK_PACKET.

If the selected task surface contains zero active task packets, the fetch result must be failure.

If the selected task surface contains more than one active task packet, the fetch result must be failure.

If the markers are malformed, the fetch result must be failure.

If the protocol is missing, the fetch result must be failure.

## Required validation checks

A future relay task fetch should validate:

```yaml
required_checks:
  - surface_role_is_task_surface
  - surface_kind_supported
  - active_packet_count_is_one
  - boundary_markers_present
  - protocol_is_task_packet_v1
  - packet_id_present
  - logical_issue_matches_expected
  - phase_matches_expected
  - action_type_supported
  - risk_level_supported
  - repository_matches_expected
  - branch_matches_expected
  - allowed_files_present
  - forbidden_operations_present
  - approval_object_present
  - payload_object_present
  - validation_object_present
  - result_target_present
  - stop_condition_present
  - no_authority_from_outside_packet
```

All required checks must pass before any bounded action can be considered.

## Approval boundary

Relay task fetch does not approve execution.

Relay task fetch does not approve commit.

Relay task fetch does not approve push.

Relay task fetch does not approve issue close.

Relay task fetch only proves the task packet can be read and validated.

High-risk phases still require explicit user approval through ChatGPT.

Approval chaining remains forbidden.

## Fetch result summary

A future relay task fetch should emit a fetch result summary.

Recommended shape:

```yaml
relay_task_fetch_result:
  protocol: lawb.local_runner.relay_task_fetch_result.v1
  result: success | failure | blocked
  task_surface:
    role: task_surface
    kind: github_comment
    url: "https://github.com/HarryWhite-TW/local-ai-workbench/issues/130#issuecomment-0000000001"
    issue: 130
    comment_id: 1
  parsed_task_packet:
    protocol: lawb.local_runner.task_packet.v1
    packet_id: task-130-relay-fetch-proof
    logical_issue: 130
    phase: relay_task_fetch_proof
    action_type: docs_only_fetch_proof
    risk_level: medium
  checks:
    - name: active_packet_count_is_one
      passed: true
      detail: "Exactly one active task packet found."
    - name: protocol_is_task_packet_v1
      passed: true
      detail: "Protocol matches Task Packet v1."
  stop_condition_reached: true
  next_recommended_action: chatgpt_review
```

This fetch result summary is not a Result Packet v1 replacement.

A future implementation may wrap or translate it into Result Packet v1.

## Failure rules

Relay task fetch must fail closed when:

* task surface is missing
* task surface kind is unsupported
* task surface is the roadmap anchor without explicit fallback permission
* active_packet_count is zero
* active_packet_count is greater than one
* boundary markers are missing
* boundary markers are malformed
* protocol is missing
* protocol is not Task Packet v1
* logical issue mismatches expected value
* phase mismatches expected value
* action type is unsupported
* risk level is unsupported
* repository mismatches expected value
* branch mismatches expected value
* allowed_files is missing
* forbidden_operations is missing
* approval object is missing
* validation object is missing
* result_target is missing
* stop_condition is missing
* fallback is true but fallback_reason is missing
* natural language outside packet attempts to grant authority
* task packet attempts to approve a future phase

## Security notes

Relay task fetch must not execute shell commands from free text.

Relay task fetch must not treat text outside Task Packet v1 markers as authority.

Relay task fetch must not read broad issue history as an implicit task queue.

Relay task fetch must not scan unrelated issues.

Relay task fetch must not use #114 as a primary task packet sink unless explicitly marked fallback.

Relay task fetch must not hide fallback behavior.

Relay task fetch must not hide transitional bridge gaps.

Relay task fetch must not transform publication proof into approval.

Relay task fetch must not transform fetch success into approval.

## Transitional limitation

In the current transitional workflow, the user may still paste Codex prompts or result blocks when bridge readback is unavailable.

That behavior is fallback.

The target is still ChatGPT-centered publication and readback.

#130 proves the fetch side conceptually.

#131 should address bounded Codex-side action proof.

#132 should address Result Packet writeback.

#133 should address no-copy / no-paste bridge smoke.

## Completion criteria

#130 is complete when this document defines:

* proof purpose
* Direction Lock binding
* relationship to the bridge
* relationship to Task Packet v1
* relationship to Result Packet v1
* relationship to Task and Result Surface v1
* relationship to #129 Publication Proof
* proof target
* non-goals
* relay task fetch stages
* fetch input contract
* active packet detection
* required validation checks
* approval boundary
* fetch result summary
* failure rules
* security notes
* transitional limitation

#130 is not complete if it implements runner code.

#130 is not complete if it creates scripts.

#130 is not complete if it creates tests.

#130 is not complete if it creates GitHub issues.

#130 is not complete if it changes a real task surface.

#130 is not complete if it changes a real result surface.

#130 is not complete if it authorizes automatic commit.

#130 is not complete if it authorizes automatic push.

#130 is not complete if it authorizes Lv5 full automation.

## Current status

Relay Task Fetch Proof is defined as a docs-only proof that a future relay can fetch and validate a Task Packet v1 from an approved Task Surface v1 location.

The next recommended step after #130 is #131 Bounded Codex-side Action Proof.

# No-copy / No-paste Bridge Smoke 133

## Purpose

This document defines #133 No-copy / No-paste Bridge Smoke.

The purpose is to prove, at the protocol and documentation level, that the bridge can define a verifiable smoke path where the user does not act as the long-form task relay and does not act as the long-form result relay.

This proof is a bridge design artifact.

This proof does not implement a runner.

This proof does not execute a runner.

This proof does not execute Codex-side actions.

This proof does not create scripts.

This proof does not create tests.

This proof does not create a GitHub issue.

This proof does not create a GitHub comment.

This proof does not write a real Task Packet.

This proof does not write a real Result Packet.

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

This proof does not claim that no-copy / no-paste execution is already implemented.

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
relay_fetch_proof_path=docs/RELAY_TASK_FETCH_PROOF_130.md
bounded_action_proof_path=docs/BOUNDED_CODEX_SIDE_ACTION_PROOF_131.md
result_writeback_proof_path=docs/RESULT_PACKET_WRITEBACK_PROOF_132.md
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
-> bounded Codex-side action candidate
-> approved result surface containing Result Packet v1
-> ChatGPT readback and review
-> user key approval decisions through ChatGPT
```

The user should not be the long-form task relay.

The user should not be the long-form result relay.

Manual copy/paste is fallback.

Manual foreground start may remain transitional.

This proof exists to define how a future smoke can distinguish the target path from fallback manual relay.

## Relationship to Task Packet v1

Task Packet v1 defines the structured task input.

No-copy / no-paste task delivery requires the task packet to be placed in an approved task surface.

The user should not need to paste the full task packet into Codex as the target workflow.

The task packet must still preserve:

* protocol
* boundary markers
* packet ID
* logical issue
* phase
* action type
* risk level
* allowed files
* forbidden operations
* approval object
* result target
* stop condition

## Relationship to Result Packet v1

Result Packet v1 defines the structured result output.

No-copy / no-paste result readback requires the result packet to be placed in an approved result surface.

The user should not need to paste the full result packet into ChatGPT as the target workflow.

The result packet must still preserve:

* protocol
* boundary markers
* result status
* task packet reference
* changed files
* validation summary
* evidence object
* failure object when blocked or failed
* stop condition reached
* next recommended action

A Result Packet is evidence.

A Result Packet is not approval.

## Relationship to Task and Result Surface v1

Task and Result Surface v1 defines where task and result packets live.

No-copy / no-paste bridge smoke requires:

1. exactly one approved task surface
2. exactly one approved result surface
3. task surface role must remain task_surface
4. result surface role must remain result_surface
5. roadmap anchor must not be the primary long-term task or result sink
6. fallback surfaces must be explicitly labeled
7. fallback_reason must be present when fallback is true

## Relationship to #129 Publication Proof

#129 proves ChatGPT can author a publication-ready Task Packet v1 candidate.

#133 assumes ChatGPT can produce task packet content without relying on the user to rewrite it.

#133 does not publish a real task packet.

#133 does not create a real task surface.

## Relationship to #130 Relay Task Fetch Proof

#130 proves a future relay can fetch and validate a Task Packet v1.

#133 assumes relay task fetch can replace manual task copy/paste in the target path.

Fetch success is not execution approval.

Fetch success is not commit approval.

Fetch success is not push approval.

## Relationship to #131 Bounded Codex-side Action Proof

#131 proves future Codex-side action must remain bounded.

#133 assumes bounded action can replace free-form Codex execution in the target path.

Bounded action success is evidence.

Bounded action success is not approval.

## Relationship to #132 Result Packet Writeback Proof

#132 proves future results can be written back as Result Packet v1-compatible evidence.

#133 assumes result packet writeback can replace manual result copy/paste in the target path.

Writeback success is evidence.

Writeback success is not next-phase approval.

## Proof target

The proof target is a no-copy / no-paste bridge smoke model.

A valid no-copy / no-paste bridge smoke must show that a future process can:

1. receive or locate a task surface reference
2. read a Task Packet v1 from that task surface
3. validate the task packet
4. produce or simulate a bounded action result
5. construct a Result Packet v1-compatible payload
6. write or reference the result packet in an approved result surface
7. allow ChatGPT to read back the result surface
8. verify evidence-not-approval semantics
9. confirm user did not relay long-form task content
10. confirm user did not relay long-form result content
11. keep user approval as explicit high-risk decision only
12. fail closed when any surface, packet, or boundary is ambiguous

## Non-goals

#133 is not runner implementation.

#133 is not script implementation.

#133 is not test implementation.

#133 is not actual Codex-side execution.

#133 is not actual Task Packet write.

#133 is not actual Result Packet writeback.

#133 is not approval-only end-to-end smoke.

#133 does not create a real task issue.

#133 does not create a real result issue.

#133 does not close #114.

#133 does not change labels.

#133 does not authorize implementation.

## Transitional invocation exception

During the current development phase, the user may still paste this Codex prompt to start a ReviewBundle task.

That is transitional invocation.

Transitional invocation is not the target bridge path.

Inside the target no-copy / no-paste smoke path, the user must not relay the long-form task packet content and must not relay the long-form result packet content.

If manual relay is used, it must be labeled fallback.

If fallback is used, fallback_reason must be present.

## Smoke stages

A future no-copy / no-paste bridge smoke should follow these conceptual stages:

```text
ChatGPT prepares task packet candidate
-> task packet is placed or referenced in approved task surface
-> relay fetches task packet from task surface
-> relay validates boundary markers and protocol
-> bounded Codex-side action candidate is produced or blocked
-> Result Packet v1-compatible payload is produced
-> result packet is placed or referenced in approved result surface
-> ChatGPT reads result surface
-> ChatGPT verifies evidence-not-approval
-> ChatGPT asks user for next explicit approval when needed
```

This proof stops before real task packet publication, real runner execution, or real result packet writeback.

## Smoke input contract

A future no-copy / no-paste smoke should receive surface references rather than long-form task/result content from the user.

Recommended shape:

```yaml
no_copy_no_paste_smoke_input:
  logical_issue: 133
  mode: proof_only
  user_relayed_long_form_task_content: false
  user_relayed_long_form_result_content: false
  task_surface_reference:
    role: task_surface
    kind: github_comment
    url: "https://github.com/HarryWhite-TW/local-ai-workbench/issues/133#issuecomment-0000000001"
    issue: 133
    comment_id: 1
    active_packet_count: 1
    fallback: false
    fallback_reason: null
  result_surface_reference:
    role: result_surface
    kind: github_comment
    url: "https://github.com/HarryWhite-TW/local-ai-workbench/issues/133#issuecomment-0000000002"
    issue: 133
    comment_id: 2
    active_packet_count: 1
    fallback: false
    fallback_reason: null
```

This input contract is a design example only.

It is not an active smoke run.

## Smoke pass criteria

A no-copy / no-paste smoke should pass only when:

```yaml
smoke_pass_criteria:
  task_surface_present: true
  result_surface_present: true
  task_packet_protocol_valid: true
  task_packet_boundary_valid: true
  relay_fetch_valid: true
  bounded_action_respected: true
  result_packet_protocol_valid: true
  result_packet_boundary_valid: true
  result_packet_evidence_not_approval: true
  chatgpt_readback_valid: true
  user_relayed_long_form_task_content: false
  user_relayed_long_form_result_content: false
  fallback_used: false
  stop_condition_reached: true
```

All pass criteria must be true.

## Smoke blocked criteria

A no-copy / no-paste smoke should be blocked when:

* task surface is missing
* result surface is missing
* task packet boundary markers are missing
* result packet boundary markers are missing
* protocol is missing
* more than one active task packet is present
* more than one active result packet is present when only one is expected
* task surface is the roadmap anchor without fallback permission
* result surface is the roadmap anchor without fallback permission
* user relays long-form task content in target path
* user relays long-form result content in target path
* fallback is true but fallback_reason is missing
* result packet claims approval
* next phase is attempted without explicit approval
* task/result surface boundaries are blurred

## Smoke result summary

A future smoke should emit a summary for ChatGPT review.

Recommended shape:

```yaml
no_copy_no_paste_bridge_smoke_result:
  protocol: lawb.local_runner.no_copy_no_paste_bridge_smoke_result.v1
  logical_issue: 133
  result: success | blocked | failure
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

This smoke result summary is not a Result Packet v1 replacement.

A future implementation may wrap or translate it into Result Packet v1.

## Evidence boundary

No-copy / no-paste smoke success is evidence.

No-copy / no-paste smoke success is not approval.

Smoke success does not approve execution.

Smoke success does not approve commit.

Smoke success does not approve push.

Smoke success does not approve issue close.

Smoke success does not approve PR creation.

Smoke success does not approve merge.

Approval chaining remains forbidden.

## Failure rules

No-copy / no-paste bridge smoke must fail closed when:

* task surface is missing
* result surface is missing
* task packet is missing
* result packet is missing
* task packet protocol is invalid
* result packet protocol is invalid
* task packet boundary markers are malformed
* result packet boundary markers are malformed
* user relays long-form task content in target path
* user relays long-form result content in target path
* fallback is used but not labeled
* fallback is true but fallback_reason is missing
* task surface is used as result surface
* result surface is used as task surface
* #114 is used as primary long-term task sink without fallback permission
* #114 is used as primary long-term result sink without fallback permission
* result packet claims approval
* writeback success claims next-phase approval
* next phase proceeds without ChatGPT review
* next phase proceeds without explicit user approval when required

## Security notes

No-copy / no-paste bridge smoke must not execute shell commands from free text.

No-copy / no-paste bridge smoke must not treat text outside Task Packet v1 or Result Packet v1 markers as authority.

No-copy / no-paste bridge smoke must not read broad issue history as an implicit task or result queue.

No-copy / no-paste bridge smoke must not scan unrelated issues.

No-copy / no-paste bridge smoke must not use #114 as a primary task or result sink unless explicitly marked fallback.

No-copy / no-paste bridge smoke must not hide fallback behavior.

No-copy / no-paste bridge smoke must not hide transitional bridge gaps.

No-copy / no-paste bridge smoke must not transform smoke success into approval.

## Completion criteria

#133 is complete when this document defines:

* proof purpose
* Direction Lock binding
* relationship to the bridge
* relationship to Task Packet v1
* relationship to Result Packet v1
* relationship to Task and Result Surface v1
* relationship to #129 Publication Proof
* relationship to #130 Relay Task Fetch Proof
* relationship to #131 Bounded Codex-side Action Proof
* relationship to #132 Result Packet Writeback Proof
* proof target
* non-goals
* transitional invocation exception
* smoke stages
* smoke input contract
* smoke pass criteria
* smoke blocked criteria
* smoke result summary
* evidence boundary
* failure rules
* security notes

#133 is not complete if it implements runner code.

#133 is not complete if it executes Codex-side actions.

#133 is not complete if it writes a real Task Packet.

#133 is not complete if it writes a real Result Packet.

#133 is not complete if it creates scripts.

#133 is not complete if it creates tests.

#133 is not complete if it creates GitHub issues.

#133 is not complete if it changes a real task surface.

#133 is not complete if it changes a real result surface.

#133 is not complete if it authorizes automatic commit.

#133 is not complete if it authorizes automatic push.

#133 is not complete if it claims no-copy / no-paste execution is already implemented.

#133 is not complete if it authorizes Lv5 full automation.

## Current status

No-copy / No-paste Bridge Smoke is defined as a docs-only smoke proof that a future bridge can verify task and result relay through approved surfaces rather than through user long-form copy/paste.

The next recommended step after #133 is #134 Approval-only End-to-end Smoke.
# Approval-only End-to-end Smoke 134

## Purpose

This document defines #134 Approval-only End-to-end Smoke.

The purpose is to prove, at the protocol and documentation level, that the target bridge can define an end-to-end smoke path where the user only provides scoped approval decisions through ChatGPT and does not act as the long-form task relay or long-form result relay.

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

This proof does not perform a real approval-only smoke.

This proof does not authorize automatic commit.

This proof does not authorize automatic push.

This proof does not authorize automatic issue close.

This proof does not authorize automatic PR creation.

This proof does not authorize automatic merge.

This proof does not authorize background watcher behavior.

This proof does not authorize always-on polling.

This proof does not authorize broad issue scanning.

This proof does not authorize Lv5 full automation.

This proof does not claim that approval-only end-to-end execution is already implemented.

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
no_copy_no_paste_smoke_path=docs/NO_COPY_NO_PASTE_BRIDGE_SMOKE_133.md
primary_goal=chatgpt_dispatches_to_codex_and_reads_results_back
issue_role=core
manual_copy_paste_is_target=false
user_only_interfaces_with_chatgpt_goal=true
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

The user should not be required to paste long-form Codex prompts in the target path.

The user should only make scoped approval decisions through ChatGPT.

Manual copy/paste is fallback.

Manual foreground start may remain transitional.

This proof exists to define how a future end-to-end smoke can distinguish approval-only user participation from manual relay.

## Relationship to Task Packet v1

Task Packet v1 defines the structured task input.

Approval-only end-to-end smoke requires the task packet to be prepared by ChatGPT and placed or referenced in an approved task surface.

The user should not need to rewrite or relay the full task packet.

The task packet must preserve protocol, boundary markers, packet ID, logical issue, phase, action type, risk level, allowed files, forbidden operations, approval object, result target, and stop condition.

Task Packet content is not approval.

Task surface presence is not approval.

## Relationship to Result Packet v1

Result Packet v1 defines the structured result output.

Approval-only end-to-end smoke requires the result packet to be placed or referenced in an approved result surface.

The user should not need to paste the full result packet into ChatGPT.

A Result Packet is evidence.

A Result Packet is not approval.

Result Packet readback does not approve the next phase.

Result Packet readback does not approve commit.

Result Packet readback does not approve push.

Result Packet readback does not approve issue close.

## Relationship to Task and Result Surface v1

Task and Result Surface v1 defines where task and result packets live.

Approval-only end-to-end smoke requires exactly one approved task surface and exactly one approved result surface.

The task surface role must remain task_surface.

The result surface role must remain result_surface.

The roadmap anchor must not be the primary long-term task or result sink.

Fallback surfaces must be explicitly labeled.

fallback_reason must be present when fallback is true.

A surface is not approval.

A pointer to a surface is not approval.

## Relationship to #129 Publication Proof

#129 proves ChatGPT can author a publication-ready Task Packet v1 candidate.

#134 assumes ChatGPT can prepare task instructions without requiring the user to rewrite them.

#134 does not publish a real task packet.

#134 does not create a real task surface.

## Relationship to #130 Relay Task Fetch Proof

#130 proves a future relay can fetch and validate a Task Packet v1.

#134 assumes relay task fetch can replace manual task relay in the target path.

Fetch success is evidence.

Fetch success is not approval.

## Relationship to #131 Bounded Codex-side Action Proof

#131 proves future Codex-side action must remain bounded.

#134 assumes bounded action prevents free-form Codex execution in the target path.

Bounded action success is evidence.

Bounded action success is not approval.

## Relationship to #132 Result Packet Writeback Proof

#132 proves future results can be written back as Result Packet v1-compatible evidence.

#134 assumes result packet writeback can replace manual result relay in the target path.

Writeback success is evidence.

Writeback success is not approval.

## Relationship to #133 No-copy / No-paste Bridge Smoke

#133 proves a future bridge smoke can verify task and result relay through approved surfaces rather than through user long-form copy/paste.

#134 adds the stricter target user role: the user only provides scoped approval decisions through ChatGPT.

The user does not relay long-form task content.

The user does not relay long-form result content.

The user does not provide long-form direct Codex prompts in the target path.

## Proof target

The proof target is an approval-only end-to-end smoke model.

A valid approval-only end-to-end smoke must show that a future process can receive a short user approval, reject, or revise decision through ChatGPT; avoid requiring long-form task or result relay; prepare or reference a Task Packet v1 through ChatGPT; place or reference the task packet in an approved task surface; fetch and validate the task packet; enforce bounded Codex-side action rules; produce or reference a Result Packet v1-compatible result; place or reference the result packet in an approved result surface; allow ChatGPT to read back the result; verify evidence-not-approval semantics; require explicit scoped approval for each high-risk next phase; prevent approval chaining; and fail closed on missing approval, ambiguous approval, missing surfaces, invalid packets, or manual relay.

## Non-goals

#134 is not runner implementation.

#134 is not script implementation.

#134 is not test implementation.

#134 is not actual Codex-side execution.

#134 is not actual Task Packet write.

#134 is not actual Result Packet writeback.

#134 is not actual approval-only end-to-end execution.

#134 does not create a real task issue.

#134 does not create a real result issue.

#134 does not close #114.

#134 does not change labels.

#134 does not authorize implementation.

## Transitional invocation exception

During the current development phase, the user may still paste this Codex prompt to start a ReviewBundle task.

That is transitional invocation.

Transitional invocation is not the target bridge path.

Inside the target approval-only end-to-end path, the user must not relay long-form task content, must not relay long-form result content, and must not issue long-form Codex prompts directly.

If manual relay is used, it must be labeled fallback.

If fallback is used, fallback_reason must be present.

## User role model

In the target approval-only end-to-end path, the user role is limited to short scoped decisions through ChatGPT.

Allowed user decision types:

```yaml
allowed_user_decision_types:
  approve_reviewbundle:
    description: "Approve proceeding from plan/review to bounded candidate phase."
    high_risk: false
  approve_commit:
    description: "Approve one explicitly scoped local commit."
    high_risk: true
  approve_push:
    description: "Approve one explicitly scoped push."
    high_risk: true
  reject:
    description: "Reject the current candidate or next phase."
    high_risk: false
  request_revision:
    description: "Ask ChatGPT to revise the task packet or decision package."
    high_risk: false
```

Disallowed user roles in target path:

```yaml
disallowed_user_roles:
  - long_form_task_relay
  - long_form_result_relay
  - direct_codex_long_prompt_operator
  - implicit_approval_source
  - approval_chain_source
```

## Approval scope rules

Approval must be explicit, scoped, and single-phase.

Recommended shape:

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
```

Commit approval does not approve push.

Push approval does not approve issue close.

ReviewBundle approval does not approve commit.

Result readback does not approve the next phase.

## Approval consumption rules

A future process must consume approval exactly once.

Recommended rules:

```yaml
approval_consumption_rules:
  approval_required_for_high_risk: true
  approval_must_be_scoped: true
  approval_must_match_logical_issue: true
  approval_must_match_phase: true
  approval_must_match_operation: true
  approval_must_match_allowed_files: true
  approval_expires_after_use: true
  approval_chaining_allowed: false
```

A consumed approval must not be reused.

An approval for commit must not be reused for push.

An approval for one issue must not be reused for another issue.

## End-to-end smoke stages

A future approval-only end-to-end smoke should follow these conceptual stages:

```text
ChatGPT prepares task packet candidate
-> user gives short scoped approval through ChatGPT when required
-> task packet is placed or referenced in approved task surface
-> relay fetches task packet from task surface
-> relay validates boundary markers and protocol
-> bounded Codex-side action candidate is produced or blocked
-> Result Packet v1-compatible payload is produced
-> result packet is placed or referenced in approved result surface
-> ChatGPT reads result surface
-> ChatGPT verifies evidence-not-approval
-> ChatGPT asks user for next explicit scoped approval when needed
```

This proof stops before real task packet publication, real runner execution, real result packet writeback, or real approval-only end-to-end smoke.

## Smoke input contract

A future approval-only end-to-end smoke should receive user decision metadata and surface references, not long-form relay content from the user.

Recommended shape:

```yaml
approval_only_end_to_end_smoke_input:
  logical_issue: 134
  mode: proof_only
  user_interaction:
    via_chatgpt_only: true
    user_relayed_long_form_task_content: false
    user_relayed_long_form_result_content: false
    user_issued_direct_long_form_codex_prompt: false
    user_decision_type: approve_reviewbundle
    approval_scope: null
  task_surface_reference:
    role: task_surface
    kind: github_comment
    issue: 134
    comment_id: 1
    active_packet_count: 1
    fallback: false
    fallback_reason: null
  result_surface_reference:
    role: result_surface
    kind: github_comment
    issue: 134
    comment_id: 2
    active_packet_count: 1
    fallback: false
    fallback_reason: null
```

This input contract is a design example only.

It is not an active smoke run.

## Smoke pass criteria

An approval-only end-to-end smoke should pass only when:

```yaml
smoke_pass_criteria:
  user_interaction_via_chatgpt_only: true
  user_relayed_long_form_task_content: false
  user_relayed_long_form_result_content: false
  user_issued_direct_long_form_codex_prompt: false
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
  approval_required_for_next_high_risk_phase: true
  approval_chaining_attempted: false
  fallback_used: false
  stop_condition_reached: true
```

All pass criteria must be true.

## Smoke blocked criteria

An approval-only end-to-end smoke should be blocked when the user relays long-form task content, relays long-form result content, issues direct long-form Codex prompts, a surface is missing, packet boundary markers are missing, protocol is missing, active packets are ambiguous, fallback lacks a reason, required approval is missing or ambiguous, approval is unscoped, approval does not match the logical issue, phase, or operation, approval is reused after consumption, approval chaining is attempted, a result packet claims approval, smoke success claims approval, or the next phase proceeds without ChatGPT review and explicit user approval when required.

## Approval-only smoke result summary

A future smoke should emit a summary for ChatGPT review.

Recommended shape:

```yaml
approval_only_end_to_end_smoke_result:
  protocol: lawb.local_runner.approval_only_end_to_end_smoke_result.v1
  logical_issue: 134
  result: success | blocked | failure
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

This smoke result summary is not a Result Packet v1 replacement.

A future implementation may wrap or translate it into Result Packet v1.

## Evidence boundary

Approval-only smoke success is evidence.

Approval-only smoke success is not approval.

Smoke success does not approve execution.

Smoke success does not approve commit.

Smoke success does not approve push.

Smoke success does not approve issue close.

Smoke success does not approve PR creation.

Smoke success does not approve merge.

Approval chaining remains forbidden.

## Failure rules

Approval-only end-to-end smoke must fail closed when user relay occurs in the target path, task or result surfaces are missing, packets are missing, packet protocol or boundary markers are invalid, fallback is unlabeled, fallback_reason is missing, task and result surface roles are confused, #114 is used as a primary long-term task or result sink without fallback permission, approval is required but missing, approval is ambiguous, approval is unscoped, approval is reused, approval chaining is attempted, a result packet claims approval, smoke success claims approval, or the next phase proceeds without ChatGPT review and explicit user approval when required.

## Security notes

Approval-only end-to-end smoke must not execute shell commands from free text.

Approval-only end-to-end smoke must not treat text outside Task Packet v1 or Result Packet v1 markers as authority.

Approval-only end-to-end smoke must not treat approval text as broad authority.

Approval-only end-to-end smoke must not read broad issue history as an implicit task or result queue.

Approval-only end-to-end smoke must not scan unrelated issues.

Approval-only end-to-end smoke must not use #114 as a primary task or result sink unless explicitly marked fallback.

Approval-only end-to-end smoke must not hide fallback behavior.

Approval-only end-to-end smoke must not hide transitional bridge gaps.

Approval-only end-to-end smoke must not transform smoke success into approval.

Approval-only end-to-end smoke must not transform result readback into approval.

## Completion criteria

#134 is complete when this document defines proof purpose, Direction Lock binding, relationship to the bridge, relationship to Task Packet v1, relationship to Result Packet v1, relationship to Task and Result Surface v1, relationship to #129 Publication Proof, relationship to #130 Relay Task Fetch Proof, relationship to #131 Bounded Codex-side Action Proof, relationship to #132 Result Packet Writeback Proof, relationship to #133 No-copy / No-paste Bridge Smoke, proof target, non-goals, transitional invocation exception, user role model, approval scope rules, approval consumption rules, end-to-end smoke stages, smoke input contract, smoke pass criteria, smoke blocked criteria, approval-only smoke result summary, evidence boundary, failure rules, and security notes.

#134 is not complete if it implements runner code.

#134 is not complete if it executes Codex-side actions.

#134 is not complete if it writes a real Task Packet.

#134 is not complete if it writes a real Result Packet.

#134 is not complete if it executes a real approval-only smoke.

#134 is not complete if it creates scripts.

#134 is not complete if it creates tests.

#134 is not complete if it creates GitHub issues.

#134 is not complete if it changes a real task surface.

#134 is not complete if it changes a real result surface.

#134 is not complete if it authorizes automatic commit.

#134 is not complete if it authorizes automatic push.

#134 is not complete if it claims approval-only end-to-end execution is already implemented.

#134 is not complete if it authorizes Lv5 full automation.

## Current status

Approval-only End-to-end Smoke is defined as a docs-only smoke proof that a future bridge can verify user participation is reduced to scoped approval decisions through ChatGPT rather than long-form task/result relay.

The next recommended step after #134 is #135 Implementation Readiness Gate.

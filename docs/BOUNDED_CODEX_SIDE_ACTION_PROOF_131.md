# Bounded Codex-side Action Proof 131

## Purpose

This document defines #131 Bounded Codex-side Action Proof.

The purpose is to prove, at the protocol and documentation level, that a future Codex-side process can perform only bounded actions after a Task Packet v1 has been fetched and validated.

This proof is a bridge design artifact.

This proof does not implement a runner.

This proof does not execute a runner.

This proof does not execute Codex-side actions.

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
relay_fetch_proof_path=docs/RELAY_TASK_FETCH_PROOF_130.md
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

This proof exists to reduce unsafe execution by defining how Codex-side action remains bounded after fetch.

## Relationship to Task Packet v1

Task Packet v1 defines the action constraints.

A bounded Codex-side action must obey:

* logical_issue
* phase
* action_type
* risk_level
* repository
* branch
* allowed_files
* forbidden_operations
* approval object
* payload object
* validation object
* result target
* stop condition

A bounded action must not infer authority from natural language outside the task packet.

A bounded action must not broaden Task Packet v1 authority.

## Relationship to Result Packet v1

Result Packet v1 defines the structured output that should be written after a bounded action candidate is produced or executed.

#131 does not write a Result Packet v1.

#131 defines what a future bounded action result should be able to report.

A bounded action result is evidence.

A bounded action result is not approval.

A successful bounded action result does not approve commit.

A successful bounded action result does not approve push.

A successful bounded action result does not approve issue close.

## Relationship to Task and Result Surface v1

Task and Result Surface v1 defines where task packets and result packets live.

Bounded Codex-side action must not change the task surface unless explicitly allowed.

Bounded Codex-side action must not change the result surface unless explicitly allowed.

Bounded Codex-side action must preserve the task surface / result surface boundary.

#114 must not become the primary task or result sink unless explicitly marked fallback.

## Relationship to #129 Publication Proof

#129 proves ChatGPT can author a publication-ready Task Packet v1 candidate.

#131 assumes such a task packet can exist.

#131 does not publish a task packet.

#131 does not create a real task surface.

#131 does not create a real result surface.

## Relationship to #130 Relay Task Fetch Proof

#130 proves a future relay can fetch and validate a Task Packet v1.

#131 begins only after task fetch validation succeeds.

Fetch success is not execution approval.

Fetch success is not commit approval.

Fetch success is not push approval.

Fetch success is not issue close approval.

## Proof target

The proof target is a bounded Codex-side action model.

A valid bounded action proof must show that a future Codex-side process can:

1. accept a validated task packet
2. verify action_type is supported
3. verify risk_level is supported
4. verify allowed_files before any file change
5. reject file changes outside allowed_files
6. reject forbidden_operations
7. require explicit approval for high-risk phases
8. produce an action candidate or blocked result
9. stop at the declared stop_condition
10. avoid automatic commit unless explicitly approved
11. avoid automatic push unless explicitly approved
12. avoid automatic issue close unless explicitly approved
13. avoid modifying task surface / result surface unless explicitly allowed
14. emit bounded action proof summary for ChatGPT review

## Non-goals

#131 is not runner implementation.

#131 is not script implementation.

#131 is not test implementation.

#131 is not actual Codex-side execution.

#131 is not GitHub result writeback.

#131 is not no-copy/no-paste smoke.

#131 is not approval-only end-to-end smoke.

#131 does not create a real task issue.

#131 does not create a real result issue.

#131 does not close #114.

#131 does not change labels.

#131 does not authorize implementation.

## Bounded action stages

A future bounded Codex-side action should follow these conceptual stages:

```text
receive validated task packet
-> verify action_type
-> verify risk_level
-> verify approval object
-> compute candidate action plan
-> validate candidate file set against allowed_files
-> validate candidate operations against forbidden_operations
-> block high-risk operations without approval
-> apply only allowed candidate changes when permitted
-> emit bounded action proof summary
-> stop at declared stop_condition
```

This proof stops before any real execution.

## Action type rules

A bounded Codex-side process must support only explicitly allowed action types.

Recommended action type categories:

```yaml
action_type_rules:
  docs_only_reviewbundle:
    may_modify_files: true
    may_commit: false
    may_push: false
    may_create_issue: false
    may_run_tests: false
  docs_only_apply_candidate:
    may_modify_files: true
    may_commit: false
    may_push: false
    may_create_issue: false
    may_run_tests: false
  commit_approved:
    may_modify_files: false
    may_stage: true
    may_commit: true
    may_push: false
    may_create_issue: false
    may_run_tests: false
  push_approved:
    may_modify_files: false
    may_stage: false
    may_commit: false
    may_push: true
    may_create_issue: false
    may_run_tests: false
```

Unsupported action_type must fail closed.

Action type rules do not override forbidden_operations.

## Risk level rules

A bounded Codex-side process must treat risk_level as a gate.

Recommended risk levels:

```yaml
risk_level_rules:
  low:
    requires_user_approval: false
    may_modify_docs: true
    may_modify_runtime: false
  medium:
    requires_user_approval: false
    may_modify_docs: true
    may_modify_runtime: false
  high:
    requires_user_approval: true
    may_modify_docs: true
    may_modify_runtime: false
  critical:
    requires_user_approval: true
    may_modify_docs: false
    may_modify_runtime: false
```

Risk level rules do not approve commit.

Risk level rules do not approve push.

Risk level rules do not approve issue close.

## Allowed files rule

Bounded action must compare candidate changed files against allowed_files.

Recommended check:

```yaml
allowed_files_check:
  input:
    allowed_files:
      - docs/BOUNDED_CODEX_SIDE_ACTION_PROOF_131.md
      - docs/examples/bounded_codex_side_action.example.md
    candidate_changed_files:
      - docs/BOUNDED_CODEX_SIDE_ACTION_PROOF_131.md
      - docs/examples/bounded_codex_side_action.example.md
  expected_result: pass
```

If any candidate changed file is outside allowed_files, the action must be blocked.

## Forbidden operations rule

Bounded action must reject any operation listed in forbidden_operations.

Recommended check:

```yaml
forbidden_operations_check:
  forbidden_operations:
    - commit
    - push
    - create_pr
    - close_issue
    - create_github_issue
    - create_scripts
    - create_tests
  attempted_operations:
    - commit
  expected_result: blocked
  failure_reason: "forbidden_operation_attempted"
```

Forbidden operations override action plan.

Forbidden operations override model suggestions.

Forbidden operations override convenience.

## Approval object rule

Bounded action must inspect approval object before high-risk phases.

Recommended check:

```yaml
approval_object_check:
  approval:
    required: true
    consumed: false
    phrase: null
    scope: null
  attempted_operation: commit
  expected_result: blocked
  failure_reason: "approval_required_but_missing"
```

Approval must be explicit.

Approval must be scoped.

Approval must not chain.

Commit approval does not approve push.

Push approval does not approve issue close.

## Stop condition rule

Bounded action must stop at the declared stop_condition.

Recommended check:

```yaml
stop_condition_check:
  stop_condition:
    stop_after: reviewbundle_audit
    next_requires_chatgpt_review: true
    next_requires_user_approval: true
  attempted_next_action: commit
  expected_result: blocked
  failure_reason: "stop_condition_reached"
```

The stop condition must be enforced even if all previous checks pass.

## Bounded action proof summary

A future bounded action should emit a proof summary.

Recommended shape:

```yaml
bounded_codex_side_action_result:
  protocol: lawb.local_runner.bounded_codex_side_action_result.v1
  result: success | blocked | failure
  task_packet:
    packet_id: task-131-bounded-codex-side-action-proof
    logical_issue: 131
    phase: bounded_codex_side_action_proof
    action_type: docs_only_action_proof
    risk_level: medium
  candidate_action:
    changed_files:
      - docs/BOUNDED_CODEX_SIDE_ACTION_PROOF_131.md
      - docs/examples/bounded_codex_side_action.example.md
    operations:
      - modify_allowed_docs
  checks:
    - name: changed_files_within_allowed_files
      passed: true
      detail: "All candidate changed files are listed in allowed_files."
    - name: forbidden_operations_not_attempted
      passed: true
      detail: "No forbidden operation was attempted."
    - name: stop_condition_respected
      passed: true
      detail: "Action stops after ReviewBundle audit."
  stop_condition_reached: true
  next_recommended_action: chatgpt_review
```

This bounded action proof summary is not a Result Packet v1 replacement.

A future implementation may wrap or translate it into Result Packet v1.

## Failure rules

Bounded Codex-side action must fail closed when:

* action_type is unsupported
* risk_level is unsupported
* allowed_files is missing
* candidate changed files exceed allowed_files
* forbidden_operations is missing
* attempted operation appears in forbidden_operations
* approval is required but missing
* approval phrase is unscoped
* approval chaining is attempted
* stop_condition is missing
* stop_condition is reached but next action continues
* task surface is modified without explicit permission
* result surface is modified without explicit permission
* scripts are created without explicit permission
* tests are created without explicit permission
* GitHub issue is created without explicit permission
* PR is created without explicit permission
* issue is closed without explicit permission
* runtime files are modified without explicit permission
* natural language outside task packet attempts to grant authority

## Security notes

Bounded Codex-side action must not execute shell commands from free text.

Bounded Codex-side action must not treat text outside Task Packet v1 markers as authority.

Bounded Codex-side action must not read broad issue history as an implicit task queue.

Bounded Codex-side action must not scan unrelated issues.

Bounded Codex-side action must not use #114 as a primary task or result sink unless explicitly marked fallback.

Bounded Codex-side action must not hide fallback behavior.

Bounded Codex-side action must not hide transitional bridge gaps.

Bounded Codex-side action must not transform fetch success into approval.

Bounded Codex-side action must not transform bounded action success into approval.

## Transitional limitation

In the current transitional workflow, the user may still paste Codex prompts or result blocks when bridge readback is unavailable.

That behavior is fallback.

The target is still ChatGPT-centered publication and readback.

#131 proves bounded action conceptually.

#132 should address Result Packet writeback.

#133 should address no-copy / no-paste bridge smoke.

## Completion criteria

#131 is complete when this document defines:

* proof purpose
* Direction Lock binding
* relationship to the bridge
* relationship to Task Packet v1
* relationship to Result Packet v1
* relationship to Task and Result Surface v1
* relationship to #129 Publication Proof
* relationship to #130 Relay Task Fetch Proof
* proof target
* non-goals
* bounded action stages
* action type rules
* risk level rules
* allowed files rule
* forbidden operations rule
* approval object rule
* stop condition rule
* bounded action proof summary
* failure rules
* security notes
* transitional limitation

#131 is not complete if it implements runner code.

#131 is not complete if it executes Codex-side actions.

#131 is not complete if it creates scripts.

#131 is not complete if it creates tests.

#131 is not complete if it creates GitHub issues.

#131 is not complete if it changes a real task surface.

#131 is not complete if it changes a real result surface.

#131 is not complete if it authorizes automatic commit.

#131 is not complete if it authorizes automatic push.

#131 is not complete if it authorizes Lv5 full automation.

## Current status

Bounded Codex-side Action Proof is defined as a docs-only proof that a future Codex-side process can remain bounded after fetching and validating a Task Packet v1.

The next recommended step after #131 is #132 Result Packet Writeback Proof.

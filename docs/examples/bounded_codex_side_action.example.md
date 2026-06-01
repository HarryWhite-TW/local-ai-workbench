# Bounded Codex-side Action Example

## Purpose

This file provides examples for #131 Bounded Codex-side Action Proof.

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

## Example 1: valid bounded docs-only action candidate

```yaml
task_packet:
  packet_id: task-131-bounded-codex-side-action-proof
  logical_issue: 131
  phase: bounded_codex_side_action_proof
  action_type: docs_only_action_proof
  risk_level: medium
  allowed_files:
    - docs/BOUNDED_CODEX_SIDE_ACTION_PROOF_131.md
    - docs/examples/bounded_codex_side_action.example.md
  forbidden_operations:
    - stage
    - commit
    - push
    - create_pr
    - close_issue
    - create_github_issue
    - create_scripts
    - create_tests
candidate_action:
  changed_files:
    - docs/BOUNDED_CODEX_SIDE_ACTION_PROOF_131.md
    - docs/examples/bounded_codex_side_action.example.md
  operations:
    - modify_allowed_docs
validation:
  expected_result: success
```

This is a valid bounded docs-only action candidate.

It is not an active task packet.

It does not approve commit.

## Example 2: invalid changed file outside allowed_files

```yaml
task_packet:
  allowed_files:
    - docs/BOUNDED_CODEX_SIDE_ACTION_PROOF_131.md
    - docs/examples/bounded_codex_side_action.example.md
candidate_action:
  changed_files:
    - docs/BOUNDED_CODEX_SIDE_ACTION_PROOF_131.md
    - README.md
validation:
  expected_result: blocked
  failure_reason: "changed_file_outside_allowed_files"
```

The action must be blocked.

## Example 3: invalid forbidden commit attempt

```yaml
task_packet:
  forbidden_operations:
    - commit
    - push
    - create_pr
    - close_issue
candidate_action:
  operations:
    - modify_allowed_docs
    - commit
validation:
  expected_result: blocked
  failure_reason: "forbidden_operation_attempted"
```

Forbidden operations override convenience.

## Example 4: invalid high-risk action without approval

```yaml
task_packet:
  risk_level: high
  approval:
    required: true
    consumed: false
    phrase: null
    scope: null
candidate_action:
  operations:
    - commit
validation:
  expected_result: blocked
  failure_reason: "approval_required_but_missing"
```

High-risk actions require explicit scoped approval.

## Example 5: invalid stop condition violation

```yaml
task_packet:
  stop_condition:
    stop_after: reviewbundle_audit
    next_requires_chatgpt_review: true
    next_requires_user_approval: true
candidate_action:
  operations:
    - modify_allowed_docs
    - commit
validation:
  expected_result: blocked
  failure_reason: "stop_condition_reached"
```

The process must stop when the stop condition is reached.

## Example 6: successful bounded action proof summary

```yaml
bounded_codex_side_action_result:
  protocol: lawb.local_runner.bounded_codex_side_action_result.v1
  result: success
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

This summary proves bounded action only.

It is not a Result Packet v1 replacement.

## Example 7: invalid bounded action treated as approval

```yaml
validation:
  expected_result: failure
  failure_reason: "bounded_action_success_is_not_approval"
invalid_claim:
  bounded_action_approves_commit: true
  bounded_action_approves_push: true
  bounded_action_approves_issue_close: true
```

Bounded action success is not approval.

## Safety notes

These examples are schema examples.

They are not active task packets unless placed in an approved active task surface.

Bounded Codex-side action is not approval.

A task surface is not approval.

A result surface is not approval.

A successful future result packet is evidence, not approval.

High-risk phases still require explicit user approval through ChatGPT.

Manual fallback must remain labeled.

Manual foreground start must remain labeled as transitional when applicable.

Task and result copy/paste should be reduced by the bridge.

Bounded Codex-side Action Proof does not authorize Lv5 full automation.

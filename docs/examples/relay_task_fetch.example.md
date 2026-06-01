# Relay Task Fetch Example

## Purpose

This file provides examples for #130 Relay Task Fetch Proof.

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

## Example 1: valid relay task fetch input

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
validation:
  expected_result: success
```

This is a valid fetch input example.

It is not an active task surface.

## Example 2: active task packet inside surface

```yaml
LOCAL-RUNNER-TASK-PACKET-V1
BEGIN_TASK_PACKET
protocol: lawb.local_runner.task_packet.v1
packet_id: task-130-relay-fetch-proof
logical_issue: 130
phase: relay_task_fetch_proof
action_type: docs_only_fetch_proof
risk_level: medium
repository: HarryWhite-TW/local-ai-workbench
branch: master
surface_binding:
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
result_target:
  role: result_surface
  kind: github_comment
  url: "https://github.com/HarryWhite-TW/local-ai-workbench/issues/130#issuecomment-0000000002"
  issue: 130
  comment_id: 2
  path: null
  sha: null
  active_packet_count: 0
  fallback: false
  fallback_reason: null
allowed_files:
  - docs/RELAY_TASK_FETCH_PROOF_130.md
  - docs/examples/relay_task_fetch.example.md
forbidden_operations:
  - stage
  - commit
  - push
  - pull
  - merge
  - rebase
  - amend
  - reset
  - restore
  - clean
  - create_branch
  - switch_branch
  - create_pr
  - close_issue
  - reopen_issue
  - change_label
  - change_assignee
  - create_github_issue
  - modify_github_issue_body
  - create_scripts
  - create_tests
  - run_runner
  - run_dispatcher
  - run_runtime_smoke
approval:
  required: false
  consumed: false
  phrase: null
  scope: null
payload:
  summary: "Create #130 docs-only proof that a future relay can fetch and validate a Task Packet v1 from an approved task surface."
validation:
  expected_changed_files:
    - docs/RELAY_TASK_FETCH_PROOF_130.md
    - docs/examples/relay_task_fetch.example.md
  require_git_diff_check: true
  require_no_stage: true
  require_no_commit: true
  require_no_push: true
  require_no_pr: true
  require_no_issue_close: true
  require_no_github_issue_created: true
stop_condition:
  stop_after: reviewbundle_audit
  next_requires_chatgpt_review: true
  next_requires_user_approval: true
END_TASK_PACKET
```

The relay should parse only the content between BEGIN_TASK_PACKET and END_TASK_PACKET.

## Example 3: successful fetch result summary

```yaml
relay_task_fetch_result:
  protocol: lawb.local_runner.relay_task_fetch_result.v1
  result: success
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
    - name: result_target_present
      passed: true
      detail: "Task packet declares a result target."
  stop_condition_reached: true
  next_recommended_action: chatgpt_review
```

This summary proves fetch and validation only.

It does not approve execution.

## Example 4: invalid surface with zero active packets

```yaml
task_surface_reference:
  role: task_surface
  kind: github_comment
  url: "https://github.com/HarryWhite-TW/local-ai-workbench/issues/130#issuecomment-0000000003"
  issue: 130
  comment_id: 3
  path: null
  sha: null
  active_packet_count: 0
  fallback: false
  fallback_reason: null
validation:
  expected_result: failure
  failure_reason: "active_task_packet_required"
```

The relay must fail closed.

## Example 5: invalid surface with multiple active packets

```yaml
task_surface_reference:
  role: task_surface
  kind: github_comment
  url: "https://github.com/HarryWhite-TW/local-ai-workbench/issues/130#issuecomment-0000000004"
  issue: 130
  comment_id: 4
  path: null
  sha: null
  active_packet_count: 2
  fallback: false
  fallback_reason: null
validation:
  expected_result: failure
  failure_reason: "multiple_active_task_packets"
```

The relay must fail closed.

## Example 6: invalid roadmap anchor as primary task surface

```yaml
task_surface_reference:
  role: task_surface
  kind: github_issue
  url: "https://github.com/HarryWhite-TW/local-ai-workbench/issues/114"
  issue: 114
  comment_id: null
  path: null
  sha: null
  active_packet_count: 1
  fallback: false
  fallback_reason: null
validation:
  expected_result: failure
  failure_reason: "roadmap_anchor_used_as_primary_task_surface_without_fallback_permission"
```

#114 should not be used as the primary long-term task packet sink.

If #114 is used during transition, it must be labeled fallback or pointer-only.

## Example 7: invalid task packet that claims approval

```yaml
validation:
  expected_result: failure
  failure_reason: "task_fetch_is_not_approval"
invalid_claim:
  relay_fetch_approves_execution: true
  relay_fetch_approves_commit: true
  relay_fetch_approves_push: true
  relay_fetch_approves_issue_close: true
```

Relay task fetch is not approval.

## Safety notes

These examples are schema examples.

They are not active task packets unless placed in an approved active task surface.

Relay task fetch is not execution.

Relay task fetch is not approval.

A task surface is not approval.

A result surface is not approval.

A successful future result packet is evidence, not approval.

High-risk phases still require explicit user approval through ChatGPT.

Manual fallback must remain labeled.

Manual foreground start must remain labeled as transitional when applicable.

Task and result copy/paste should be reduced by the bridge.

Relay Task Fetch Proof does not authorize Lv5 full automation.

# ChatGPT Task Packet Publication Example

## Purpose

This file provides examples for #129 ChatGPT Task Packet Publication Proof.

These examples are documentation only.

These examples do not authorize implementation.

These examples do not authorize runner code.

These examples do not authorize automatic commit.

These examples do not authorize automatic push.

These examples do not authorize automatic issue close.

These examples do not authorize background watcher behavior.

These examples do not authorize Lv5 full automation.

These examples do not create real task surfaces.

These examples do not create real result surfaces.

These examples do not create GitHub issues.

## Example 1: publication-ready task packet candidate

```yaml
LOCAL-RUNNER-TASK-PACKET-V1
BEGIN_TASK_PACKET
protocol: lawb.local_runner.task_packet.v1
packet_id: task-129-publication-proof
logical_issue: 129
phase: chatgpt_task_packet_publication_proof
action_type: docs_only_publication_proof
risk_level: medium
repository: HarryWhite-TW/local-ai-workbench
branch: master
surface_binding:
  role: task_surface
  kind: github_comment
  url: null
  issue: null
  comment_id: null
  path: null
  sha: null
  active_packet_count: 1
  fallback: false
  fallback_reason: null
result_target:
  role: result_surface
  kind: github_comment
  url: null
  issue: null
  comment_id: null
  path: null
  sha: null
  active_packet_count: 0
  fallback: false
  fallback_reason: null
allowed_files:
  - docs/CHATGPT_TASK_PACKET_PUBLICATION_PROOF_129.md
  - docs/examples/chatgpt_task_packet_publication.example.md
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
  summary: "Create #129 docs-only proof that ChatGPT can author a Task Packet v1 candidate ready for publication into an approved task surface."
validation:
  expected_changed_files:
    - docs/CHATGPT_TASK_PACKET_PUBLICATION_PROOF_129.md
    - docs/examples/chatgpt_task_packet_publication.example.md
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

This is a publication-ready example.

It is not an active task packet unless it is placed inside an approved active task surface.

## Example 2: task surface pointer example

```yaml
roadmap_anchor_marker:
  role: roadmap_anchor
  kind: github_comment
  url: "https://github.com/HarryWhite-TW/local-ai-workbench/issues/114#issuecomment-0000000005"
  issue: 114
  comment_id: 5
  path: null
  sha: null
  active_packet_count: 0
  fallback: false
  fallback_reason: null
  points_to:
    task_surface_url: "https://github.com/HarryWhite-TW/local-ai-workbench/issues/129#issuecomment-0000000006"
    result_surface_url: "https://github.com/HarryWhite-TW/local-ai-workbench/issues/129#issuecomment-0000000007"
```

This example keeps #114 as roadmap anchor only.

It points to canonical task and result surfaces.

It avoids turning #114 into the primary long-term packet sink.

## Example 3: invalid task packet without result target

```yaml
validation:
  expected_result: failure
  failure_reason: "result_target_required"
task_packet_problem:
  protocol: lawb.local_runner.task_packet.v1
  packet_id: task-129-invalid-missing-result-target
  logical_issue: 129
  phase: chatgpt_task_packet_publication_proof
  action_type: docs_only_publication_proof
  risk_level: medium
  result_target: null
```

A publication-ready task packet must declare a result target.

## Example 4: invalid publication proof treated as approval

```yaml
validation:
  expected_result: failure
  failure_reason: "publication_proof_is_not_approval"
invalid_claim:
  publication_proof_approves_commit: true
  publication_proof_approves_push: true
  publication_proof_approves_issue_close: true
```

Publication proof is not approval.

Commit approval does not approve push.

Push approval does not approve issue close.

## Safety notes

These examples are schema examples.

They are not active task packets unless placed in an approved active task surface.

A publication proof is not approval.

A task surface is not approval.

A result surface is not approval.

A successful future result packet is evidence, not approval.

High-risk phases still require explicit user approval through ChatGPT.

Manual fallback must remain labeled.

Manual foreground start must remain labeled as transitional when applicable.

Task and result copy/paste should be reduced by the bridge.

ChatGPT Task Packet Publication Proof does not authorize Lv5 full automation.

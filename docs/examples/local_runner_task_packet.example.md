# Local Runner Task Packet v1 Example

## Purpose

This file provides example Local Runner Task Packet v1 payloads.

These examples are documentation only.

These examples do not authorize implementation.

These examples do not authorize automatic commit.

These examples do not authorize automatic push.

These examples do not authorize automatic issue close.

These examples do not authorize background watcher behavior.

These examples do not authorize Lv5 full automation.

## Example 1: read-only audit task packet

```text
LOCAL-RUNNER-TASK-PACKET-V1
BEGIN_TASK_PACKET
protocol: lawb.local_runner.task_packet.v1
packet_id: task-128-read-only-runner-smoke
logical_issue: 128
phase: readonly_audit
action_type: read_only_audit
risk_level: low
repository: HarryWhite-TW/local-ai-workbench
branch: master
expected_head: "<expected_head_sha>"
expected_origin_master: "<expected_origin_master_sha>"
allowed_files: []
forbidden_files:
  - scripts/
  - tests/
  - README.md
  - AGENTS.md
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
  - add_label
  - remove_label
  - modify_assignee
  - run_tests
  - run_runner
  - run_dispatcher
  - runtime_smoke
approval:
  required: false
  phrase: null
  scope: null
payload:
  kind: audit_request
  target_file: null
  content_boundary: null
validation:
  required_checks:
    - repository_matches
    - branch_matches
    - head_matches
    - working_tree_clean
    - no_staged_changes
    - no_commit_created
    - no_push_performed
    - no_pr_created
    - no_issue_closed
result_target:
  github_issue: 114
  marker: RESULT-PACKET-VISIBLE
stop_condition: stop_after_result_packet
END_TASK_PACKET
```

## Example 2: docs-only apply candidate task packet

```text
LOCAL-RUNNER-TASK-PACKET-V1
BEGIN_TASK_PACKET
protocol: lawb.local_runner.task_packet.v1
packet_id: task-130-docs-only-apply-candidate
logical_issue: 130
phase: docs_only_apply_candidate
action_type: docs_only_apply_candidate
risk_level: medium
repository: HarryWhite-TW/local-ai-workbench
branch: master
expected_head: "<expected_head_sha>"
expected_origin_master: "<expected_origin_master_sha>"
allowed_files:
  - docs/EXAMPLE_TARGET.md
forbidden_files:
  - scripts/
  - tests/
  - README.md
  - AGENTS.md
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
  - add_label
  - remove_label
  - modify_assignee
  - run_tests
  - run_runner
  - run_dispatcher
  - runtime_smoke
approval:
  required: false
  phrase: null
  scope: null
payload:
  kind: document
  target_file: docs/EXAMPLE_TARGET.md
  content_boundary: DOCUMENT_1
validation:
  required_checks:
    - repository_matches
    - branch_matches
    - head_matches
    - changed_files_exact
    - diff_check_passed
    - no_staged_changes
    - no_commit_created
    - no_push_performed
    - no_pr_created
    - no_issue_closed
    - no_scripts_created
    - no_tests_created
result_target:
  github_issue: 114
  marker: REVIEWBUNDLE-AUDIT-VISIBLE
stop_condition: stop_after_result_packet
END_TASK_PACKET

BEGIN_DOCUMENT_1
# Example Target

This is example document content.

The runner should write only this bounded document content to docs/EXAMPLE_TARGET.md.
END_DOCUMENT_1
```

## Example 3: commit-approved task packet

```text
LOCAL-RUNNER-TASK-PACKET-V1
BEGIN_TASK_PACKET
protocol: lawb.local_runner.task_packet.v1
packet_id: task-131-commit-approved-example
logical_issue: 131
phase: commit_approved
action_type: local_commit
risk_level: high
repository: HarryWhite-TW/local-ai-workbench
branch: master
expected_head: "<expected_head_sha>"
expected_origin_master: "<expected_origin_master_sha>"
allowed_files:
  - docs/EXAMPLE_TARGET.md
forbidden_files:
  - scripts/
  - tests/
  - README.md
  - AGENTS.md
forbidden_operations:
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
  - add_label
  - remove_label
  - modify_assignee
  - run_tests
  - run_runner
  - run_dispatcher
  - runtime_smoke
approval:
  required: true
  phrase: "APPROVE #131 commit"
  scope: "local commit only"
payload:
  kind: command_plan
  target_file: null
  content_boundary: null
validation:
  required_checks:
    - repository_matches
    - branch_matches
    - head_matches
    - allowed_files_exact
    - working_tree_expected
    - commit_message_exact
    - working_tree_clean_after_commit
    - no_push_performed
    - no_pr_created
    - no_issue_closed
result_target:
  github_issue: 114
  marker: LOCAL-COMMIT-AUDIT-VISIBLE
stop_condition: stop_after_local_commit_audit
END_TASK_PACKET
```

## Example 4: push-approved task packet

```text
LOCAL-RUNNER-TASK-PACKET-V1
BEGIN_TASK_PACKET
protocol: lawb.local_runner.task_packet.v1
packet_id: task-132-push-approved-example
logical_issue: 132
phase: push_once
action_type: push_once
risk_level: high
repository: HarryWhite-TW/local-ai-workbench
branch: master
expected_head: "<approved_local_commit_sha>"
expected_origin_master: "<expected_remote_parent_sha>"
allowed_files:
  - docs/EXAMPLE_TARGET.md
forbidden_files:
  - scripts/
  - tests/
  - README.md
  - AGENTS.md
forbidden_operations:
  - stage
  - commit
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
  - add_label
  - remove_label
  - modify_assignee
  - run_tests
  - run_runner
  - run_dispatcher
  - runtime_smoke
approval:
  required: true
  phrase: "APPROVE #132 push"
  scope: "push approved local commit only"
payload:
  kind: command_plan
  target_file: null
  content_boundary: null
validation:
  required_checks:
    - repository_matches
    - branch_matches
    - head_matches
    - origin_master_matches
    - ahead_by_expected_commit_count
    - pushed_commit_exact
    - no_new_commit_created_in_push_phase
    - no_pr_created
    - no_issue_closed
result_target:
  github_issue: 114
  marker: PUSH-AUDIT-VISIBLE
stop_condition: stop_after_push_audit
END_TASK_PACKET
```

## Safety notes

These examples are schema examples.

They are not active task packets unless explicitly copied into an approved GitHub issue or comment as a current task.

The runner must not scan this example file as a live task source.

The runner must only read a task packet from an explicitly selected GitHub issue or comment.

High-risk examples require separate user approval.

Commit approval does not approve push.

Push approval does not approve issue close.

Task Packet v1 does not authorize Lv5 full automation.

# Local Runner Result Packet v1 Example

## Purpose

This file provides example Local Runner Result Packet v1 payloads.

These examples are documentation only.

These examples do not authorize implementation.

These examples do not authorize runner code.

These examples do not authorize automatic commit.

These examples do not authorize automatic push.

These examples do not authorize automatic issue close.

These examples do not authorize background watcher behavior.

These examples do not authorize Lv5 full automation.

## Example 1: read-only audit success

```yaml
LOCAL-RUNNER-RESULT-PACKET-V1
BEGIN_RESULT_PACKET
protocol: lawb.local_runner.result_packet.v1
packet_id: result-128-read-only-audit-success
task_packet_id: task-128-read-only-audit
logical_issue: 128
phase: readonly_audit
action_type: read_only_audit
risk_level: low
result: success
repository: HarryWhite-TW/local-ai-workbench
branch: master
head: "<current_head_sha>"
origin_master: "<origin_master_sha>"
executor:
  kind: local_runner
  name: local-runner-bridge-v0
  version: null
task_surface:
  kind: github_comment
  url: "<task_comment_url>"
  issue: 128
  comment_id: 123456789
result_surface:
  kind: github_comment
  url: "<result_comment_url>"
  issue: 128
  comment_id: 987654321
changed_files: []
staged_changes_present: false
commit_created: false
commit_hash: null
push_performed: false
pushed_commit: null
pr_created: false
pr_url: null
merge_performed: false
issue_closed: false
label_changed: false
runtime_behavior_changed: false
runner_behavior_changed: false
dispatcher_behavior_changed: false
automation_authority_expanded: false
approval:
  required: false
  consumed: false
  phrase: null
  scope: null
evidence:
  summary: "Read-only audit completed without repository changes."
  checks:
    - name: repository_matches
      passed: true
      detail: "Repository matched expected owner/name."
    - name: branch_matches
      passed: true
      detail: "Branch matched expected branch."
    - name: no_commit_created
      passed: true
      detail: "No commit was created."
    - name: no_push_performed
      passed: true
      detail: "No push was performed."
    - name: no_issue_closed
      passed: true
      detail: "No issue was closed."
  artifacts:
    - kind: comment
      path: null
      url: "<result_comment_url>"
      sha: null
failure:
  reason: null
  failed_check: null
  recoverable: false
remaining_bridge_gaps:
  - manual_foreground_start_still_required
next_recommended_action: chatgpt_review
stop_condition_reached: true
END_RESULT_PACKET
```

## Example 2: docs-only candidate success

```yaml
LOCAL-RUNNER-RESULT-PACKET-V1
BEGIN_RESULT_PACKET
protocol: lawb.local_runner.result_packet.v1
packet_id: result-134-docs-only-candidate-success
task_packet_id: task-134-docs-only-apply-candidate
logical_issue: 134
phase: docs_only_apply_candidate
action_type: docs_only_apply_candidate
risk_level: medium
result: success
repository: HarryWhite-TW/local-ai-workbench
branch: master
head: "<current_head_sha>"
origin_master: "<origin_master_sha>"
executor:
  kind: relay
  name: local-runner-bridge-v0
  version: null
task_surface:
  kind: github_comment
  url: "<task_comment_url>"
  issue: 134
  comment_id: 123456789
result_surface:
  kind: github_comment
  url: "<result_comment_url>"
  issue: 134
  comment_id: 987654321
changed_files:
  - docs/EXAMPLE_TARGET.md
staged_changes_present: false
commit_created: false
commit_hash: null
push_performed: false
pushed_commit: null
pr_created: false
pr_url: null
merge_performed: false
issue_closed: false
label_changed: false
runtime_behavior_changed: false
runner_behavior_changed: false
dispatcher_behavior_changed: false
automation_authority_expanded: false
approval:
  required: false
  consumed: false
  phrase: null
  scope: null
evidence:
  summary: "Docs-only candidate was applied within allowed files and stopped before commit."
  checks:
    - name: changed_files_exact
      passed: true
      detail: "Only docs/EXAMPLE_TARGET.md changed."
    - name: no_staged_changes
      passed: true
      detail: "No staged changes are present."
    - name: no_commit_created
      passed: true
      detail: "No commit was created."
    - name: no_push_performed
      passed: true
      detail: "No push was performed."
  artifacts:
    - kind: diff
      path: docs/EXAMPLE_TARGET.md
      url: null
      sha: null
failure:
  reason: null
  failed_check: null
  recoverable: false
remaining_bridge_gaps:
  - manual_foreground_start_still_required
next_recommended_action: chatgpt_review_then_commit_approval_package
stop_condition_reached: true
END_RESULT_PACKET
```

## Example 3: blocked high-risk task without approval

```yaml
LOCAL-RUNNER-RESULT-PACKET-V1
BEGIN_RESULT_PACKET
protocol: lawb.local_runner.result_packet.v1
packet_id: result-135-commit-blocked-missing-approval
task_packet_id: task-135-commit-approved
logical_issue: 135
phase: commit_approved
action_type: local_commit
risk_level: high
result: blocked
repository: HarryWhite-TW/local-ai-workbench
branch: master
head: "<current_head_sha>"
origin_master: "<origin_master_sha>"
executor:
  kind: local_runner
  name: local-runner-bridge-v0
  version: null
task_surface:
  kind: github_comment
  url: "<task_comment_url>"
  issue: 135
  comment_id: 123456789
result_surface:
  kind: github_comment
  url: "<result_comment_url>"
  issue: 135
  comment_id: 987654321
changed_files:
  - docs/EXAMPLE_TARGET.md
staged_changes_present: false
commit_created: false
commit_hash: null
push_performed: false
pushed_commit: null
pr_created: false
pr_url: null
merge_performed: false
issue_closed: false
label_changed: false
runtime_behavior_changed: false
runner_behavior_changed: false
dispatcher_behavior_changed: false
automation_authority_expanded: false
approval:
  required: true
  consumed: false
  phrase: null
  scope: null
evidence:
  summary: "Commit task was blocked because explicit phase-specific approval was missing."
  checks:
    - name: approval_required
      passed: true
      detail: "Local commit requires explicit approval."
    - name: approval_present
      passed: false
      detail: "No valid approval phrase was present."
    - name: no_commit_created
      passed: true
      detail: "No commit was created."
    - name: no_push_performed
      passed: true
      detail: "No push was performed."
  artifacts: []
failure:
  reason: "missing_explicit_commit_approval"
  failed_check: approval_present
  recoverable: true
remaining_bridge_gaps:
  - high_risk_approval_required_through_chatgpt
next_recommended_action: chatgpt_review_then_request_commit_approval
stop_condition_reached: true
END_RESULT_PACKET
```

## Example 4: GitHub writeback unavailable fallback

```yaml
LOCAL-RUNNER-RESULT-PACKET-V1
BEGIN_RESULT_PACKET
protocol: lawb.local_runner.result_packet.v1
packet_id: result-132-github-writeback-fallback
task_packet_id: task-132-result-writeback
logical_issue: 132
phase: result_writeback
action_type: write_result_packet
risk_level: low
result: partial
repository: HarryWhite-TW/local-ai-workbench
branch: master
head: "<current_head_sha>"
origin_master: "<origin_master_sha>"
executor:
  kind: relay
  name: local-runner-bridge-v0
  version: null
task_surface:
  kind: github_comment
  url: "<task_comment_url>"
  issue: 132
  comment_id: 123456789
result_surface:
  kind: local_stdout
  url: null
  issue: null
  comment_id: null
changed_files: []
staged_changes_present: false
commit_created: false
commit_hash: null
push_performed: false
pushed_commit: null
pr_created: false
pr_url: null
merge_performed: false
issue_closed: false
label_changed: false
runtime_behavior_changed: false
runner_behavior_changed: false
dispatcher_behavior_changed: false
automation_authority_expanded: false
approval:
  required: false
  consumed: false
  phrase: null
  scope: null
evidence:
  summary: "GitHub writeback was unavailable; local fallback result packet was emitted."
  checks:
    - name: github_writeback_attempted
      passed: true
      detail: "GitHub writeback was attempted."
    - name: github_writeback_succeeded
      passed: false
      detail: "GitHub writeback failed."
    - name: local_fallback_emitted
      passed: true
      detail: "Result packet was printed locally."
  artifacts: []
failure:
  reason: "github_writeback_unavailable"
  failed_check: github_writeback_succeeded
  recoverable: true
remaining_bridge_gaps:
  - github_writeback_unavailable
  - fallback_report_used
next_recommended_action: chatgpt_review_with_fallback_report
stop_condition_reached: true
END_RESULT_PACKET
```

## Safety notes

These examples are schema examples.

They are not active result packets unless explicitly emitted by an approved relay, runner, or Codex-side process.

A result packet is evidence, not approval.

A success result does not approve commit.

A commit result does not approve push.

A push result does not approve issue close.

High-risk phases still require explicit user approval through ChatGPT.

Manual fallback must remain labeled.

Manual foreground start must remain labeled as transitional when applicable.

Task and result copy/paste should be reduced by the bridge.

Result Packet v1 does not authorize Lv5 full automation.

# Controlled Valid Task Surface Comment Draft (#155)

## 1. Purpose

This task prepares a controlled valid Task Surface comment body only.

The draft is intended for a future live fetch validation success smoke. It does not post a GitHub comment, run live GitHub fetch, implement code, modify tests, write Result Packets, or execute Codex-side actions.

## 2. Issue Classification

```yaml
issue_number: 155
issue_role: core
risk_lane: standard
alignment: core
value_target: prepare one controlled valid Task Surface comment body, based on the actual validator and tests, so a human can manually post exactly one GitHub issue comment for the next live fetch validation success smoke
```

## 3. Validator Sources Inspected

The controlled body below is based on these existing repo sources:

- `src/local_runner_bridge/task_surface_validation_flow.py`
- `src/local_runner_bridge/task_surface_dry_run.py`
- `src/local_runner_bridge/task_surface_resolver.py`
- `src/local_runner_bridge/task_packet_validator.py`
- `tests/local_runner_bridge/test_task_surface_validation_flow.py`
- `tests/local_runner_bridge/test_task_surface_dry_run.py`
- `tests/local_runner_bridge/test_task_packet_validator.py`
- `tests/local_runner_bridge/test_explicit_task_surface_fetch_cli.py`

## 4. Inferred Valid Task Surface Requirements

The current validator requires:

- A standalone `LOCAL-RUNNER-TASK-PACKET-V1` protocol marker.
- Exactly one standalone `BEGIN_TASK_PACKET` marker.
- Exactly one standalone `END_TASK_PACKET` marker.
- Non-empty packet text between the boundary markers.
- Packet protocol `lawb.local_runner.task_packet.v1`.
- Required top-level fields:
  - `protocol`
  - `packet_id`
  - `logical_issue`
  - `phase`
  - `action_type`
  - `risk_level`
  - `repository`
  - `branch`
  - `expected_head`
  - `allowed_files`
  - `forbidden_operations`
  - `approval`
  - `payload`
  - `result_target`
  - `stop_condition`
- Required nested fields:
  - `approval.required`
  - `payload.kind`
  - `result_target.github_issue`
  - `result_target.marker`
- `allowed_files` and `forbidden_operations` must be non-empty lists.
- No unknown top-level fields may be present.

The local stdin dry-run command validated the exact body below with `result=success`.

```text
local_validation_performed=true
local_validation_result=success
```

## 5. Controlled Comment Body To Manually Post

A human operator may manually post exactly this body as one GitHub issue comment:

```text
LOCAL-RUNNER-TASK-PACKET-V1
BEGIN_TASK_PACKET
protocol: lawb.local_runner.task_packet.v1
packet_id: task-155-controlled-valid-task-surface-live-fetch-smoke
logical_issue: 155
phase: controlled_valid_task_surface_live_fetch_smoke
action_type: read_only_audit
risk_level: low
repository: HarryWhite-TW/local-ai-workbench
branch: master
expected_head: 81496581ad4890471346e04bbca9c291188f1b38
allowed_files:
  - docs/CONTROLLED_VALID_TASK_SURFACE_COMMENT_DRAFT_155.md
forbidden_operations:
  - execution
  - commit
  - push
  - writeback
  - github_writeback
  - result_packet_write
  - codex_side_action_execution
  - runner
  - dispatcher
  - watcher
  - broad_scan
  - next_latest_issue_inference
  - issue_close
  - label_change
  - pr
  - merge
approval:
  required: false
payload:
  kind: none
result_target:
  github_issue: 114
  marker: CONTROLLED-VALID-TASK-SURFACE-SMOKE-VISIBLE
stop_condition: stop_after_local_validation
END_TASK_PACKET
```

## 6. Why This Comment Is Safe

The controlled Task Surface is minimal and read-only.

It does not request or authorize:

- execution
- commit
- push
- GitHub writeback
- Result Packet write
- Codex-side action execution
- runner
- dispatcher
- watcher
- broad scan
- issue close
- label change
- PR / merge

It uses `payload.kind: none`, `approval.required: false`, and `stop_condition: stop_after_local_validation`.

Do not include secrets or tokens in the GitHub comment.

## 7. Manual Posting Instructions

Codex must not post the GitHub comment.

A human operator must manually post the controlled comment body to a GitHub issue. Manual copy/paste here is test setup only, not the final target workflow.

After posting, copy the exact resulting `#issuecomment-...` URL and return it to ChatGPT.

## 8. Expected Next Step After Posting

The next live fetch smoke must use exactly one resulting `#issuecomment-...` URL.

The next smoke should run the existing explicit fetch CLI against that one explicit comment URL to prove:

```text
live fetch -> validation dry-run -> validation success
```

The project target remains:

```text
ChatGPT -> explicit auditable task surface -> local read-only fetch -> validation dry-run -> JSON readback -> ChatGPT review -> user approval
```

## 9. Still Forbidden Behaviors

The controlled Task Surface and the next smoke must not authorize:

- execution
- commit
- push
- writeback
- GitHub writeback
- Result Packet write
- Codex-side action execution
- runner
- dispatcher
- watcher
- broad scan
- next/latest issue inference
- issue close
- label change
- PR
- merge

## 10. Final Boundary Statement

This document is a controlled comment draft only. It does not post the comment, run live GitHub fetch, touch code, touch tests, write secrets, write GitHub comments, close issues, change labels, create PRs, merge, write Result Packets, execute Codex-side actions, create runner behavior, create dispatcher behavior, create watcher behavior, scan issues, or infer next/latest issues.

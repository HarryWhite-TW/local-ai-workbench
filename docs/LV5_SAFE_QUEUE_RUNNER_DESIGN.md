# Lv5-Safe Queue Runner Design

## Purpose

The Lv5-safe Queue Runner is the proposed workflow layer after completed Lv5-safe BoundedPoll. It is a foreground, manually started, bounded task queue runner that executes approved low-risk tasks in sequence, stops at gates, and emits a structured queue result.

The goal is not full unattended automation. The goal is to reduce repetitive copy/paste operations between ChatGPT and Codex while preserving human review for important decisions.

Expected workflow:

1. ChatGPT and the user agree on a task direction or bounded work segment.
2. The user manually starts one bounded queue run.
3. The queue executes approved low-risk tasks in order.
4. The queue stops when a task node is complete, an important decision appears, risk increases, quota or rate-limit occurs, or any abnormal state is detected.
5. High-risk steps still require explicit user approval outside the queue.

This document is design-only. It does not authorize Queue Runner implementation, runner code changes, dispatcher code changes, test changes, background watcher implementation, always-on polling, automatic commit, automatic push, issue close, label edits, PR creation, merge, approval chaining, or approval token consumption.

## Relationship To Existing Rails

The Queue Runner must preserve the current safety rails:

- ReviewBundle before commit
- commit approval marker before local commit
- PushOnce before push
- CloseIssueOnce before close
- no approval chaining
- no automatic commit, push, or close inside the queue runner

The Queue Runner may sequence low-risk and medium-risk review-producing tasks, but it must not convert a queue result, `LAWBRUNNER-RESULT`, ReviewBundle, or status check into approval for a higher-risk operation.

BoundedPoll remains the verified Lv5-safe dispatcher layer for explicit issue polling and `maybe-status-check`. The Queue Runner is a future workflow design above that layer, not a replacement for BoundedPoll and not permission to widen BoundedPoll behavior.

## Non-Goals

The Queue Runner is not:

- a background watcher
- always-on polling
- full autonomous development
- automatic commit, push, close, label, PR, merge, or force-push automation
- approval chaining
- a way to consume approval tokens
- broad issue scanning
- a scheduler or daemon
- multi-agent chaining
- a productization-first orchestration framework

## Task Risk Levels

### Low-Risk Tasks

Low-risk tasks may run sequentially inside one approved queue when they are explicitly listed in the queue definition and remain within the current repo, branch, HEAD, and issue bounds.

Examples:

- read-only audit
- `git status` or issue state check
- marker readback
- `DryRunBoundedPoll`
- `maybe-status-check`
- `LAWBRUNNER-RESULT` verification
- final read-only audit

Low-risk tasks must not stage files, create commits, push, close issues, edit labels, create PRs, merge, force-push, consume approvals, or modify original source documents.

### Medium-Risk Tasks

Medium-risk tasks may run only when explicitly approved for the queue, and the queue should stop after producing a reviewable artifact.

Examples:

- ReviewBundle generation
- docs-only candidate generation
- issue body audit update
- compact summary update

Medium-risk tasks are allowed to create reviewable local artifacts only within the approved scope. They do not authorize commit, push, close, labels, PRs, merges, or approval consumption. After a medium-risk task produces an artifact, the default next action is human or ChatGPT review.

### High-Risk Tasks

High-risk tasks must stop the queue and wait for explicit user approval through the existing rail for that operation.

Examples:

- local commit
- push
- close issue
- modifying runner code
- modifying dispatcher code
- modifying tests
- broad repo changes
- any unexpected diff
- any action beyond `maybe-status-check`

High-risk tasks must not be performed by the Queue Runner. They remain separate manually approved operations.

## Queue Definition

A queue definition should be explicit and bounded before execution starts.

Recommended fields:

- `queue_id`: operator-provided or generated id for the run
- `repo`: expected owner/name, currently `HarryWhite-TW/local-ai-workbench`
- `parent_issue`: GitHub issue that authorized the queue
- `branch`: expected local branch
- `head`: expected local `HEAD`
- `max_codex_tasks_per_batch`: maximum number of Codex task invocations allowed in this batch
- `max_runtime_minutes`: maximum wall-clock runtime
- `tasks`: ordered list of task nodes

Each task node should include:

- `task_id`
- `description`
- `risk_level`: `low`, `medium`, or `high`
- `allowed_action`
- `expected_inputs`
- `expected_outputs`
- `stop_after_completion`
- `approved_changed_files`, when writes are allowed

The queue must not infer extra tasks from natural language once execution begins. If the next needed step is not in the approved queue, the queue stops and reports that a new decision is required.

## Stop Rules

The Queue Runner must stop if:

- Codex quota or rate limit is detected
- tests fail
- git status contains unexpected files
- diff exceeds approved scope
- marker mismatch occurs
- duplicate current marker ambiguity occurs
- action is unsupported
- branch, repo, or HEAD mismatch occurs
- high-risk task is reached
- task node is complete and `stop_after_completion` is true
- Codex is uncertain whether it should continue
- queue runtime exceeds `max_runtime_minutes`
- task count exceeds `max_codex_tasks_per_batch`
- a required validation cannot be performed
- GitHub or local repo state is unreadable
- the queue result cannot be emitted

Stopping is a successful safety behavior when the stop reason is explicit and the result is structured.

## Codex Quota Handling

It may not be possible to know exact remaining Codex quota before a run starts. The queue design should therefore rely on conservative bounds and immediate stop behavior.

Required controls:

- `max_codex_tasks_per_batch`
- `max_runtime_minutes`
- no automatic retry after quota or rate-limit
- no continuation after quota or rate-limit without explicit user approval

If quota or rate-limit is detected, the Queue Runner must stop immediately and emit a queue result with:

- `result = "stopped"`
- `stop_reason = "quota_or_rate_limit_detected"`
- `quota_or_rate_limit_detected = true`
- no further task execution

Retrying after quota or rate-limit is a human gate.

## Human Gate Rules

Explicit user approval is required for:

- commit
- push
- close issue
- modifying runner code
- modifying dispatcher code
- modifying tests
- expanding the action allowlist
- enabling a background watcher
- increasing issue scope above approved bounds
- retrying after quota or rate-limit
- continuing after unexpected diff or test failure

Approval must be specific to the operation and current state. A queue approval does not imply commit approval, push approval, close approval, or permission to consume any existing approval marker.

## Queue Result Format

Future implementations should emit a machine-readable result with this marker:

```text
QUEUE-RUNNER-RESULT protocol=lawb.queue_runner_result.v1
```

The marker line should be followed immediately by parseable JSON. Consumers should not need Markdown fence parsing to recover the result.

Recommended shape:

```json
{
  "schema": "lawb.queue_runner_result.v1",
  "repo": "HarryWhite-TW/local-ai-workbench",
  "parent_issue": 99,
  "queue_id": "<queue-id>",
  "branch": "master",
  "head": "<sha>",
  "result": "success | stopped | failed",
  "completed_tasks": [
    {
      "task_id": "<task-id>",
      "risk_level": "low",
      "action": "<action>",
      "result": "success",
      "summary": "<short-summary>"
    }
  ],
  "skipped_tasks": [
    {
      "task_id": "<task-id>",
      "reason": "<reason>"
    }
  ],
  "stopped_at_task": "<task-id-or-null>",
  "stop_reason": "<reason-or-null>",
  "risk_gate": "none | medium_review | high_risk_user_approval",
  "quota_or_rate_limit_detected": false,
  "changed_files": [],
  "validations": {
    "repo_match": {
      "status": "passed",
      "summary": "Repo matched the approved queue definition."
    },
    "branch_match": {
      "status": "passed",
      "summary": "Branch matched the approved queue definition."
    },
    "head_match": {
      "status": "passed",
      "summary": "HEAD matched the approved queue definition."
    },
    "git_status_scope": {
      "status": "passed",
      "summary": "Changed files stayed within the approved queue scope."
    }
  },
  "safety": {
    "foreground_manual_start": true,
    "bounded_task_count": true,
    "bounded_runtime": true,
    "no_background_watcher": true,
    "no_stage": true,
    "no_commit": true,
    "no_push": true,
    "no_issue_close": true,
    "no_label": true,
    "no_pr": true,
    "no_merge": true,
    "no_approval_chaining": true,
    "no_approval_token_consumption": true
  },
  "next_recommended_action": "chatgpt_review"
}
```

Allowed validation statuses should match the existing runner result convention where practical: `passed`, `failed`, `not_run`, `warning`, and `reported`.

The queue result is an audit artifact. It is not an approval token and must not trigger follow-on actions by itself.

## Safety Invariants

Every Queue Runner design and future implementation slice must preserve these invariants:

- one manual foreground start per queue run
- finite task list
- finite runtime
- finite Codex task count
- explicit repo, branch, HEAD, and issue bounds
- no broad issue scan unless separately approved by design
- no background process that outlives the command
- no automatic retry loop
- no high-risk operation inside the queue
- no approval chaining
- no automatic transition from review artifact to commit, push, or close

## Future Implementation Slices

Potential future work should be split into small reviewable issues:

1. Docs-only Queue Runner design. This document.
2. Dry-run queue validator that reads a local queue definition and prints the planned task sequence only.
3. Queue result formatter that emits `QUEUE-RUNNER-RESULT` locally without executing tasks.
4. Low-risk queue execution for read-only audit and status checks only.
5. Medium-risk ReviewBundle handoff that stops after producing the review artifact.

No slice should add commit, push, close, labels, PRs, merges, force-push, approval consumption, approval chaining, background watcher behavior, runner code modification, dispatcher code modification, or test modification unless that exact slice is explicitly approved.

## Open Decisions For Later Issues

These decisions require separate approval before implementation:

- exact queue definition file or marker format
- whether queue definitions live in GitHub comments, local files, or both
- exact command-line syntax
- exact default values for `max_codex_tasks_per_batch` and `max_runtime_minutes`
- whether medium-risk docs-only candidate generation may write directly to docs files or only to a review bundle artifact
- whether queue results are local-only or may be posted to GitHub
- whether issue body audit updates are allowed, and under what marker
- whether compact summary updates are local-only or GitHub-visible
- exact behavior for partial success when one task completes and the next task stops

Until those decisions are approved, the Queue Runner remains a design target only.

## Runner Capability

```text
review-bundle
```

This design is review-bundle capable for docs-only Lv5-safe Queue Runner design documentation. It does not authorize stage, commit, push, issue close, labels, PRs, merges, force push, `PushOnce`, `CloseIssueOnce`, dispatcher `PollOnce`, `BoundedPoll`, approval chaining, background watcher implementation, always-on polling, queue execution, runner code changes, dispatcher code changes, test changes, or feature implementation.

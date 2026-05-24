# Queue Runner Operator Example

This example demonstrates the safe Queue Runner flow for an operator:

```text
DryRunQueue -> low-risk RunQueue -> run-reviewbundle-handoff stop -> ChatGPT / human review
```

It is a foreground, manually started flow with no background watcher. It does not consume approval tokens, stage files, commit, push, close issues, edit labels, create PRs, merge, or chain approvals.

## Example Queue

Use `docs/queue_runner_reviewbundle_handoff_queue.example.json` as the explicit queue definition.

## Prepare The Queue

Copy the queue example to a temporary working file and replace `REPLACE_WITH_CURRENT_HEAD` with the current local `HEAD`:

```powershell
$head = git rev-parse HEAD
$queue = Get-Content .\docs\queue_runner_reviewbundle_handoff_queue.example.json -Raw
$queue = $queue.Replace("REPLACE_WITH_CURRENT_HEAD", $head)
$queue | Set-Content $env:TEMP\reviewbundle_handoff_queue.local.json -Encoding utf8
```

If the repo is already dirty because a ReviewBundle candidate is under review, add an `allowed_dirty_files` array to the temporary copy that lists exactly the current changed files. Do not add broad wildcards.

## Dry Run

Validate the explicit queue definition without executing queue tasks:

```powershell
.\scripts\local_runner_v2.ps1 -DryRunQueue -QueueFile $env:TEMP\reviewbundle_handoff_queue.local.json
```

Expected review signal:

- `QUEUE-RUNNER-RESULT protocol=lawb.queue_runner_result.v1`
- parseable JSON immediately after the marker
- `dry_run=true`
- no task execution
- safety flags remain true

## Run The Safe Smoke

Run the same queue to execute the approved low-risk read-only tasks and stop at the medium-risk ReviewBundle handoff:

```powershell
.\scripts\local_runner_v2.ps1 -RunQueue -QueueFile $env:TEMP\reviewbundle_handoff_queue.local.json
```

Expected review signal:

- low-risk tasks complete before the handoff
- `run-reviewbundle-handoff` is reached
- the queue stops with `stop_reason=reviewbundle_handoff_completed`
- the high-risk task after the handoff is not executed
- no stage, commit, push, close, label, PR, merge, or approval chaining occurs
- `next_recommended_action=chatgpt_review`

The result packet is the Single Review Packet for ChatGPT or human review. It is not an approval token for commit, push, close, or any other follow-on action.

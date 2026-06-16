# Bridge Operator B3-A Runbook

## Purpose

Bridge Operator B3-A is the foreground dry-run bounded loop foundation for
Bridge Operator Phase B3.

B3-A proves fixed Inbox polling, loop bounds, local runtime state, heartbeat,
lock, pause, stop, logs, and fail-closed behavior. It does not invoke
Dispatcher, Runner, Codex, or GitHub result writeback.

B3-A is development workflow tooling only. It is not Local
Document-to-Knowledge Workbench product runtime.

## Fixed Boundary

- Repository: `HarryWhite-TW/local-ai-workbench`
- Permanent Bridge Inbox: Issue `#147`
- Mode: foreground dry-run bounded loop
- Dispatcher invocation: forbidden
- Runner invocation: forbidden
- Codex invocation through Dispatcher/Runner: forbidden
- GitHub result comments: forbidden
- Broad Issue scanning: forbidden
- Latest/next Issue inference: forbidden
- Startup, tray UI, service, and MCP behavior: forbidden

## Production CLI

Run from the repository root:

```powershell
$env:PYTHONPATH='src'
python -m local_runner_bridge.bridge_operator_b3_cli --repo-root . --max-cycles 1 --poll-interval-seconds 0
```

Optional arguments:

```powershell
--repo HarryWhite-TW/local-ai-workbench
--github-token-env <ENV_VAR_NAME>
--state-dir <PATH>
```

The CLI always uses Inbox `#147`. Standard output is one parseable JSON
summary. Invalid arguments return nonzero and print a blocked JSON summary.

## Runtime State

Default state directory:

```text
%LOCALAPPDATA%\LocalAIWorkbench\BridgeOperator\
```

State files:

```text
state.json
dry_run_observations.jsonl
processed_requests.jsonl
operator.lock
heartbeat.json
operator.log
last_failure.json
pause.flag
stop.flag
```

B3-A may write `dry_run_observations.jsonl`. It must not mark a request as
truly processed. `processed_requests.jsonl` is reserved for B3-B/C after a
verified success or safe preexisting-result detection.

## Controls

- `pause.flag`: when present, the foreground loop records paused heartbeat/log
  state and skips request processing for that cycle.
- `stop.flag`: when present before a cycle, the foreground loop exits cleanly.
- `operator.lock`: prevents concurrent instances. Existing locks always block;
  stale locks are not silently removed.

## Failure Handling

B3-A fails closed for unsupported repository, non-`#147` Inbox, invalid loop
bounds, active lock, corrupted local state, missing `%LOCALAPPDATA%` without an
explicit state directory, and bounded GitHub read failure.

On failure, B3-A writes `last_failure.json` when the state directory is usable.
Logs state whether Dispatcher, Runner, Codex, or GitHub writeback was reached;
for B3-A these must remain false.

## Recovery

Review the JSON summary, `operator.log`, `heartbeat.json`, and
`last_failure.json`. Do not delete `operator.lock` until the foreground process
state and heartbeat have been inspected.

Manual `PollOnce` remains the recovery path, not the target daily workflow:

```powershell
.\scripts\local_dispatcher_v1.ps1 -PollOnce -IssueNumber <N> -PostResultComment
```

## Next Phase Boundary

B3-A does not authorize B3-B or B3-C. Real Dispatcher invocation,
`maybe-status-check` loop delegation, `run-reviewbundle` loop delegation,
startup behavior, tray UX, MCP, trusted-actor changes, action allowlist changes,
or any commit/push/close/label/PR/merge behavior require separate approval.

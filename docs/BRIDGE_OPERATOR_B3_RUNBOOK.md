# Bridge Operator B3 Runbook

## Purpose

Bridge Operator B3 is the foreground bounded loop layer for Bridge Operator
Phase B3.

B3-A proves fixed Inbox polling, loop bounds, local runtime state, heartbeat,
lock, pause, stop, logs, and fail-closed behavior. It does not invoke
Dispatcher, Runner, Codex, or GitHub result writeback.

B3-B adds the first real Dispatcher delegation slice for exactly one eligible
`maybe-status-check` request. It delegates through the existing Dispatcher
`PollOnce` path, verifies one matching `LAWBRUNNER-RESULT`, and writes
`processed_requests.jsonl` only after verified success.

B3-C adds the explicit opt-in real Dispatcher delegation slice for exactly one
eligible `run-reviewbundle` request. It uses the same existing Dispatcher
`PollOnce` path and never invokes Runner or Codex directly.

B3 is development workflow tooling only. It is not Local
Document-to-Knowledge Workbench product runtime.

## Fixed Boundary

- Control repository: `HarryWhite-TW/local-ai-workbench`
- Permanent Bridge Inbox: control repository Issue `#147`
- Target repository: `HarryWhite-TW/local-ai-workbench` or exactly
  `HarryWhite-TW/human-approval-automation-gateway`
- Modes:
  - `b3a-dry-run`: foreground dry-run bounded loop
  - `b3b-maybe-status-check`: foreground bounded loop with real Dispatcher
    delegation for `maybe-status-check` only
  - `b3c-run-reviewbundle`: foreground bounded loop with real Dispatcher
    delegation for `run-reviewbundle` only
- Dispatcher invocation: forbidden in B3-A; allowed once per unprocessed
  eligible request in B3-B or B3-C
- Runner invocation: forbidden
- Codex direct invocation: forbidden
- `maybe-status-check` in B3-C: forbidden unless separately configured as B3-B
- `run-reviewbundle` in B3-B: forbidden
- Broad Issue scanning: forbidden
- Latest/next Issue inference: forbidden
- Startup, tray UI, service, and MCP behavior: forbidden

Inbox `#147` is shared by the two exact supported target repositories. B1
globally safety-validates every marker-like comment before B3 sees a selected
request. Lifecycle counts, processed-record matching, current ambiguity, and
selection are then scoped to B3's configured target repository. Valid history
for the other supported repository is ignored for selection rather than
treated as authority; malformed, untrusted, unsupported-repository,
unsupported-action, and requester-mismatched markers still fail closed. This
does not expand repository, trusted-actor, action, fixed-Inbox, Dispatcher, or
Runner authority.

## Canonical Repository Launcher

Run the canonical launcher from the repository root for routine local use:

```powershell
.\scripts\start_bridge_operator_b3c.ps1
```

This default invocation is preflight-only. It verifies the repository, reviewed
runtime bindings, and existing operator state without reading Inbox `#147` or
invoking B3. It does not create another Bridge or polling loop.

One bounded foreground B3-C run requires an explicit switch:

```powershell
.\scripts\start_bridge_operator_b3c.ps1 `
  -StartForeground `
  -MaxCycles 1 `
  -PollIntervalSeconds 0 `
  -TimeoutSeconds 600
```

The launcher reuses the existing B3-C CLI. Its reviewed `PATH` and `PYTHONPATH`
bindings are process-local only: it does not install tools, repair
authentication, or persist a PATH change. Manual Dispatcher `PollOnce` remains
recovery only, not the routine entrypoint.

### Optional ChatGPT-readable status publication

Status publication is disabled by default. The ordinary preflight command and
`-StartForeground` by itself make no status API call and preserve
`github_write_performed_directly=false`. Publication requires the explicit
`-PublishStatus` switch:

```powershell
.\scripts\start_bridge_operator_b3c.ps1 -PublishStatus
```

The destination is hard-coded to
`HarryWhite-TW/local-ai-workbench` Issue `#147`. It cannot be redirected by a
launcher argument, target repository, or remote request. Even when B3-C targets
HAG, the status destination remains the control repository Inbox. Every status
API call also fixes `--hostname github.com`; `GH_HOST`, `GH_REPO`, launcher
arguments, target repository configuration, and remote request text cannot
redirect it. The launcher uses only the authenticated, reviewed `gh` executable
returned by bootstrap; it does not discover a replacement, repair
authentication, or create an Issue.

Each invocation has a new 32-character lowercase GUID `run_id`. A status
comment begins with:

```text
LAWBRIDGE-STATUS protocol=lawb.bridge_status.v1
```

The marker is a machine-readable status surface, not discussion and not B1
request authority. B1 continues to recognize only a standalone
`BRIDGE-INBOX-REQUEST` marker; status JSON cannot supply repository, action,
branch, HEAD, target Issue, or request authority.

For preflight-only use, the launcher creates at most one final `ready` or
`blocked` comment and performs no update. For
`-StartForeground -PublishStatus`, a ready preflight creates one `running`
comment. Only a successful create response containing a positive integer
comment identity permits the operator to start. After the one foreground run,
the launcher updates that same identity at most once with the final
`completed` or `blocked` status. It never searches for or reuses an older
status comment, creates a replacement comment, or retries create/update.

If the reviewed `gh` is unavailable or unauthenticated, the launcher performs
no publication and blocks locally with `status_publication_unavailable`. An
explicit create/update failure means that the write process definitely did not
start, including a local invocation-contract rejection. Once the process has
started, any result without a verified zero exit and matching positive-integer
comment identity is uncertain; this includes invocation exceptions, nonzero
exit, timeout, undecodable or malformed response, missing/invalid identity, and
update identity mismatch. Uncertain create blocks the operator; uncertain
update does not rerun it. Both cases fail closed without a retry or replacement
comment, and an uncertain result alone never sets
`github_write_performed_directly=true`.

The status `repository`, `branch`, and `head` describe the validated execution
target. The local-ai-workbench target uses the validated control checkout
identity. A valid HAG target uses the independently validated HAG checkout
branch and HEAD, never the control checkout HEAD. If the HAG target is missing
or invalid, its status still names the HAG repository but publishes empty
`branch` and `head` fields with the relevant blocker.

The remote JSON is rebuilt from this whitelist only, in stable order:

- `protocol`
- `run_id`
- `observed_at_utc`
- `stage`
- `result`
- `repository`
- `branch`
- `head`
- `launch_requested`
- `operator_invoked`
- valid `request_id`, when present
- positive integer `target_issue`, when present
- `dispatcher_invoked`
- `dispatcher_result_writeback_reached`
- `dispatcher_result_writeback_verified`
- `target_result_verified`
- sanitized and deduplicated `blocked_reasons`
- deterministic-code `next_action`

The remote surface excludes local repository/target/state paths, reviewed tool
paths, usernames, credentials, tokens, environment values, stdout, stderr,
`operator_stderr_summary`, raw operator summaries, Task Packets, source, diffs,
logs, evidence files, and GitHub API response bodies. Unexpected blocked reason
text becomes `unknown_blocked_reason`; it is never copied verbatim.

This implementation package uses only fake `gh` tests. It does not perform or
claim a live Issue write, live daily-UX acceptance, `HOME-B3C-02`,
`B3C-OPS-02`, startup, tray, service, or MCP acceptance. Any real status
publication remains a separately supervised operation.

The direct `python -m local_runner_bridge.bridge_operator_b3_cli` command below
is an advanced/internal command, not the preferred routine entrypoint. This
launcher node does not prove a real live B3-C task, daily UX, live status
publication, `B3C-OPS-02`, `HOME-B3C-02`, startup, tray, service, or MCP
acceptance.

## Advanced/Internal CLI Invocation

Run from the repository root:

```powershell
$env:PYTHONPATH='src'
python -m local_runner_bridge.bridge_operator_b3_cli --repo-root . --max-cycles 1 --poll-interval-seconds 0
```

B3-B maybe-status-check mode:

```powershell
$env:PYTHONPATH='src'
python -m local_runner_bridge.bridge_operator_b3_cli --repo-root . --max-cycles 1 --poll-interval-seconds 0 --mode b3b-maybe-status-check
```

Optional arguments:

```powershell
--repo HarryWhite-TW/local-ai-workbench
--target-repo-root <EXPLICIT_LOCAL_TARGET_PATH>
--github-token-env <ENV_VAR_NAME>
--state-dir <PATH>
--mode b3a-dry-run|b3b-maybe-status-check|b3c-run-reviewbundle
--timeout-seconds <SECONDS>
```

`--repo-root` remains the control repository root. The local target defaults
to that path only for the local-ai-workbench compatibility case. HAG requires
an explicit local `--target-repo-root`; remote request text cannot supply it.

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
truly processed.

B3-B and B3-C write `processed_requests.jsonl` only after Dispatcher exit `0`
and one matching verified result. They never write processed-request state for
Dispatcher failure, timeout, exception, missing result, untrusted result author,
identity mismatch, dirty repo, wrong HEAD, pause, stop, or active lock.
Already processed `request_id` values are skipped and do not rerun Dispatcher.
New processed identities are keyed by target repository plus `request_id`.
Historical records without repository identity are compatible only with the
local-ai-workbench target and never establish HAG completion.

There are two valid processed-record paths:

1. Ordinary verified Dispatcher completion:
   - Dispatcher exits `0`;
   - exactly one trusted matching success result exists;
   - the processed record is written with Dispatcher provenance.
2. Durable `COMPLETED` reconciliation:
   - exactly one trusted matching completion exists;
   - local `CONSUMED` state is reconstructed before Dispatcher delegation;
   - `dispatcher_invoked=false`;
   - strict reconciliation provenance is recorded;
   - no new GitHub write occurs.

Local processed state remains the first duplicate gate. `NOT_FOUND` is the only
durable reconciliation decision that may proceed to ordinary delegation.
`BLOCKED` and `ERROR` fail closed.

`github_write_performed=false` means the Bridge Operator itself did not perform
a direct GitHub write. B3-B records Dispatcher-mediated result publication with
separate evidence fields:

```text
dispatcher_result_writeback_reached
dispatcher_result_writeback_verified
```

Both fields remain false in B3-A. In B3-B, `dispatcher_result_writeback_reached`
becomes true only when a matching `LAWBRUNNER-RESULT` is found on the target
Issue after Dispatcher execution. `dispatcher_result_writeback_verified` becomes
true only when that matching result is trusted and successful. Operator logs and
`last_failure.json` include the same two fields for review.

`current_delegation_outcome` is cycle-local audit evidence. It is reset before
every loop cycle, then a current-cycle delegation path may set it to
`durable_completion_reconciled`, `local_processed_request_already_seen`, or
`verified_dispatcher_result`. Safe-wait, pause, stop, or no-request cycles must
not reuse a prior cycle's outcome. Cumulative counters such as
`dispatcher_invocation_count` and `durable_reconciliation_read_attempts` remain
cumulative across the run.

## B3-B/B3-C Dispatcher Contract

B3-B and B3-C do not reimplement Dispatcher policy. They delegate through the
existing Dispatcher command equivalent to:

```powershell
.\scripts\local_dispatcher_v1.ps1 -PollOnce -IssueNumber <target_issue> -PostResultComment
```

The production invoker builds an argument array, captures stdout and stderr
with UTF-8 decoding and `errors="replace"`, and uses a bounded timeout. Tests
inject a fake Dispatcher invoker and do not call the real Dispatcher, Runner,
Codex, or GitHub write path.

Dispatcher and Runner scripts are always loaded from the control repository.
Their target repository/root arguments bind Git inspection, Runner/Codex
working directory, Task Packet evaluation, candidate evidence, result
publication/verification, and durable reconciliation to the target.

B3-B blocks or skips before Dispatcher when:

- the request action is not exactly `maybe-status-check`;
- the request was already written to `processed_requests.jsonl`;
- B1 validation fails;
- local readiness reports a dirty repo or wrong HEAD;
- pause, stop, or active lock controls are present.

B3-C blocks or skips before Dispatcher when:

- the request action is not exactly `run-reviewbundle`;
- the request was already written to `processed_requests.jsonl`;
- B1 validation fails;
- local readiness reports a dirty repo or wrong HEAD;
- pause, stop, or active lock controls are present.

After Dispatcher success, B3-B and B3-C verify a target Issue result comment:

```text
LAWBRUNNER-RESULT protocol=lawb.runner_result.v1
```

The JSON payload must match:

```text
schema=lawb.runner_result.v1
issue=<target_issue>
action=<maybe-status-check|run-reviewbundle>
repo=HarryWhite-TW/local-ai-workbench
branch=<expected_branch>
head=<expected_head>
request_id=<target_dispatch_request_id>
result=success
```

The result author must remain trusted by GitHub metadata. Missing, duplicate,
untrusted, malformed, mismatched, or failure results fail closed and do not
write processed-request state.

## Controls

- `pause.flag`: when present, the foreground loop records paused heartbeat/log
  state and skips request processing for that cycle.
- `stop.flag`: when present before a cycle, the foreground loop exits cleanly.
- `operator.lock`: prevents concurrent instances. Existing locks always block;
  stale locks are not silently removed.

## Failure Handling

B3 fails closed for unsupported repository, non-`#147` Inbox, invalid loop
bounds, active lock, corrupted local state, missing `%LOCALAPPDATA%` without an
explicit state directory, and bounded GitHub read failure.

On failure, B3 writes `last_failure.json` when the state directory is usable.
Logs state whether Dispatcher, Runner, Codex, or GitHub writeback was reached.
For B3-A these remain false. For B3-B and B3-C, `dispatcher_reached` may be
true, while Runner and Codex direct invocation remain false.

## Recovery

Review the JSON summary, `operator.log`, `heartbeat.json`, and
`last_failure.json`. Do not delete `operator.lock` until the foreground process
state and heartbeat have been inspected.

Manual `PollOnce` remains the recovery path, not the target daily workflow:

```powershell
.\scripts\local_dispatcher_v1.ps1 -PollOnce -IssueNumber <N> -PostResultComment
```

## Next Phase Boundary

B3-C does not authorize startup behavior, tray UX, MCP, trusted-actor changes,
action allowlist changes, or any commit/push/close/label/PR/merge behavior.
Those changes require separate approval.

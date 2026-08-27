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
`processed_requests.jsonl` only after one unique trusted identity-matching
terminal result.

B3-C adds the explicit opt-in real Dispatcher delegation slice for exactly one
eligible `run-reviewbundle`, `read-final-audit`, or `maybe-status-check` request.
`read-final-audit` is a request-bound, same-node dirty-candidate readback: Runner
re-reads the named trusted review-bundle parent and publishes only bounded,
digest-checked reviewer evidence without invoking Codex. It uses the same existing
Dispatcher `PollOnce` path and never invokes Runner or Codex directly.

B3 is development workflow tooling only. It is not Local
Document-to-Knowledge Workbench product runtime.

## Fixed Boundary

- Control repository: `HarryWhite-TW/local-ai-workbench`
- Normal control relay: control repository Issue `#279`
- Target repository: `HarryWhite-TW/local-ai-workbench` or exactly
  `HarryWhite-TW/human-approval-automation-gateway`
- Modes:
  - `b3a-dry-run`: foreground dry-run bounded loop
  - `b3b-maybe-status-check`: foreground bounded loop with real Dispatcher
    delegation for `maybe-status-check` only
  - `b3c-run-reviewbundle`: foreground bounded loop with real Dispatcher
    delegation for `run-reviewbundle`, `read-final-audit`, and the on-demand
    `maybe-status-check` probe
- Dispatcher invocation: forbidden in B3-A; allowed once per unprocessed
  eligible request in B3-B or B3-C
- Runner invocation: forbidden
- Codex direct invocation: forbidden
- `maybe-status-check` in B3-C: allowed through the same existing Dispatcher;
  Runner and Codex remain uninvoked for this action
- `run-reviewbundle` in B3-B: forbidden
- Broad Issue scanning: forbidden
- Latest/next Issue inference: forbidden
- service, scheduler, tray UI, daemon, second poller, and MCP behavior:
  forbidden

Control relay `#279` is shared by the two exact supported target repositories. B1
globally safety-validates every marker-like comment before B3 sees a selected
request. Lifecycle counts, processed-record matching, current ambiguity, and
selection are then scoped to B3's configured target repository. Valid history
for the other supported repository is ignored for selection rather than
treated as authority; malformed, untrusted, unsupported-repository,
unsupported-action, requester-mismatched, and relay-identity-mismatched markers still fail closed. This
does not expand repository, trusted-actor, action, fixed-Inbox, Dispatcher, or
Runner authority.

For the normal path, one standalone trusted `BRIDGE-INBOX-REQUEST` on `#279`
binds the target Issue, repository, branch, full HEAD, action, expiry, and
`request_id`. Its `target_dispatch_request_id` must equal that same
`request_id`. B1 passes this identity as a private local relay contract;
Dispatcher then freshly re-reads the exact `#279` GitHub comment, author
metadata, fields, and expiry before action execution. Normal operation does not require a target-Issue
`CHATGPT-DISPATCH` comment. The target Issue retains the Task Packet and
`LAWBRUNNER-RESULT`. Issue `#147` and direct `CHATGPT-DISPATCH` PollOnce remain
legacy/manual recovery compatibility, not the default B3 route.

## Canonical Repository Launcher

Run the canonical launcher from the repository root for routine local use:

```powershell
.\scripts\start_bridge_operator_b3c.ps1
```

This default invocation is preflight-only. It verifies the repository, reviewed
runtime bindings, and existing operator state without reading control relay `#279` or
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

### Local LAWB execution-worktree routing

The launcher and all control scripts remain rooted in the stable
`local-ai-workbench` control checkout. By default, that checkout is also the
LAWB execution target. To route routine Startup invocation to a separate local
LAWB engineering worktree without changing the Startup adapter, an operator may
manually create this optional file under the configured `StateDir`:

```text
repository_routing.json
```

Its exact schema is:

```json
{"protocol":"lawb.bridge_operator_local_routing.v1","repository":"HarryWhite-TW/local-ai-workbench","target_repo_root":"C:\\path\\to\\local-ai-workbench-engineering"}
```

The launcher only reads this file; it never creates, rewrites, repairs, or
deletes it. The three properties are exact, the repository is fixed to LAWB,
and `target_repo_root` must be a fully qualified, drive-qualified local Windows
filesystem path such as `C:\...`. Drive-relative paths such as
`C:engineering`, current-drive-root-relative paths such as `\engineering`, and
UNC or device/network namespace paths are rejected. A local interactive launch
may instead supply `-TargetRepoRoot` under the same path rules; configuring
both sources is ambiguous and fails closed. Missing configuration preserves
the control-checkout target.

Before operator launch, a separately selected LAWB target must be the exact Git
root, normalize to `HarryWhite-TW/local-ai-workbench` at `origin`, have a
readable branch and full 40-character HEAD, and have both a clean worktree and
empty staged area. Invalid JSON or encoding, unexpected properties, repository
mismatch, relative/invalid paths, or failed Git validation block without
changing the configuration. Remote Inbox, Issue, comment, dispatch marker,
Task Packet, status, and child result text never select or override this local
path. HAG continues to require its explicit local `-TargetRepoRoot` input and
does not use the LAWB routing file.

### Optional ChatGPT-readable status publication

Status publication is disabled by default. The ordinary preflight command and
`-StartForeground` by itself make no status API call and preserve
`github_write_performed_directly=false`. Publication requires the explicit
`-PublishStatus` switch:

```powershell
.\scripts\start_bridge_operator_b3c.ps1 -PublishStatus
```

The destination is hard-coded to
`HarryWhite-TW/local-ai-workbench` Issue `#279`. It cannot be redirected by a
launcher argument, target repository, or remote request. Even when B3-C targets
HAG, the status destination remains the control repository Inbox. Every status
API call also fixes `--hostname github.com`; `GH_HOST`, `GH_REPO`, launcher
arguments, target repository configuration, and remote request text cannot
redirect it. The launcher uses only the authenticated, reviewed `gh` executable
returned by bootstrap; it does not discover a replacement, repair
authentication, or create an Issue.

Each invocation has a new 32-character lowercase GUID `run_id`, also used as
the B3 `operator_session_id`. A status comment begins with:

```text
LAWBRIDGE-STATUS protocol=lawb.bridge_status.v1
```

The marker is a machine-readable status surface, not discussion and not B1
request authority. B1 continues to recognize only a standalone
`BRIDGE-INBOX-REQUEST` marker; status JSON cannot supply repository, action,
branch, HEAD, target Issue, or request authority.

The existing `lawb.bridge_status.v1` schema is retained. Backward-compatible
optional fields expose `operator_session_id`, `started_at_utc`,
`valid_until_utc`, `configured_max_cycles`,
`configured_poll_interval_seconds`, and `configured_timeout_seconds`. One
startup status is bounded session metadata, not continuing liveness proof.

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

For a timed status write, the launcher terminates the exact native process tree
with the operating-system-bound `%SystemRoot%\System32\taskkill.exe` and
`/PID <captured process id> /T /F`; `PATH` cannot redirect that cleanup.
The tree-termination command, its forced-cleanup wait, the post-termination
process wait, and stdout/stderr drain are all independently bounded to 3000,
1000, 2000, and 3000 milliseconds respectively. A timeout or unconfirmed
cleanup/drain remains an uncertain write outcome, so create does not start the
operator and update is never retried or replaced.

The status `repository`, `branch`, and `head` describe the validated execution
target. The local-ai-workbench target uses the validated control checkout
identity by default or the independently validated LAWB engineering-worktree
identity when local routing selects a different target. Failed target
validation publishes empty `branch` and `head` fields even when Git can still
read untrusted values. Later unrelated blockers do not erase an already
validated target identity. A valid HAG target likewise uses the independently
validated HAG checkout branch and HEAD, never the control checkout HEAD. If the
HAG target is missing or invalid, its status still names the HAG repository but
publishes empty `branch` and `head` fields with the relevant blocker.

The remote JSON is rebuilt from this whitelist only, in stable order:

- `protocol`
- `run_id`
- `operator_session_id`
- `started_at_utc`
- `valid_until_utc`
- `configured_max_cycles`
- `configured_poll_interval_seconds`
- `configured_timeout_seconds`
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
The final foreground update also imports only the child operator summary's
`blocked_reasons` array, merges it after launcher-owned reasons, and applies the
same validation and stable deduplication. Missing or null child reasons add
nothing; a non-array value, nested object, or unsafe string adds only
`unknown_blocked_reason`. The create payload never includes child reasons, and
the raw operator summary is never published.

This implementation package uses only fake `gh` tests. It does not perform or
claim a live Issue write, live daily-UX acceptance, `HOME-B3C-02`,
`B3C-OPS-02`, startup, tray, service, or MCP acceptance. Any real status
publication remains a separately supervised operation.

The direct `python -m local_runner_bridge.bridge_operator_b3_cli` command below
is an advanced/internal command, not the preferred routine entrypoint. This
launcher node does not prove a real live B3-C task, daily UX, live status
publication, `B3C-OPS-02`, `HOME-B3C-02`, startup, tray, service, or MCP
acceptance.

### On-demand health readiness

No periodic GitHub heartbeat is added. Before publishing a real task, ChatGPT
must publish a new unique `maybe-status-check` request through the existing
Inbox/Dispatcher route and treat the runtime as ready only when the result is
unique, trusted, protocol-valid, and an exact repository, Issue, action,
branch, HEAD, and request-ID match. The probe expiry may be at most 300 seconds
from evaluation, Dispatcher/result observation is bounded to 120 seconds, and
the verified probe may precede real-task publication by at most 60 seconds.
The durable terminal evidence records the local bounded observation timestamp.

Missing, multiple, conflicting, untrusted, malformed, unsupported, mismatched,
or provider-unavailable evidence means stale/unavailable. ChatGPT must not
publish the real task or infer health. The pre-dispatch negative reconciliation
plus the same bounded invocation's post-dispatch observation prevents an old
matching result from being mistaken for a fresh response.

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
--operator-session-id <32-character-lowercase-hex-session>
```

`--repo-root` remains the control repository root. The LAWB local target
defaults to that path, while the canonical launcher passes
`--target-repo-root` when local configuration or explicit local input selected
a different validated LAWB worktree. HAG requires an explicit local
`--target-repo-root`; remote request text cannot supply either repository's
local path.

The CLI always uses control relay `#279`. Standard output is one parseable JSON
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
in_flight.json
heartbeat.json
operator.log
last_failure.json
pause.flag
stop.flag
```

B3-A may write `dry_run_observations.jsonl`. It must not mark a request as
truly processed.

B3-B and B3-C write `processed_requests.jsonl` only after one unique trusted
identity-matching terminal result. `success` is `settled_success`; `failure`
and `blocked` are `settled_non_success`. All three suppress automatic rerun of
the same request ID. They never write processed-request state for Dispatcher
failure, timeout, exception, missing result, untrusted result author, malformed
or unsupported result, multiple/conflicting result, identity mismatch,
provider failure, dirty repo, wrong HEAD, pause, stop, or a non-recoverable
lock.
Already processed `request_id` values are skipped and do not rerun Dispatcher.
New processed identities are keyed by target repository plus `request_id`.
Historical records without repository identity are compatible only with the
local-ai-workbench target and never establish HAG completion.

There are two valid processed-record paths:

1. Ordinary verified Dispatcher completion:
   - Dispatcher exits `0`;
   - exactly one trusted matching `success`, `failure`, or `blocked` result
     exists;
   - the processed record is written with Dispatcher provenance.
2. Durable terminal reconciliation:
   - exactly one trusted identity-matching terminal completion exists;
   - local `CONSUMED` state is reconstructed before Dispatcher delegation;
   - `dispatcher_invoked` records whether this is pre-dispatch discovery or
     abnormal-restart recovery;
   - strict reconciliation provenance is recorded;
   - no new GitHub write occurs.

Local processed state remains the first duplicate gate. `NOT_FOUND` is the only
durable reconciliation decision that may proceed to ordinary delegation.
`COMPLETED` and `SETTLED_NON_SUCCESS` settle without redispatch. `BLOCKED` and
`ERROR` are uncertain and fail closed.

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
true only when that matching result is a trusted identity-matching terminal
result. `target_result_verified` does not rewrite terminal `failure` or
`blocked` as success. Operator logs and `last_failure.json` include the same
fields for review.

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

- the request action is neither `run-reviewbundle`, `read-final-audit`, nor
  `maybe-status-check`;
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
result=<success|failure|blocked>
```

The result author must remain trusted by GitHub metadata. A unique trusted
matching `failure` or `blocked` result is terminal non-success and is durably
settled without retry. Missing, duplicate, conflicting, untrusted, malformed,
unsupported, mismatched, or provider-unavailable results remain uncertain and
do not write processed-request state.

## Controls

- `pause.flag`: when present, the foreground loop records paused heartbeat/log
  state and skips request processing for that cycle.
- `stop.flag`: when present before a cycle, the foreground loop exits cleanly.
- `operator.lock`: protocol v2 records the operator session plus PID and exact
  process-start identity. A matching live process always blocks, even with a
  stale heartbeat. Legacy or invalid locks require exceptional manual
  recovery.
- `in_flight.json`: B3-owned protocol v1 evidence, durably written before
  Dispatcher invocation with atomic replace, flush/fsync, and exact readback.
  It records request identity, session/process identity, lifecycle stage,
  `dispatcher_invoked`, and terminal evidence when settled.

## Failure Handling

B3 fails closed for unsupported repository, non-`#279` control relay, invalid loop
bounds, active lock, corrupted local state, missing `%LOCALAPPDATA%` without an
explicit state directory, and bounded GitHub read failure.

On failure, B3 writes `last_failure.json` when the state directory is usable.
Logs keep the request identity and state whether Dispatcher result writeback
was reached. A structured Dispatcher-controlled outcome may additionally prove
that rejection occurred before Runner; otherwise Runner/Codex reach remains
unknown rather than being inferred from stderr. B3 never directly invokes
Runner or Codex.

## Recovery

Review the JSON summary, read-only diagnostics, `operator.log`,
`heartbeat.json`, `last_failure.json`, `operator.lock`, and `in_flight.json`.
Do not delete either lifecycle file based on heartbeat age alone.

The durable ordering states are:

1. `NOT_ADMITTED`: no `in_flight.json`; a future run may process normally.
2. `PREPARED`: durable admission exists but Dispatcher is not recorded as
   invoked; restart is uncertain, preserves evidence, and never redispatches.
3. `DISPATCHED_NOT_LOCALLY_SETTLED`: Dispatcher returned or otherwise may have
   been invoked, but no durable processed record exists. Restart settles only
   one trusted identity-matching terminal result; every other outcome remains
   uncertain and is never retried.
4. `REJECTED_BEFORE_RUNNER`: Dispatcher returned the parent-controlled,
   deterministic pre-Runner admission-rejection outcome. Restart completes only
   the local terminal non-success settlement; it does not redispatch and does
   not claim a GitHub result was written. A typed transient or environmental
   failure proven before Runner does not enter this terminal stage or create a
   processed record, so a later independent operator run may retry it.
5. `PROCESSED`: the processed record is durable; restart skips the request and
   clears only the exact matching in-flight evidence.

Automatic dead-lock quarantine is allowed only for a complete protocol-v2
lock when the PID is absent or its process-start identity proves PID reuse,
the descendant snapshot is empty, and no unresolved in-flight remains. A
settleable dispatched in-flight must first reconcile. The original lock is
atomically renamed to `operator.lock.quarantine.<session>.<digest>.json` with
exact bytes preserved; the new session then uses exclusive lock creation.
Live, descendant-present, uncertain, invalid, legacy, PREPARED, and unresolved
states remain blocked without deletion or redispatch. Truly ambiguous stopped
state requires a separately ChatGPT-approved bounded local recovery; there is
no second service or control plane.

Manual `PollOnce` remains an exceptional, separately approved diagnostic or
recovery command, not the target daily workflow. It must never retry an
uncertain in-flight request or reuse its request ID:

```powershell
.\scripts\local_dispatcher_v1.ps1 -PollOnce -IssueNumber <N> -PostResultComment
```

## Next Phase Boundary

The bounded visible login Startup adapter below is the only approved startup
surface. B3-C does not authorize a service, scheduler, daemon, second poller,
tray UX, MCP, trusted-actor changes, further action allowlist changes, or any
commit/push/close/label/PR/merge behavior. Those changes require separate
approval.

## Read-only diagnostics

`bridge_diagnostics` reports the in-flight file presence/validity/stage and
session, lock metadata/process/descendant classification, quarantine evidence,
status freshness, and any exceptional recovery reason. It never creates,
deletes, quarantines, or rewrites lifecycle evidence and never calls
Dispatcher, Runner, Codex, or GitHub. An expired status is evidence for
attention, not proof that a matching live process is dead.

## Optional Visible Login Startup Adapter

The separately approved B3-C login-startup adapter manages one current-user
Windows Startup-folder file:

```text
LocalAIWorkbench-BridgeOperator-B3C.cmd
```

It is disabled by default and has no implicit operation. Inspect, enable, or
disable it explicitly from the repository root:

```powershell
.\scripts\configure_bridge_operator_b3c_startup.ps1 -Status
.\scripts\configure_bridge_operator_b3c_startup.ps1 -Enable
.\scripts\configure_bridge_operator_b3c_startup.ps1 -Disable
```

Every command emits one JSON summary. Status is read-only and distinguishes an
absent entry, the exact enabled entry, unrecognized content, drifted/invalid
managed content, and a blocked adapter. Enable is idempotent only for the exact
managed content. Disable removes only that exact content and is idempotent when
the entry is absent. Both refuse an unrecognized or drifted file.

The managed command opens a visible Windows PowerShell console and invokes the
canonical repository launcher with fixed values:

```text
-StartForeground
-PublishStatus
-MaxCycles 960
-PollIntervalSeconds 30
-TimeoutSeconds 600
-StateDir %LOCALAPPDATA%\LocalAIWorkbench\BridgeOperator
```

This starts a bounded 960-cycle session. The configured lifecycle validity is
eight hours (`960 * 30` seconds); it is not a permanent background service or
an infinite loop. Startup publishes one session status using the existing
status schema, while actual health before a real task still requires the
on-demand probe above.
The existing `pause.flag` and `stop.flag` mechanisms remain available:
`pause.flag` pauses request processing for subsequent cycles, while
`stop.flag` exits the foreground loop cleanly.

The file is deterministic UTF-8 without a BOM and carries the ownership marker
`LAWBRIDGE-B3C-STARTUP-MANAGED`. The adapter uses only the logged-in user's
standard Startup folder. Its temporary-directory override is test-only and
requires the explicit `LAWB_STARTUP_ADAPTER_TEST_ONLY=1` test-process guard.

This adapter does not start the operator while configuring it, create a
scheduled task, Registry autorun entry, Windows service, tray process,
persistent PATH change, authentication material, or another execution path.
It does not represent Task Scheduler, Registry, service, tray, or unbounded
loop behavior. The canonical launcher retains repository/tool/state preflight,
fixed control relay `#279`, one-task behavior, locking, pause/stop controls, logging,
durable duplicate suppression, and no Codex auto-retry. Manual Dispatcher
`PollOnce` remains recovery only.

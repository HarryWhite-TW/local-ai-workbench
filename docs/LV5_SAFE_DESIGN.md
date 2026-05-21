# Lv5-Safe Bounded Polling Design

## Purpose

Lv5-safe is the proposed next workflow after the successful Lv5-lite trial. It is a bounded polling design for the local dispatcher path, not an implementation plan for always-on automation.

The design keeps the repository aligned with the `Local Document Assistant Prototype` showcase: a localhost, single-user, personal-use document workbench with explicit review and approval boundaries. Lv5-safe may reduce manual checking, but it must not expand authority beyond the current safe dispatch contract.

This document is the Lv5-safe design and boundary record. It does not authorize runner code changes, dispatcher code changes, watcher implementation, background polling, automatic commit, automatic push, issue close, label edits, PR creation, merge, approval chaining, or test changes.

For the operator-facing SOP after the completed #89 through #97 smoke path, see [Lv4.5 Operating SOP](LV45_OPERATING_SOP.md). That SOP documents the verified `-DryRunBoundedPoll`, single-issue `-BoundedPoll -IssueNumber`, duplicate/idempotency, and multi-issue `-BoundedPoll -IssueNumbers` usage.

For the future workflow layer after completed BoundedPoll, see [Lv5-Safe Queue Runner Design](LV5_SAFE_QUEUE_RUNNER_DESIGN.md). That document is design-only and does not authorize queue execution, background watching, approval chaining, automatic commit, automatic push, or issue close.

## Baseline

The current baseline is:

- Lv4.5 manual `PollOnce` dispatcher behavior is documented in [Lv4.5 Operating SOP](LV45_OPERATING_SOP.md).
- `CHATGPT-DISPATCH protocol=lawb.dispatch.v1` is the request marker.
- `LAWBRUNNER-RESULT protocol=lawb.runner_result.v1` is the structured result marker.
- The active low-risk dispatch action is `maybe-status-check`.
- Dispatch remains issue-scoped, repo-bound, branch-bound, HEAD-bound, and expiry-bound.
- Invalid, unsupported, duplicate, stale, or mismatched markers fail closed.

Expected baseline HEAD for this design issue:

```text
7e6ed35f304489e86687668961f888e69ed5a0bb
```

## What Lv5-Safe Means

Lv5-safe means bounded, foreground polling with explicit scope, explicit limits, and fail-closed execution.

It is safe because:

- the user still starts each run manually
- the poller has a finite issue scope
- the poller has a finite runtime
- the action set is allowlisted
- every accepted dispatch is bound to an issue, repo, branch, HEAD, expiry, and request id
- duplicate or ambiguous dispatch state stops execution
- results are issue-bound and machine-readable
- no approval-gated operation can be performed through the dispatch marker

Lv5-safe is not a daemon, scheduler, or continuous watcher. It is a constrained local tool mode that can inspect a small, explicit scope and stop.

## Workflow Levels

### Lv4.5

Lv4.5 is the current daily operating procedure:

- user chooses one explicit issue
- user runs `PollOnce`
- dispatcher evaluates that issue only
- dispatcher may run one allowed low-risk action
- dispatcher may post one `LAWBRUNNER-RESULT` comment for the same issue
- dispatcher stops

Lv4.5 is the safety baseline for all later levels.

### Lv5-Lite

Lv5-lite is the first limited daily workflow trial beyond the Lv4.5 manual bridge. It proves that the same marker/result contract can support a more repeatable operator workflow without adding broad automation authority.

Lv5-lite does not imply continuous polling, broad scanning, automatic retries, or approval consumption.

### Lv5-Safe

Lv5-safe is bounded polling over a constrained issue scope. It may support:

- manual single issue polling
- bounded issue list polling
- short time-window polling
- dry-run evaluation

Lv5-safe keeps all Lv4.5 safety checks and adds usage limits, claim strategy, idempotent result checks, and emergency stop controls.

### Deferred Full Lv5

Full Lv5 remains deferred. It would involve broader automation questions that are not authorized by this design:

- background watcher behavior
- scheduler behavior
- longer-running automation
- richer action sets
- automatic retries
- multi-step execution
- any approval-gated workflow integration

Those choices require separate explicit approval and are outside this document.

## Safe Polling Modes

### Manual Single Issue Polling

Manual single issue polling is the Lv4.5-compatible mode:

```text
poll issue #N once, then stop
```

Rules:

- exactly one issue is selected by the operator
- only current valid markers on that issue are considered
- zero current markers means no action
- one valid current marker may be accepted
- duplicate current markers fail closed
- result posting targets the same issue only

### Bounded Issue List Polling

Bounded issue list polling accepts an explicit finite list:

```text
poll issues #N, #M, #K once each, then stop
```

Rules:

- issue numbers must be supplied explicitly
- the list must have a configured maximum size
- each issue is evaluated independently
- one accepted dispatch on one issue must not authorize action on another issue
- results must be posted only to the issue that supplied the accepted marker
- ambiguous state on one issue should not widen scope to other issues

Recommended first implementation slice:

```text
max_issues_per_run = 3
```

### Short Time-Window Polling

Short time-window polling repeatedly checks an explicit scope for a short local runtime:

```text
poll the explicit issue list for up to T seconds, then stop
```

Rules:

- the issue scope is still explicit
- the runtime limit is mandatory
- the poll interval is bounded
- the run stops when time expires
- the run stops when a local emergency stop is detected
- no continuous high-frequency loop is allowed

Recommended first implementation slice:

```text
max_runtime_seconds = 60
min_poll_interval_seconds = 10
```

### Dry-Run Mode

Dry-run mode evaluates markers and reports what would happen without running the action or posting result comments.

Rules:

- dry-run must not execute dispatch actions
- dry-run must not post GitHub comments
- dry-run may print local structured output
- dry-run should include the same validation decision that a real run would use
- dry-run should identify accepted, rejected, expired, duplicate, and unsupported markers

Dry-run is the preferred first implementation target for Lv5-safe because it tests selection and safety logic before side effects.

## Safety Rules

### Explicit Issue Scope

Every run must start with an explicit issue number or explicit issue list. Label search, broad repo scanning, open-ended issue queries, and "all issues" modes are not part of Lv5-safe.

### Action Allowlist

The dispatcher may run only implemented allowlisted dispatch actions.

Initial allowlist:

```text
maybe-status-check
```

Reserved or unknown actions must fail closed. Commit, push, close, label, PR, merge, force-push, approval consumption, and any indirect form of those operations are forbidden through Lv5-safe dispatch.

### HEAD Binding

The marker `head=<sha>` must match the local repository HEAD for the intended branch. A mismatch fails closed before action execution.

The result payload must echo the accepted HEAD.

### Repo / Branch Binding

The marker must bind to:

```text
repo=HarryWhite-TW/local-ai-workbench
branch=master
```

The local checkout must match both values. A wrong repo or wrong branch fails closed.

### Marker Expiry

Markers must include an expiry in UTC basic format:

```text
expires=<UTC_BASIC>
```

Expired markers are not current. A run must not execute an expired marker. A short expiry window is preferred so stale comments do not remain actionable.

### Duplicate Marker Handling

Duplicate current markers on the same issue are ambiguous and must fail closed. This includes duplicates with different `request_id` values.

The poller must not choose the newest marker, oldest marker, or a marker by heuristic when more than one current marker exists.

### Idempotency

The same accepted dispatch must produce at most one result.

Idempotency should be based on:

- issue number
- `request_id`
- action
- repo
- branch
- HEAD
- accepted marker identity

Before posting a result or executing a real action, the poller should check whether a matching `LAWBRUNNER-RESULT` already exists for the accepted dispatch. If it exists, the poller should report already-handled and skip action execution.

### Fail-Closed Behavior

Lv5-safe must stop without running the action when it detects:

- no explicit issue scope
- too many issues
- max runtime exceeded
- emergency stop
- malformed marker
- expired marker
- duplicate current marker
- unsupported action
- forbidden action
- repo mismatch
- branch mismatch
- HEAD mismatch
- issue mismatch
- missing request id
- claim conflict
- existing matching result
- result target mismatch
- GitHub read/write uncertainty for real mode

Failure should be visible in local output. Invalid markers must not create successful result comments.

## Usage Protection

Lv5-safe must be bounded by defaults and command-line limits:

- maximum runtime per run
- maximum issues per run
- minimum poll interval for any time-window mode
- no continuous high-frequency loop
- no automatic retry loop by default
- no scheduler or daemon mode
- no background process that outlives the foreground command

Recommended defaults for first real implementation:

```text
max_issues_per_run = 3
max_runtime_seconds = 60
min_poll_interval_seconds = 10
automatic_retry = false
```

Any retry behavior should require explicit separate design approval.

## Lock / Claim Strategy

Lv5-safe needs a simple claim strategy to avoid duplicate local executions.

Acceptable claim models:

- claim marker on the issue
- lock comment on the issue
- local run record keyed by issue and `request_id`

Preferred first strategy:

```text
issue-bound lock comment with run_id and request_id
```

The lock should include:

- protocol name
- issue number
- action
- request id
- run id
- repo
- branch
- HEAD
- timestamp

Example shape:

```text
LAWBRUNNER-CLAIM protocol=lawb.runner_claim.v1 issue=<N> action=maybe-status-check request_id=<id> run_id=<id> repo=HarryWhite-TW/local-ai-workbench branch=master head=<sha> created=<UTC_BASIC>
```

Rules:

- the claim is issue-bound
- a claim for one issue cannot authorize another issue
- a claim conflict fails closed
- dry-run mode does not post a claim
- real mode should claim before executing a real action
- after a successful result exists, later runs should skip instead of repeating work

If lock comments are considered too noisy later, a local lock file may be evaluated, but it must not become the only audit trail for accepted real dispatches.

## Result Strategy

Lv5-safe should continue to use `LAWBRUNNER-RESULT` comments.

Rules:

- one result per accepted dispatch
- result comments post to the same issue as the accepted marker
- result comments begin with `LAWBRUNNER-RESULT protocol=lawb.runner_result.v1`
- parseable JSON follows immediately after the marker line
- JSON includes `schema`, `repo`, `issue`, `action`, `result`, `branch`, `head`, `selected_issue`, `request_id`, `run_id`, `safety`, and `next_recommended_action`
- failure results should be machine-readable when a valid accepted dispatch was claimed but execution failed
- invalid or unaccepted markers should not produce success results

Recommended additional fields for Lv5-safe:

```json
{
  "poll_mode": "single_issue | issue_list | time_window | dry_run",
  "request_id": "<id>",
  "run_id": "<id>",
  "claim_id": "<id-or-null>",
  "idempotency_key": "<stable-key>",
  "already_handled": false
}
```

The result is an audit artifact. It is not an approval token and must not trigger follow-on actions by itself.

## Emergency Stop

Lv5-safe should support multiple stop mechanisms:

- local stop file
- command-line switch
- issue-level stop marker
- manual stop by not running the poller

### Local Stop File

Before each issue evaluation and before each action execution, the poller checks for a local stop file.

Recommended path:

```text
.lawb-stop
```

If present, the poller stops without executing additional actions.

### Command-Line Switch

A command-line switch should provide an immediate no-run path for operator validation.

Example:

```text
-Stop
```

This can be used to verify that stop handling is wired without evaluating issues.

### Issue-Level Stop Marker

An issue-level stop marker can make one issue non-actionable.

Example:

```text
LAWBRUNNER-STOP protocol=lawb.stop.v1 issue=<N> reason=<short-text>
```

If a current stop marker exists on an issue, the poller must not accept dispatch markers from that issue.

### Manual Stop

The simplest emergency stop remains manual: do not run the poller. Lv5-safe has no scheduler, no daemon, and no background watcher, so stopping local invocation is sufficient to stop future work.

## Future Implementation Slices

Implementation should be split into small reviewable steps:

1. Docs-only Lv5-safe design. Completed in #89.
2. Dry-run bounded poller that reads explicit issue scope and prints local decisions only. Completed and smoke-tested in #90 and #91.
3. Real bounded poller for `maybe-status-check` with issue-bound result comments. Completed and smoke-tested for a single issue in #92 and #93.
4. Duplicate/idempotency smoke covering existing matching `LAWBRUNNER-RESULT` by `request_id`. Completed in #94.
5. Multi-issue bounded smoke covering explicit child issues. Completed in #95, #96, and #97.
6. Optional future hardening, such as a negative smoke for more than three issues, time-window behavior, expiry, HEAD mismatch, existing result variants, and emergency stop.
7. Future docs-only Queue Runner design for manually started bounded task queues after BoundedPoll. Tracked separately in [Lv5-Safe Queue Runner Design](LV5_SAFE_QUEUE_RUNNER_DESIGN.md).

Each slice should have its own issue, review bundle, and verification notes. No slice should add commit, push, close, labels, PRs, merges, force-push, approval chaining, or background watcher behavior without separate explicit authorization.

## Non-Goals

Lv5-safe does not authorize:

- runner code changes from this design issue
- dispatcher code changes from this design issue
- test changes from this design issue
- watcher implementation
- background polling implementation
- continuous polling
- scheduler setup
- automatic retry loops
- automatic commit
- automatic push
- automatic issue close
- label edits
- PR creation
- merge
- force-push
- approval chaining
- multi-agent chaining
- modification of original source documents
- changes to the `Local Document Assistant Prototype` positioning

## Open Decisions For Later Issues

These decisions should be made only when implementation is explicitly authorized:

- exact command-line syntax for dry-run bounded polling
- exact maximum defaults and override limits
- whether claims are GitHub comments, local records, or both
- exact result JSON schema additions
- local log file path and retention
- whether issue-level stop markers expire
- whether failure results are posted for claimed dispatches that fail during execution

Until those decisions are approved, the optional future hardening items remain design targets, not active behavior.

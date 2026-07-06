# RV2-03 Recovery And Acceptance Lessons — 2026-07-06

## Purpose

This document records reusable engineering lessons from the course-computer recovery, D2 publication closeout, Primary Operational Host live acceptance, blocker repair, and evidence collection work performed on 2026-07-06.

It is not the canonical source for mutable state. Branches, SHAs, Issue or PR state, authentication, working-tree state, and tool availability must still be revalidated at task start.

## Lessons

### 1. Environment recovery requires current-state verification

A reset or restore-card computer may preserve project files while losing tools, authentication, local state, or previous assumptions.

Before execution, verify repository identity, branch, HEAD, local/remote divergence, clean working tree, staged area, virtual environment, test runner, Git, Node.js, GitHub CLI, Codex launcher, authenticated account, and applicable project instructions.

A recovery script is useful, but its output proves only the current run.

### 2. Tool presence and authentication validity are separate gates

A portable GitHub CLI can exist and run while its stored session is invalid or overridden by the current process environment.

Verify authentication explicitly before remote operations. Never print credentials. On shared or reset computers, sign out from GitHub, ChatGPT, Codex, and the browser before leaving.

### 3. UTF-8 BOM can break valid JSON

The Phase B publication manifest was valid JSON but began with UTF-8 BOM bytes. The preflight parser rejected it as malformed before schema validation.

For machine-readable JSON:

- write UTF-8 without BOM;
- verify raw bytes;
- run a strict parse probe;
- then run schema validation;
- do not publish markers when either step fails.

On Windows PowerShell 5.1, exact encoding should be written with a BOM-free UTF-8 encoder rather than assumed from default cmdlet behavior.

### 4. Outer-wrapper timeout does not automatically mean nested execution failure

The outer B3-C evidence wrapper timed out, but durable evidence showed that the nested chain had already completed:

```text
Bridge -> Dispatcher -> Runner -> Codex -> GitHub result
```

Runner and Codex exited successfully, one trusted result was published, local `CONSUMED` state was written, and the repository remained clean.

Before declaring a live chain failed, inspect target Issue comments, Runner review bundle, matching result, operator state, heartbeat, processed-request records, and Git status.

Classify the failure layer precisely: nested execution, result publication, result readback, local state write, or outer capture/termination.

### 5. Exact-once workflows should fail closed instead of retrying automatically

An ambiguous outer timeout creates pressure to rerun a command even when the nested chain may already have completed.

The safe sequence is:

1. stop;
2. preserve evidence;
3. inspect durable result surfaces;
4. determine whether a trusted completion exists;
5. reconcile or fail closed;
6. never republish or rerun the same request without a new explicit decision.

### 6. Per-cycle and cumulative state must be separated

`current_delegation_outcome` was reset only when delegation began. A later safe-wait cycle could therefore log the previous cycle's outcome.

Per-cycle fields must be reset at the cycle boundary before stop, pause, read, safe wait, failure handling, or delegation. Cumulative counters must remain cumulative.

Regression tests should inspect the actual second-cycle waiting log, not only the final summary.

### 7. Documentation must remain correct after merge

Wording such as “current master baseline” or “next gate is to repair and review” becomes stale immediately after the repair PR merges.

Prefer stable wording:

- historical merge baseline rather than permanent current master;
- “PR carries the repair” rather than claiming it is already merged;
- “next operational gate after merge” rather than describing the current repair as a future action;
- distinguish older Issue body text from newer append-only current-truth comments.

### 8. Evidence extraction must preserve meaning

Two evidence filenames were populated with the same machine-readable result even though one was intended to contain the full Runner review bundle.

Keep raw Issue comments in addition to extracted sections. Verify every evidence filename against its semantic contract and record comment IDs and URLs.

### 9. Successful silence is not durable evidence

`git diff --check` can succeed with no output. A pipeline that captures stdout only may fail to create the expected evidence file.

Evidence should record the command, exit code, stdout state, and stderr state explicitly, even when both streams are empty.

### 10. PowerShell archive semantics can be misleading

Using `-LiteralPath` together with a wildcard caused the ZIP step to resolve paths incorrectly.

For deterministic evidence ZIP creation:

- verify the evidence directory and checksum manifest exist;
- remove any old destination ZIP explicitly;
- use the .NET ZIP API when PowerShell archive parsing is ambiguous;
- verify the resulting file exists;
- record size and SHA-256.

### 11. Display corruption is not always data corruption

Non-ASCII punctuation appeared as `??`, and some JSON evidence was emitted in UTF-16LE and looked NUL-separated in simple viewers.

Prefer ASCII sentinel lines and UTF-8 without BOM. Validate structured content through parsing rather than appearance alone.

### 12. Codex quota limits are not repository failures

The focused documentation repair was complete and staged, but Codex could not perform the final commit and evidence write because its escalation quota was exhausted.

When remaining steps are deterministic and already approved, preserve state, verify exact branch/HEAD/staged files, and complete the mechanical Git steps manually. Do not redesign or rerun implementation because of agent quota.

### 13. Agent summaries are claims, not proof

Final review must still inspect branch, HEAD, local/remote refs, working tree, staged area, raw diff, test commands and exit codes, changed-file allowlist, PR metadata, review threads, durable result comments, and unverified items.

## Reusable Preflight Checklist

Before the next RV2-03 live acceptance:

1. Revalidate `master`, PR state, Issue state, authentication, and working tree.
2. Read applicable plans, specifications, runbooks, source, and tests.
3. Generate fresh request IDs and expiry.
4. Write JSON as UTF-8 without BOM.
5. Strict-parse and schema-validate before publication.
6. Publish each approved marker exactly once.
7. Run B1 read-only validation.
8. Execute the live chain no more than once.
9. Separate outer-wrapper status from nested durable evidence.
10. Preserve raw comments and state files.
11. Use a brand-new empty state directory for state-loss reconciliation.
12. Require zero Dispatcher, Runner, and Codex invocations during reconciliation.
13. Verify local `CONSUMED` reconstruction and the next local duplicate gate.
14. Record command exit codes even when output is empty.
15. Create the evidence ZIP deterministically and verify every hash.
16. Keep RV2-03 `ACTIVE` until all acceptance and closeout criteria pass.

## Scope And Safety

This document records experience only. It does not authorize live execution, publication, retry, merge, Issue closure, authority changes, startup work, RV2-03 completion, or RV2-04 activation.

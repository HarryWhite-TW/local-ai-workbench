# Bridge Operator Acceleration and Phase 3 Roadmap 143

## Purpose

This document records the current ChatGPT / Codex bridge operator rules, workflow acceleration policy, and Phase 3 roadmap.

This is a docs-only alignment artifact.

This document exists to prevent drift after #142.

This document does not implement a runner.

This document does not implement a dispatcher.

This document does not implement GitHub fetch.

This document does not implement GitHub writeback.

This document does not write a Task Packet.

This document does not write a Result Packet.

This document does not execute Codex-side action.

This document does not authorize autonomous commit, push, PR, merge, issue close, label change, always-on watcher, Lv5, or full automation.

## Direction Lock Binding

```text
Direction Lock Binding
plan_path=docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md
plan_version=v1
primary_goal=chatgpt_dispatches_to_codex_and_reads_results_back
issue_role=support
manual_copy_paste_is_target=false
must_emit_plan_read_audit=true
```

## Primary Goal Reminder

The strategic goal is not safer manual copy/paste.

The strategic goal is a ChatGPT-centered bridge where:

```text
User
-> ChatGPT
-> auditable Task Packet surface
-> local relay / runner / Codex-side process
-> bounded Codex-side work
-> auditable result surface
-> ChatGPT readback and review
-> user approval decisions through ChatGPT
```

Manual relay remains a temporary fallback only.

It must not be hidden as the target workflow.

## Current Completed State After #142

The project has completed the first read-only local validation layer.

Completed sequence:

```text
#138 read-only task packet validator
#139 validator hardening plan
#140 validator hardening implementation
#141 read-only task surface validation flow
#142 minimal read-only validation dry-run entry
```

Current local chain:

```text
stdin / local surface text
-> run_validation_dry_run()
-> validate_task_surface()
-> extract_task_packet()
-> validate_task_packet()
-> JSON summary
```

Current capability:

```text
A local dry-run can validate explicit Task Surface text and return a JSON validation summary.
```

Current non-capabilities:

```text
No GitHub issue fetch.
No GitHub result writeback.
No Result Packet write.
No Codex-side action execution.
No dispatcher.
No always-on watcher.
No Lv5.
No full automation.
```

## Why The Process Felt Slow

The #138 through #142 work used strict review sequencing because it touched the foundation of validation, flow, and dry-run behavior.

The strict sequence was useful for the first safety layer, but it is too slow if applied to every future issue.

The old default pattern was:

```text
ReviewBundle
-> code readback or diff audit
-> local commit approval
-> push approval
-> final audit
```

This pattern is still valid for high-risk work, but it must not be the default for all future work.

## Workflow Acceleration Policy

Future work must use risk lanes.

### Fast Lane

Use Fast Lane for:

```text
docs-only changes
roadmap documents
usage examples
fixtures
sample input/output
non-executable demo text
minor README notes
```

Fast Lane target:

```text
1 to 2 rounds
```

Allowed combined action:

```text
create or update allowed docs/example files
commit
push
final audit
```

Fast Lane must still forbid:

```text
code changes
runner implementation
dispatcher implementation
GitHub fetch/write implementation
Result Packet write
Codex-side action
dependency changes
PR / merge / issue close / label change
```

### Standard Lane

Use Standard Lane for:

```text
small local-only helpers
small adapters
CLI smoke tests
stdin/local file dry-run behavior
no external network
no GitHub write
no Result Packet write
no Codex-side action
```

Standard Lane target:

```text
2 to 3 rounds
```

Standard Lane may combine commit and push after ChatGPT review if:

```text
changed files are tightly bounded
targeted tests pass
no new authority is added
preflight and postflight checks are explicit
```

### Strict Lane

Use Strict Lane for:

```text
GitHub fetch
GitHub writeback
Result Packet write
Codex-side action
runner behavior
dispatcher behavior
approval handling
any external side effect
any automation authority expansion
```

Strict Lane keeps separate checkpoints:

```text
ReviewBundle
diff / code readback
commit approval
push approval
final audit
```

Strict Lane is intentionally slower.

## Issue Role Labels

Every future bridge-related issue should be described using:

```text
issue_role=core|support|fallback
risk_lane=fast|standard|strict
alignment=core|core_support|fallback|drift_detected
value_target=<one sentence>
```

Definitions:

```text
core = directly advances ChatGPT dispatch, relay/Codex execution, or ChatGPT result readback.
support = improves safety, auditability, validation, documentation, or demo value needed for core.
fallback = still relies on user manual relay and must remain explicitly temporary.
drift_detected = hides manual relay as target or optimizes around the missing bridge without saying so.
```

## Anti-Drift Rule

Support work must not run indefinitely.

If two consecutive support issues do not move the project closer to the bridge feasibility probe, ChatGPT should pause and ask for roadmap review.

Each future issue must answer:

```text
How does this move us closer to ChatGPT dispatch / Codex result readback?
```

If the answer is unclear, do not start the issue.

## Not-White-Busy Rule

Every future issue should satisfy at least one of:

```text
A. reduces manual relay work
B. makes task validation easier or safer
C. blocks errors earlier
D. improves demo value
E. enables the next bridge feasibility step
```

If an issue satisfies none of these, it should not be done.

## Phase 3 Goal

Phase 3 should move from local dry-run toward a bounded Bridge Feasibility Probe.

Phase 3 is not full automation.

Phase 3 should test the minimum bridge path:

```text
ChatGPT-readable task surface
-> explicit task fetch or read
-> local validation
-> later bounded result surface writeback
-> ChatGPT readback
```

Phase 3 must not introduce:

```text
always-on watcher
broad issue scan
unscoped GitHub issue scanning
autonomous commit
autonomous push
autonomous PR
autonomous merge
autonomous issue close
approval chaining
Lv5
full automation
```

## Proposed Phase 3 Roadmap

Recommended next issues:

```text
#144 Explicit GitHub Task Surface Fetch Plan
risk_lane=fast
issue_role=support
value_target=define exactly how a future read-only fetch may accept one explicit GitHub issue comment or URL without scanning.

#145 Read-only GitHub Task Surface Fetch Implementation
risk_lane=strict
issue_role=core
value_target=read one explicit GitHub task surface and pass its text to validate_task_surface without writing back.

#146 GitHub Fetch + Validation Smoke
risk_lane=strict
issue_role=core
value_target=prove explicit GitHub fetch plus local validation works end-to-end in read-only mode.

#147 Result Writeback Proof Plan
risk_lane=fast
issue_role=support
value_target=plan how a future result surface writeback should work without implementing it.

#148 Bounded Result Writeback Implementation
risk_lane=strict
issue_role=core
value_target=write a bounded result summary to an approved explicit result surface after validation.
```

This roadmap may be adjusted by ChatGPT and the user, but changes must preserve the Direction Lock primary goal.

## Immediate Next Recommendation

The next issue after #143 should not be another local validator polish task unless a clear blocker is found.

Recommended next issue:

```text
#144 Explicit GitHub Task Surface Fetch Plan
```

#144 should be docs-only and Fast Lane.

#145 should be the first Strict Lane implementation that touches GitHub fetch.

## Assistant Behavior Rules Going Forward

ChatGPT should:

```text
1. identify issue_role, risk_lane, alignment, and value_target before each issue
2. avoid defaulting every issue to Strict Lane
3. use Fast Lane for docs-only alignment artifacts
4. use Standard Lane for local-only helpers and smoke tests
5. use Strict Lane only for external side effects or automation authority
6. explicitly say when a task is support instead of core
7. prevent manual copy/paste from being reframed as the final target
8. stop after repeated support work if bridge progress stalls
9. prioritize visible workflow value after the safety foundation
10. keep the user approval boundary explicit
```

## Current Status Summary

```text
Phase 1 protocol / approval / smoke foundation: completed enough to proceed
Phase 2 read-only local validation layer: completed through #142
Phase 3 bridge feasibility probe: next
```

Current mainline direction:

```text
Move from local dry-run toward explicit GitHub task fetch, then validated result writeback, while preserving user approval through ChatGPT.
```

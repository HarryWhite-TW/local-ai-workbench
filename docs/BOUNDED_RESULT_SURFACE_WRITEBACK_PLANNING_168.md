# Bounded Result Surface Writeback Planning (#168)

## 1. Purpose

This document defines #168 Bounded Result Surface Writeback Planning.

The purpose is to define how a future Result Surface writeback path should be bounded, reviewed, and approved after the successful authenticated live fetch to Result Surface readback path.

This is a docs-only planning document.

This document does not implement GitHub writeback.

This document does not implement Result Packet write.

This document does not write GitHub comments.

This document does not update GitHub issue bodies.

This document does not execute Codex-side actions.

This document does not create or expand runner, dispatcher, watcher, or automation behavior.

## 2. Issue Classification

```yaml
issue_number: 168
issue_role: support
risk_lane: fast
alignment: core_support
value_target: define a bounded Result Surface writeback planning boundary after the successful authenticated live fetch to Result Surface readback path, without implementing GitHub writeback, Result Packet write, runner, dispatcher, watcher, or automation
```

## 3. Direction Lock

The current proven direction remains:

```text
ChatGPT
-> explicit auditable Task Surface reference
-> local authenticated read-only fetch
-> validation dry-run
-> Result Surface stdout/readback
-> ChatGPT review
-> user approval decision
```

Manual copy/paste remains fallback only, not the target workflow.

#168 does not change the project direction from readback-first evidence to automatic writeback.

## 4. Current Proven Path

#166 proved the authenticated live fetch to Result Surface readback path.

#167 recorded that success as a Phase 3 decision note.

The currently proven path is:

```text
ChatGPT
-> explicit auditable Task Surface reference
-> local authenticated read-only fetch
-> validation dry-run
-> Result Surface stdout/readback
-> ChatGPT review
-> user approval decision
```

The proven path shows that authenticated read-only fetch can reach validation dry-run and produce a Result Surface for ChatGPT readback.

It does not prove GitHub writeback.

It does not prove Result Packet write.

It does not prove Codex-side action execution.

It does not prove runner, dispatcher, watcher, or automation behavior.

## 5. Why Writeback Requires a New Boundary

Result Surface stdout/readback is review evidence.

GitHub writeback would be an external side effect.

Result Packet write would also be a side effect because it persists structured result evidence into a target surface.

External side effects require a stricter boundary than local readback.

GitHub writeback must not be implemented until there is a bounded plan.

Result Packet write must not be implemented until there is a bounded plan.

A future writeback path must prevent broad issue scanning, next/latest issue inference, approval chaining, silent token exposure, and automatic follow-up actions.

## 6. Result Surface vs Result Packet vs GitHub Writeback

A local Result Surface stdout artifact is a structured review artifact emitted locally.

A local Result Surface file is a structured review artifact written to one local review file target.

A Result Packet is a formal structured result record. It is not the same as a local Result Surface and must not be written without a separate bounded plan.

GitHub comment writeback is an external write to GitHub. It is not the same as stdout readback, local file readback, or a Result Packet.

The distinctions are:

- `local_result_surface_stdout`: local review output only; no external write.
- `local_result_surface_file`: one local review file target only; no external write.
- `result_packet`: formal structured result record; side effect when written.
- `github_comment_writeback`: external GitHub comment write; side effect.

GitHub writeback requires Strict Lane.

Result Packet write requires Strict Lane.

## 7. Proposed Future Writeback Scope

A future writeback target should be bounded to one approved result surface destination only, such as:

- one explicit GitHub issue comment target, or
- one local review file target

Future writeback must require exactly one explicit target.

Future writeback must not infer the next issue.

Future writeback must not fetch the latest issue.

Future writeback must not scan open issues.

Future writeback must not write to multiple destinations.

Future writeback must not close issues, change labels, create PRs, merge, commit, push, or trigger Codex-side action execution.

## 8. Minimum Writeback Preconditions

A future writeback task must define and satisfy these preconditions before any write:

- exactly one explicit target
- no broad issue scan
- no next/latest issue inference
- ChatGPT readback before write
- explicit user approval before write
- safe content preview before write
- token value never printed or written
- no automatic issue close
- no automatic label change
- no PR creation
- no merge
- no approval chaining
- no automatic commit
- no automatic push

If any precondition is missing or ambiguous, the future writeback task must fail closed.

## 9. Required Human Approval Gate

Writeback must require explicit user approval through ChatGPT before the write occurs.

Approval must be scoped to the exact write target and content preview.

Approval must expire after use.

Approval must not chain into commit, push, PR creation, merge, issue close, label change, Result Packet write, runner invocation, dispatcher invocation, watcher behavior, or Codex-side action execution.

A successful Result Surface readback is evidence only.

Evidence is not approval.

## 10. Required ChatGPT Readback Gate

ChatGPT must read back the proposed Result Surface writeback content before any user approval decision.

The readback must show:

- the exact target
- the exact content or safe preview
- the source task reference
- the validation result
- the safety flags
- whether the write is GitHub writeback, local file writeback, or Result Packet write
- which behaviors remain forbidden

The user approval decision must happen after ChatGPT readback, not before.

## 11. Failure and Rollback Boundaries

The future writeback path must fail closed when:

- the target is missing
- the target is ambiguous
- more than one target is provided
- the content preview is missing
- ChatGPT readback has not happened
- explicit user approval is missing
- approval scope does not match the target and content
- the token value would be printed or written
- broad issue scanning would be needed
- next/latest issue inference would be needed
- Result Packet write is attempted without Strict Lane approval
- GitHub writeback is attempted without Strict Lane approval

Rollback must not be automatic.

Rollback for an external write is itself an external side effect and requires a separate explicit approval boundary.

## 12. Still Forbidden Behaviors

The following behaviors remain forbidden:

```text
GitHub writeback implementation
Result Packet write implementation
Codex-side action execution
runner behavior
dispatcher behavior
watcher behavior
broad issue scan
next/latest issue inference
autonomous execution
automatic commit
automatic push
PR creation
merge
issue close
label change
approval chaining
```

#168 does not implement any of these behaviors.

## 13. Next Candidate Step

The next candidate issue should be:

```text
#169 Bounded Writeback Target Contract Plan
```

#169 should still be docs-only or planning unless explicitly approved otherwise.

#169 should define the exact contract for a future writeback target, including required fields, approval gates, forbidden actions, and audit shape.

#169 must not implement GitHub writeback yet.

#169 must not implement Result Packet write yet.

## 14. Final Boundary Statement

#168 defines a bounded planning boundary only.

It preserves the proven Phase 3 path from explicit Task Surface reference to authenticated read-only fetch, validation dry-run, Result Surface stdout/readback, ChatGPT review, and user approval decision.

It does not implement GitHub writeback, Result Packet write, Codex-side action execution, runner behavior, dispatcher behavior, watcher behavior, broad issue scanning, next/latest issue inference, autonomous execution, PR creation, merge, issue close, label change, or approval chaining.

Future writeback requires a separate bounded plan, ChatGPT readback, explicit user approval, safe content preview, and exactly one approved target.

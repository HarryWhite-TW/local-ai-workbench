# Bounded Result Surface Planning (#158)

## 1. Purpose

This document defines the bounded Result Surface concept after Phase 3 controlled fetch validation success.

It explains why the project should move from Task Surface validation success into local-only Result Surface planning, without implementing GitHub writeback, Result Packet write, runner behavior, dispatcher behavior, watcher behavior, or automation.

## 2. Issue Classification

```yaml
issue_number: 158
issue_role: support
risk_lane: fast
alignment: core_support
value_target: define the bounded Result Surface concept and next implementation boundary after Phase 3 controlled fetch validation success, without implementing writeback, Result Packet write, runner, dispatcher, or automation
```

## 3. Direction Lock

The long-term target remains:

```text
ChatGPT
-> explicit auditable Task Surface
-> local read-only fetch
-> validation dry-run
-> bounded Codex-side work
-> bounded Result Surface
-> ChatGPT readback and review
-> user approval decisions through ChatGPT
```

Manual copy/paste remains fallback only, not the final target workflow.

## 4. Why Result Surface Is Needed

#156 proved controlled valid Task Surface live fetch and validation success.

#157 recorded that success as a Phase 3 decision note.

The next design question is how Codex should report bounded results in a form that ChatGPT can read, review, and use for user approval decisions.

The project should not jump directly from task validation success to GitHub writeback. A future writeback path needs a bounded result shape first, with clear safety flags and review semantics.

## 5. Task Surface vs Result Surface

A Task Surface is the inbound task/request side.

It answers:

- What was requested?
- What explicit reference was used?
- What is allowed?
- What is forbidden?
- What validation gates must pass before work proceeds?

A Result Surface is the outbound result/evidence side.

It answers:

- What happened?
- What changed?
- What did not happen?
- What checks ran?
- What safety flags were observed?
- What is the next recommended step?
- Does any follow-up require user approval?

## 6. What #156 / #157 Proved

#156 and #157 proved:

- explicit single GitHub issue reference can be fetched
- authenticated live read-only fetch works
- stdout JSON evidence can be produced
- validation dry-run can be reached
- a controlled valid Task Surface can pass validation after live fetch
- no broad scan is needed
- no writeback is needed for this proof

## 7. What #156 / #157 Did Not Prove

#156 and #157 did not prove:

- GitHub writeback
- Result Packet write
- Codex-side action execution
- runner behavior
- dispatcher behavior
- watcher behavior
- approval handling
- PR / merge / issue close / label change

Those behaviors remain outside the current boundary.

## 8. Bounded Result Surface Definition

A bounded Result Surface is a structured, reviewable result/evidence record produced after a validated Task Surface.

It should be designed so ChatGPT can review the result before any user approval decision. It should be local-only and readback-oriented until a separate approved task defines writeback behavior.

A bounded Result Surface must not automatically authorize:

- commit
- push
- GitHub writeback
- Result Packet write
- Codex-side action execution
- runner
- dispatcher
- watcher
- issue close
- label change
- PR / merge

## 9. Minimum Result Surface Fields

The minimum future Result Surface should include fields such as:

- `result_id`
- `source_task_reference`
- `task_surface_validation_result`
- `operation_mode`
- `summary`
- `files_changed`
- `tests_run`
- `safety_flags`
- `blocked_reasons`
- `requires_user_approval`
- `next_recommended_step`

Safety flags should include explicit booleans such as:

- `github_write_performed=false`
- `result_packet_written=false`
- `codex_side_action_executed=false`
- `runner_invoked=false`
- `dispatcher_invoked=false`
- `broad_scan_performed=false`

## 10. Safety Requirements

A bounded Result Surface should:

- be deterministic enough for ChatGPT review
- separate evidence from authorization
- report what happened and what did not happen
- include explicit no-write and no-action flags
- include blocked reasons when work does not proceed
- avoid secrets and token values
- avoid broad scan summaries unless a future task explicitly authorizes a scan
- avoid implying commit, push, writeback, PR, merge, issue close, or label change approval

## 11. Review and Approval Boundary

A bounded Result Surface should be reviewable by ChatGPT before any user approval decision.

The Result Surface should not itself consume approval. It should support review by making the result, safety flags, changed files, tests, blockers, and recommended next step visible.

User approval decisions should remain separate and explicit through ChatGPT.

## 12. Forbidden Behaviors

Still forbidden in this planning step:

- GitHub writeback
- Result Packet write
- Codex-side action execution
- runner
- dispatcher
- watcher
- broad issue scan
- autonomous execution
- commit
- push
- PR / merge
- issue close
- label change

## 13. Next Candidate Step

The next candidate issue should be:

```text
#159 Local Result Surface Draft and Readback Plan
```

#159 should define or produce a local-only sample Result Surface, preferably as docs/sample text or stdout-only evidence.

#159 must not write to GitHub.

#159 must not implement Result Packet writeback.

#159 must not implement runner or dispatcher behavior.

The next step should be local-only and readback-oriented.

## 14. Final Boundary Statement

This planning document defines a bounded Result Surface concept only.

It does not implement code, modify tests, run live GitHub fetch, write GitHub comments, update GitHub issue bodies, close issues, change labels, create PRs, merge, write Result Packets, implement GitHub writeback, execute Codex-side actions, create runner behavior, create dispatcher behavior, create watcher behavior, enable broad scans, enable autonomous execution, add dependencies, or authorize high-risk operations.

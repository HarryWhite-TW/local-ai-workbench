# Local Runner Bridge v0 Architecture

## Purpose

This document defines the architecture for Local Runner Bridge v0.

Local Runner Bridge v0 is the next phase after Semi-automated Workflow v1 proof report.

The purpose is to reduce manual copy and paste between ChatGPT, GitHub, Codex, and the local machine.

The bridge automates task handoff.

The bridge does not automate high-risk approval.

This document is an architecture document only.

This document does not authorize implementation.

This document does not authorize automatic commit.

This document does not authorize automatic push.

This document does not authorize automatic issue close.

This document does not authorize automatic PR creation.

This document does not authorize automatic merge.

This document does not authorize background watcher behavior.

This document does not authorize always-on polling.

This document does not authorize Lv5 full automation.

## Direction Lock Binding

This architecture must be read together with `docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md`.

The direction lock is the source of truth for bridge direction.

Manual copy/paste is not the target workflow.

The user-only-interfaces-with-ChatGPT goal remains active.

ChatGPT-to-Codex dispatch and Codex-to-ChatGPT result readback remain the strategic target.

Any manual foreground runner start described in this document is a transitional safety constraint and bridge gap, not the target end state.

## Strategic context

Semi-automated Workflow v1 has validated the governance layer.

The validated governance layer includes:

* ChatGPT-centered planning and review
* GitHub as task and audit surface
* Codex or local tools as bounded execution layers
* user-retained high-risk approval
* phase separation for ReviewBundle, commit, push, and final audit
* fallback-assisted review when GitHub comment readback is unstable

The next bottleneck is manual task handoff.

The current manual handoff looks like:

```text
ChatGPT prepares a long prompt
-> user copies prompt to Codex
-> Codex executes locally
-> user reports completion or pastes short result
-> ChatGPT reviews
```

The transitional Local Runner Bridge v0 handoff is:

```text
ChatGPT creates or references a GitHub task packet
-> user may manually start foreground relay / runner while direct bridge trigger is unavailable
-> local runner reads one explicit task packet
-> local runner validates schema and policy
-> local runner performs one bounded action
-> local runner writes one result packet
-> ChatGPT reviews GitHub-visible result
-> user approves only high-risk phases
```

This manual foreground start is transitional.

It is a current safety and capability constraint.

It must not be presented as the target end state.

The target remains ChatGPT-centered dispatch and Codex-to-ChatGPT result readback through an auditable bridge.

## Non-goals

Local Runner Bridge v0 is not a full autonomous agent.

Local Runner Bridge v0 is not Lv5 automation.

Local Runner Bridge v0 is not an always-on background worker.

Local Runner Bridge v0 is not a broad GitHub issue scanner.

Local Runner Bridge v0 is not a replacement for ChatGPT review.

Local Runner Bridge v0 is not a replacement for user approval.

Local Runner Bridge v0 must not create automatic commits.

Local Runner Bridge v0 must not push automatically.

Local Runner Bridge v0 must not close issues automatically.

Local Runner Bridge v0 must not create PRs automatically.

Local Runner Bridge v0 must not merge PRs automatically.

Local Runner Bridge v0 must not expand runtime, runner, dispatcher, or automation authority without separate approval.

## Core architecture

Local Runner Bridge v0 has five primary participants:

1. User
2. ChatGPT
3. GitHub
4. Local runner
5. Local repository

Codex may still be used as a bounded execution assistant, but the bridge architecture must not depend on unrestricted Codex behavior.

The core transitional v0 flow is:

```text
User
-> ChatGPT
-> GitHub task packet
-> foreground relay / runner start, manual only while required by current safety constraints
-> schema validation
-> policy validation
-> bounded local action
-> GitHub result packet
-> ChatGPT review
-> user approval for high-risk phases
```

## Responsibility boundaries

## User responsibility

The user is the final approval authority for high-risk phases.

The user may temporarily start the foreground relay / runner while direct bridge trigger is unavailable.

This is a transitional bridge gap, not the target end state.

The user must explicitly approve:

* local commit
* push
* issue close
* PR creation
* merge
* label changes
* approval-consuming actions
* future automation authority expansion

The user should not need to manually copy long prompts after the bridge MVP is available.

The user should also not need to manually copy long Codex results back into ChatGPT after result readback is available.

The user should primarily make direction decisions and high-risk approval decisions through ChatGPT.

The user may still provide short fallback reports when GitHub writeback or connector readback is unavailable.

## ChatGPT responsibility

ChatGPT is the planning and review layer.

ChatGPT prepares or reviews task packets.

ChatGPT reviews result packets.

ChatGPT decides whether a result is acceptable.

ChatGPT prepares high-risk approval packages before any high-risk action.

ChatGPT must not treat marker evidence as authority by itself.

ChatGPT must prefer remote file readback when file content matters.

ChatGPT must prefer remote commit or branch readback when remote state matters.

ChatGPT must not assume that task packet existence equals user approval.

## GitHub responsibility

GitHub is the task and audit surface.

GitHub may store:

* roadmap anchor issue
* task packet
* result packet
* audit marker
* commit history
* remote file content

GitHub is not the authority to approve high-risk actions by itself.

A GitHub comment can carry evidence.

A GitHub comment cannot replace explicit user approval.

When marker evidence and remote file content disagree, remote file readback wins.

## Local runner responsibility

The local runner is a bounded executor.

The local runner must read exactly one explicit task packet per run.

The local runner must validate the task packet schema.

The local runner must validate policy before doing anything.

The local runner must fail closed when required fields are missing or inconsistent.

The local runner must check repository identity, branch, and expected HEAD before action.

The local runner must perform only allowlisted actions.

The local runner must produce a structured result packet.

The local runner must stop after one task.

The local runner must not run as a background watcher in v0.

The local runner must not scan broad issue ranges in v0.

The local runner must not consume high-risk approval unless the action type explicitly requires it and the task packet contains the approved phase.

## Local repository responsibility

The local repository is the execution state.

The local repository must be checked before any write action.

The local repository must match the expected branch.

The local repository must match the expected HEAD.

The local repository must have no unexpected dirty files.

The local repository must not allow write actions outside allowed files.

The local repository state must be included in the result packet.

## Architecture principles

## Manual trigger only

Local Runner Bridge v0 may require foreground manual start in the current transitional safety slice.

When direct bridge trigger is unavailable, the user may run one explicit command or start one explicit local action.

This is transitional and must remain visible as a bridge gap.

No background watcher is allowed in v0.

No always-on polling is allowed in v0.

No scheduled execution is allowed in v0.

Manual start is not the target workflow.

Manual start must not be confused with manual copy/paste relay.

The target direction remains ChatGPT dispatching task packets and reading result packets through the bridge.

## Single-task execution

Each runner invocation handles one task packet.

The runner must stop after the task is completed or fails.

The runner must not continue to the next issue.

The runner must not batch multiple issues.

The runner must not infer additional work.

## Fail-closed behavior

The runner must fail closed when:

* task packet is missing
* task packet has invalid schema
* action type is not allowlisted
* risk level is missing
* allowed files are missing for write actions
* forbidden operations are missing
* repository identity does not match
* branch does not match
* HEAD does not match
* working tree has unexpected dirty files
* staged changes are present unexpectedly
* approval is required but not present
* GitHub writeback fails and no local fallback is available

Fail-closed means:

* do not modify files
* do not stage
* do not commit
* do not push
* do not close issue
* write or print a failure result packet when possible

## Allowlist-first execution

The runner may only execute known action types.

Unknown action types must fail.

Natural language inside the task packet must not create new authority.

The runner should treat task packet fields as structured data, not as free-form instructions.

## Evidence-first review

Every runner result must include evidence.

Evidence may include:

* repository path
* branch
* HEAD
* origin/master
* changed files
* staged changes
* git diff summary
* commit hash
* pushed commit hash
* GitHub comment URL
* failure reason

Evidence should be short and structured.

Long logs should only be used for diagnosis.

## Action categories

## Read-only audit

Read-only audit is the safest initial action category.

Allowed behavior:

* read task packet
* validate schema
* validate repo identity
* validate branch
* validate HEAD
* run git status
* generate result packet

Forbidden behavior:

* modify files
* stage
* commit
* push
* close issue
* create PR
* merge

## Docs-only apply candidate

Docs-only apply candidate is the first useful MVP after read-only mode.

Allowed behavior:

* read BEGIN_DOCUMENT content from a valid task packet
* write exactly one allowed docs file
* run diff check
* write result packet

Forbidden behavior:

* stage
* commit
* push
* close issue
* create PR
* merge
* modify files outside allowed files

## Commit rail

Commit rail is future work after the docs-only MVP is stable.

Commit rail must require explicit user approval for the commit phase.

Allowed behavior when approved:

* verify expected HEAD
* verify allowed files
* stage exact files only
* create exactly one local commit
* write LOCAL-COMMIT-AUDIT result

Forbidden behavior:

* push
* close issue
* create PR
* merge
* stage unrelated files
* amend existing commits

## Push rail

Push rail is future work after commit rail is stable.

Push rail must require explicit user approval for the push phase.

Allowed behavior when approved:

* verify local HEAD
* verify origin/master
* verify local branch is ahead by expected commit count
* push only the approved commit
* write PUSH-AUDIT result

Forbidden behavior:

* create new commit
* modify files
* close issue
* create PR
* merge

## Final audit rail

Final audit rail may assist with read-only verification.

Allowed behavior:

* verify HEAD equals origin/master
* verify remote file content when needed
* verify issue state when needed
* verify no PR, merge, close, or label change occurred
* write FINAL-AUDIT result

Forbidden behavior:

* modify files
* commit
* push
* close issue
* label issue
* merge PR

## Task Packet relationship

#125 should define Local Runner Task Packet v1.

This architecture expects the task packet to include at least:

* protocol
* task_id
* logical_issue
* phase
* action_type
* risk_level
* repository
* branch
* expected_head
* allowed_files
* forbidden_operations
* approval_required
* approval_phrase when needed
* stop_condition
* document payload when needed
* result_target

The runner must reject task packets with missing required fields.

The runner must reject task packets with conflicting fields.

The runner must reject task packets that request non-allowlisted actions.

## Task Packet v1.1 Discipline Fields

Task Packet v1.1 should make the Codex task discipline in `AGENTS.md` available as verifiable task packet fields.

This is a validation and readback discipline update only.

Task Packet v1.1 does not add runner, dispatcher, watcher, background automation, commit, push, GitHub writeback, PR creation, merge, issue close, or label change authority.

Task Packet v1 compatibility should be preserved unless a later task explicitly approves a breaking migration.

The minimal new fields are:

* `task_mode` limits whether the task is plan-only, patch-only, verify-only, or docs-only.
* `objective` keeps the task to one explicit goal.
* `max_allowed_files` keeps the task small and reviewable.
* `context_scope` prevents broad repository exploration.
* `repair_attempt_limit` prevents endless self-repair loops.
* `verification_command_policy` explains whether verification is explicit, not required, or forbidden for the task mode.
* `verification_commands` records the exact commands allowed or expected.
* `scope_expansion_allowed` must default to false.

The next small follow-up tasks should be validator structural support, focused validator tests, and README alignment.

## Result Packet relationship

#126 should define Local Runner Result Packet v1.

This architecture expects the result packet to include at least:

* protocol
* task_id
* logical_issue
* phase
* action_type
* result
* repository
* branch
* head
* origin_master
* changed_files
* staged_changes_present
* commit_created
* push_performed
* pr_created
* merge_performed
* issue_closed
* label_changed
* evidence
* failure_reason
* next_recommended_action

The result packet should be readable by ChatGPT without long transcripts.

## Policy Engine relationship

#127 should define Local Runner Policy Engine v0.

The policy engine should evaluate:

* action allowlist
* risk level
* required approval
* repository identity
* branch guard
* HEAD guard
* file scope guard
* forbidden operations
* dirty working tree guard
* staged changes guard
* evidence requirements
* fail-closed conditions

The policy engine must run before any write action.

The policy engine must reject ambiguous tasks.

## MVP implementation path

The recommended implementation path is:

1. #124 architecture
2. #125 task packet schema
3. #126 result packet schema
4. #127 policy engine design
5. #128 read-only runner MVP
6. #129 GitHub result writeback MVP
7. #130 docs-only apply candidate MVP
8. pause and measure copy-paste reduction
9. only then consider commit rail
10. only then consider push rail
11. only then consider final audit rail

The first meaningful success criterion is:

```text
ChatGPT creates a GitHub task packet
-> user may manually start foreground relay / runner while direct bridge trigger is unavailable
-> runner reads the task packet
-> runner applies one docs-only candidate
-> runner writes a GitHub result packet
-> ChatGPT reviews without the user pasting a long prompt or long transcript
```

This success criterion is transitional.

The stronger bridge success criterion is no-copy / no-paste dispatch and result readback, where the user does not manually paste task text into Codex and does not manually paste Codex output back into ChatGPT.

## Security model

Local Runner Bridge v0 uses a restrictive security model.

The default state is deny.

Every allowed action must be explicit.

Every write target must be explicit.

Every high-risk phase must be separately approved.

Every result must be auditable.

No single task packet should authorize a chain of high-risk operations.

Approval chaining remains forbidden.

Commit approval does not approve push.

Push approval does not approve issue close.

## Error handling model

The runner should produce a failure result when it cannot safely continue.

Failure results should include:

* failure_reason
* failed_check
* current_branch when available
* current_head when available
* expected_head when available
* changed_files when available
* staged_changes_present when available
* whether any write happened

The runner should avoid partial writes.

If partial writes occur, the result packet must say so clearly.

The runner must not hide partial failure.

## GitHub writeback model

GitHub writeback is useful but must not be treated as perfect.

If GitHub writeback succeeds, the runner should report:

* comment URL
* comment ID
* marker first line

If GitHub writeback fails, the runner should print a local fallback result packet.

ChatGPT may use fallback-assisted review when connector comment readback is unstable.

Fallback-assisted review must be labeled as such.

## Future Lv5 expansion compatibility

Local Runner Bridge v0 should preserve future upgrade paths.

The architecture should reserve room for:

* approval ledger
* policy profiles
* evidence store
* task queue
* queue manager
* human approval inbox
* multi-issue scheduler
* multi-repo support
* background watcher adapter
* automatic low-risk execution
* rollback planner
* execution sandbox
* audit dashboard

These are future-facing extension points.

They are not authorized in v0.

Any Lv5 or beyond capability requires separate design, review, and explicit approval.

## Explicitly not authorized

This document does not authorize:

* background watcher
* always-on polling
* broad issue scanning
* multi-issue scheduling
* automatic low-risk execution
* automatic commit
* automatic push
* automatic issue close
* automatic PR creation
* automatic merge
* automatic label changes
* automatic approval consumption
* unrestricted Codex execution
* runner authority expansion
* dispatcher authority expansion
* runtime authority expansion
* automation authority expansion
* Lv5 full automation

## Completion criteria

#124 is complete when this architecture document exists and clearly defines:

* strategic context
* non-goals
* core architecture
* responsibility boundaries
* manual trigger only rule
* single-task execution rule
* fail-closed behavior
* allowlist-first execution
* action categories
* task packet relationship
* result packet relationship
* policy engine relationship
* MVP path
* security model
* error handling model
* GitHub writeback model
* future Lv5 expansion compatibility
* explicitly not authorized capabilities

#124 is not complete if it creates runner code.

#124 is not complete if it expands automation authority.

#124 is not complete if it authorizes background watcher behavior.

#124 is not complete if it authorizes automatic high-risk actions.

## Current status

Local Runner Bridge v0 architecture is defined as a bounded transitional task handoff bridge aligned with the Direction Lock.

Manual foreground start may remain a current safety constraint, but it is not the target end state.

The next recommended step after #124 is #125 Local Runner Task Packet v1.

The bridge should reduce copy-paste overhead while preserving ChatGPT review and user-controlled high-risk approval.


# GitHub-visible Markers and Readback Policy

## Purpose

This document defines how GitHub-visible markers and ChatGPT readback should work in the ChatGPT-centered semi-automated workflow.

The goal is to reduce reliance on long pasted Codex output while preserving auditability, user control, and safety gates.

This document does not expand automation authority.

This document does not authorize automatic commit.

This document does not authorize automatic push.

This document does not authorize automatic issue close.

This document does not authorize full autonomous agent behavior.

## Relationship to roadmap

#114 is the roadmap anchor for Semi-automated workflow v1.

#117 defines risk levels and approval gates.

#118 defines GitHub-visible markers and readback policy.

This document should be read together with the risk level and approval gate rules.

## Core principle

A result is more useful when ChatGPT can read it from a shared auditable surface.

GitHub issues, issue comments, commits, files, branches, and pull requests can serve as ChatGPT-readable surfaces when explicitly scoped.

A marker is not authority by itself.

A marker is evidence for review.

The user keeps final approval authority for high-risk actions.

## Marker purpose

Markers are short structured comments written to a GitHub issue.

Markers exist to let ChatGPT review task results without requiring the user to paste long runner or Codex output.

Markers should be:

* short
* structured
* scoped
* searchable
* phase-specific
* auditable
* non-ambiguous

Markers should not hide important failures.

Markers should not claim success unless the required state was actually verified.

## Marker location

The default marker location for the Semi-automated workflow v1 roadmap is GitHub issue #114.

A task may use another issue only when ChatGPT explicitly scopes that issue as the target.

A marker should include:

* issue_source
* logical_issue
* result
* phase
* working_mode
* changed files or affected state
* forbidden operations confirmation
* next recommended action

## Marker identity fields

Every marker should include enough identity fields for readback.

Recommended fields include:

* protocol
* issue_source
* logical_issue
* result
* phase
* working_mode
* repository
* branch
* base head or commit
* changed files
* changed files count
* next recommended action

For high-risk phases, the marker should also include relevant safety confirmations.

## Marker result values

Allowed result values are:

* success
* failure
* skipped
* stopped

A success marker means the scoped audit passed.

A failure marker means the scoped audit failed.

A skipped marker means the task was intentionally not run.

A stopped marker means execution was halted for safety.

A success marker must not be used when required checks were skipped.

## Marker protocols

Common marker protocols include:

* REVIEWBUNDLE-AUDIT-VISIBLE
* LOCAL-COMMIT-AUDIT-VISIBLE
* PUSH-AUDIT-VISIBLE
* FINAL-AUDIT-VISIBLE
* PUSH-READBACK-DIAGNOSTIC
* LAWBRUNNER-RESULT
* CHATGPT-DISPATCH

Each protocol should correspond to one phase or evidence type.

A marker protocol should not be reused for unrelated authority.

## ReviewBundle markers

A ReviewBundle marker records whether a candidate review passed.

A ReviewBundle marker may include:

* changed files
* changed files count
* docs-only status
* git diff check result
* no staged changes
* no commit
* no push
* no PR
* no issue close
* next recommended action

A ReviewBundle success does not approve commit.

## Local commit audit markers

A local commit audit marker records whether a local commit was created correctly.

A local commit audit marker may include:

* commit message
* commit hash when available
* committed files
* committed files count
* working tree clean status
* staged changes status
* no push
* no PR
* no issue close
* next recommended action

A local commit audit success does not approve push.

Because local commits may not be visible remotely before push, local commit audit markers are acceptable evidence but weaker than remote commit readback.

## Push audit markers

A push audit marker records whether a push phase completed.

A push audit marker may include:

* pushed branch
* commit message
* pushed files
* pushed files count
* remote push performed
* new commit created in push phase
* working tree clean status
* staged changes status
* no PR
* no merge
* no issue close
* next recommended action

A push audit success does not approve issue close.

For pushed changes, ChatGPT should prefer direct remote commit or file readback when possible.

## Final audit markers

A final audit marker records whether a completed logical issue was verified after push.

A final audit marker may include:

* commit
* commit message
* remote file
* head equals origin/master
* working tree clean
* staged changes absent
* PR status
* merge status
* issue close status
* runtime behavior status
* runner behavior status
* dispatcher behavior status
* automation authority status
* next recommended action

A final audit success does not approve the next roadmap task by itself.

## Diagnostic markers

Diagnostic markers record troubleshooting results.

They should be used when readback fails, marker search is inconsistent, or local and remote evidence disagree.

Diagnostic markers should include:

* what was checked
* what was found
* what failed
* whether retry occurred
* whether files were modified
* whether commit or push occurred
* whether PR or issue close occurred
* exact failure reason
* next recommended action

Diagnostic markers should not silently retry high-risk operations.

## Readback strength

Readback strength should be classified.

Strong readback means ChatGPT directly verified the actual remote state.

Examples:

* remote file fetched from GitHub
* remote commit fetched from GitHub
* branch comparison verified remotely
* PR state fetched directly
* issue state fetched directly

Acceptable readback means ChatGPT found enough GitHub-visible marker evidence to continue a bounded workflow.

Examples:

* ReviewBundle marker found
* local commit audit marker found
* push audit marker found plus later remote file check pending

Weak readback means evidence is incomplete or indirect.

Examples:

* user says Codex completed but marker is missing
* marker exists but lacks required fields
* search result is ambiguous
* local-only state cannot be directly verified

Failed readback means the expected evidence cannot be found or contradicts other evidence.

## Marker-only evidence

Marker-only evidence is useful but limited.

It is acceptable for:

* candidate review
* local-only audit before push
* diagnostic reporting
* low-risk or medium-risk workflow continuation

It is not enough for:

* proving pushed file content
* proving remote branch state
* proving remote master state
* proving issue close state
* proving PR merge state
* expanding automation authority

When direct remote readback is possible, direct remote readback should be preferred.

## Remote readback

Remote readback should verify the actual state on GitHub.

Remote readback may include:

* fetching a file from master
* fetching a commit by SHA
* comparing two commits
* searching for a pushed commit
* checking branch state
* checking PR state
* checking issue state

For pushed docs changes, ChatGPT should verify that the file exists remotely and that the commit message matches the expected logical issue.

## Readback conflict rule

If marker evidence and remote readback disagree, remote readback wins.

If a marker says push succeeded but the remote branch or file cannot be found, the push is not accepted as complete.

If a marker says a file changed but remote commit shows a different file list, the marker is not enough.

If a marker says no issue close occurred but the issue is closed, the actual issue state wins.

Conflict requires diagnostic audit or stop.

## Search limitations

GitHub search may be delayed or incomplete.

A marker may exist before it is searchable.

A search result may match roadmap text rather than the actual marker.

A search result may be insufficient when the exact marker body is not visible.

When search is insufficient, ChatGPT should use issue comment fetch, remote commit readback, file fetch, or fallback user-provided short audit output.

## Fallback paste rule

The preferred path is GitHub-visible readback.

However, fallback paste is allowed when:

* marker search fails
* connector readback is delayed
* GitHub result is truncated
* remote state is unavailable
* local-only state must be reviewed before push

Fallback paste should be short and structured.

The user should paste only the required audit block, not the entire long Codex transcript.

## Required marker repair

Marker repair is allowed when the task state is already established and only the GitHub-visible marker is missing or malformed.

Marker repair must be read-only with respect to repo files.

Marker repair must not modify files.

Marker repair must not stage.

Marker repair must not commit.

Marker repair must not push.

Marker repair must not create PRs.

Marker repair must not close issues.

## No approval chaining

A marker does not grant approval for the next high-risk phase.

Examples:

* ReviewBundle success does not approve commit
* local commit audit success does not approve push
* push audit success does not approve issue close
* final audit success does not approve the next roadmap task
* diagnostic success does not approve recovery

Each high-risk phase still requires explicit user approval.

## Security and authority boundaries

Markers must not be used to expand authority silently.

A marker must not authorize:

* automatic commit
* automatic push
* automatic issue close
* automatic PR creation
* automatic merge
* broad issue scanning
* background watcher
* always-on polling
* unrestricted Codex execution
* full autonomous agent behavior
* Lv5 full automation

Authority expansion requires a separate design, risk package, review, and explicit user approval.

## Stop conditions

The workflow must stop when:

* expected marker is absent
* marker result is failure
* marker fields are missing
* marker is written to the wrong issue
* marker identity fields are wrong
* remote readback contradicts marker
* search result is ambiguous
* local-only evidence is insufficient for a remote claim
* forbidden operation is reported
* high-risk approval is missing
* Codex attempts automatic recovery without approval

Stopping is a successful safety behavior.

## Current status

This document defines GitHub-visible markers and readback policy for Semi-automated workflow v1.

It supports the current ChatGPT-centered Lv4.5-style workflow.

It does not implement new dispatcher behavior.

It does not change runtime behavior.

It does not change runner behavior.

It does not change dispatcher behavior.

It does not expand automation authority.

Future changes to marker protocols, readback authority, or automation scope require separate design, review, and explicit approval.

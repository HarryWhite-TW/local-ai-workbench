# Runner v2A Dry-Run Orchestrator Design

## Purpose

Runner v2 is meant to reduce manual relay in the local GitHub Issue workflow, not to expand automation permissions.

The first v2A step should keep the same safety posture as the current localhost, single-user prototype: detect eligible work, show the planned action, and stop before changing anything.

## Current workflow problem

The current workflow still requires the user to relay several manual steps:

- copying commands
- running PowerShell manually
- reporting status back to ChatGPT
- choosing the next runner phase manually

Runner v2 should reduce that relay burden without taking over approval, commit, push, close, label, PR, or merge decisions.

## v2A design goal

v2A starts as:

```text
local on-demand dry-run detector
```

It should first detect eligible issues and print planned actions without modifying anything.

## v2A initial boundary

The first implementation is an on-demand PowerShell command that runs locally from the repo root:

```powershell
.\scripts\local_runner_v2.ps1 -DryRun
```

This mode must only inspect local repo state and open GitHub Issues. It must not call Codex, run runner v1, modify files, post comments, stage, commit, push, close issues, edit labels, create PRs, merge, or force push.

v2A must start from a clean repo. A dirty repo is a stop condition, not a warning.

## Issue detection protocol

v2A should use a conservative issue body marker first:

```text
Runner marker: runner-v2-reviewbundle-ready
```

The issue body must also include existing write/review capability markers, such as:

```text
write-capable
review-bundle capable
```

v2A should not require labels. Label mutation introduces additional GitHub write operations and is outside the initial boundary.

## Dry-run behavior

The initial dry-run command is:

```powershell
.\scripts\local_runner_v2.ps1 -DryRun
```

Expected dry-run behavior:

- check repo clean
- read open issues
- find issues with the v2 marker
- verify expected capability markers
- print candidate issues
- print planned action
- do not call Codex
- do not run runner v1
- do not modify files
- do not post GitHub comments
- do not stage, commit, push, close, label, create PRs, or merge

The planned action should be descriptive only, for example: "would run runner v1 ReviewBundle for issue #N after dry-run validation."

## Future ReviewBundle behavior

A later implementation may add:

```powershell
.\scripts\local_runner_v2.ps1 -RunOnce
```

`-RunOnce` may run runner v1 `ReviewBundle` only for explicitly marked issues after the same dry-run validation succeeds.

Before broader use, v2A `-RunOnce` should be validated through a dedicated docs-only marker issue that leaves reviewable unstaged changes.

That validation path should stay docs-only until the RunOnce handoff and review bundle output are confirmed.

It must not run `CommitApproved`. It must not push, close issues, edit labels, create PRs, merge, or force push.

## Approval and CommitApproved boundary

For now:

- v2A must not auto-run `CommitApproved`.
- `CommitApproved` remains explicit and manual.
- The user must still enter the exact state-bound ASCII approval token locally.
- ChatGPT approval language by itself is not enough to trigger a commit.
- GitHub approval comments may be considered later, but must not directly trigger commits in v2A.

`CommitApproved` remains a separate local action with its own validation and approval token. It is not part of v2A dry-run orchestration.

## External-agent boundary

External agents are optional workflow executor adapters only.

Allowed future role:

- operate the local shell under runner control
- run approved runner commands
- capture logs
- surface status
- stop on timeout or runner exit

Forbidden role:

- product developer
- project owner
- decision maker
- independent git or GitHub operator

External agents must not independently plan product features, modify product code, stage, commit, push, close issues, edit labels, create PRs, merge, or decide approvals.

## Forbidden operations

v2A must not perform:

- auto-push
- auto-close issue
- auto-label edit
- auto-PR creation
- auto-merge
- force push
- auto-commit from GitHub comment alone
- product-code `CommitApproved` automation
- running when repo is dirty
- external agent making independent repo or GitHub writes

## Failure and stop conditions

v2A must stop on:

- dirty repo
- GitHub unreachable
- duplicate candidate issue
- unexpected modified files
- Codex failure in future ReviewBundle mode
- failed post-comment in future ReviewBundle mode
- stale approval
- external agent timeout or failure
- user abort

When v2A stops, it should print the reason and leave the repo and GitHub state unchanged except for any future ReviewBundle comment explicitly produced by runner v1 in `-RunOnce` mode.

## Initial implementation sequence

Recommended sequence:

1. document v2A boundary
2. implement dry-run detector only
3. validate dry-run against a marker issue
4. then implement `RunOnce` ReviewBundle only
5. validate with docs-only issue
6. only later consider external-agent adapter
7. defer `CommitApproved` automation, push, close, labels, and PR handling

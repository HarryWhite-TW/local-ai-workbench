# Semi-automated Workflow v1 Operating Model

## Purpose

This document defines the operating model for Semi-automated workflow v1.

The goal is to let the user, ChatGPT, Codex App, Codex Web, VS Code + Codex Extension, GitHub, and the local runner cooperate through auditable steps without becoming unrestricted autonomous agent behavior.

This workflow keeps ChatGPT as the primary user interface and decision coordinator. It also keeps the user as the final approval authority for high-risk actions.

## Background

#114 is the roadmap anchor for Semi-automated workflow v1.

#115 clarified the bridge status, Lv4.5 / Lv5 boundary, current schema, future schema, active actions, reserved actions, and risk authority model.

#116 defines the day-to-day operating model for continuing work safely across Away Mode, Away-IDE Working Mode, and Home Mode.

The current target is not full autonomous agent behavior.

The current target is a ChatGPT-centered semi-automated workflow:

1. User
2. ChatGPT
3. GitHub Issue / Comment / Task Packet
4. Codex App / Codex Web / VS Code Codex Extension / local runner
5. GitHub-visible or user-provided result
6. ChatGPT review
7. User approval only for key high-risk decisions

## Core direction

ChatGPT is the primary user interface.

The user should not manually coordinate every tool unless fallback is required.

Codex App is the main Home Mode execution tool.

Codex Web is a Browser-only Away Mode candidate helper, not the primary adoption rail.

VS Code + Codex Extension can be used as an Away-IDE Working Mode candidate environment.

GitHub is the task, audit, and recovery surface.

High-risk operations remain user-approved.

Full autonomous agent behavior is not the target.

## Operating modes

Semi-automated workflow v1 uses three operating modes:

1. Browser-only Away Mode
2. Away-IDE Working Mode
3. Home Mode

These modes do not have the same authority.

Browser-only Away Mode is for planning, drafting, cloud candidate generation, and review preparation.

Away-IDE Working Mode is for using VS Code + Codex Extension on a non-primary but resettable or controlled machine, such as a course computer, to inspect the repo and produce local candidate diffs.

Home Mode is for local verification, official adoption, commit, push, close, and final audit rails.

## Browser-only Away Mode

Browser-only Away Mode is used when the user is on:

- a course computer without local repo access
- a phone
- a borrowed machine
- a browser-only environment
- Codex Web only
- an environment without a trusted local working tree

Typical available tools:

- ChatGPT
- GitHub Web
- Codex Web
- browser
- screenshots or pasted output

Allowed:

- roadmap discussion
- issue drafting
- issue body preparation
- docs-only planning
- Codex Web candidate generation when explicitly approved
- GitHub issue or comment review
- ChatGPT review of GitHub-visible information
- preparation of Home Mode adoption packets
- preparation of risk notes and approval packages

Forbidden by default:

- local runner execution
- PowerShell dispatcher smoke
- pytest
- local commit
- push
- issue close rail
- merge
- production-like validation
- tasks depending on local working tree state

Browser-only Away Mode may produce candidate outputs, but those outputs are not official adoption until reviewed and applied through an approved path.

Codex Web must not be treated as the official PR rail until a dedicated PR policy is designed and approved.

Codex Web must not be assumed to have reliable access to GitHub issue comments.

Required task context should be embedded in the prompt when Codex Web is used.

Codex Web internal commit or PR metadata must not be treated as approved repository change.

For docs-only Codex Web tasks, prefer no-op or minimal setup to avoid unrelated dependency installation failures.

## Away-IDE Working Mode

Away-IDE Working Mode is used when:

- the user is on a course computer or another non-primary machine
- VS Code is available
- Codex Extension is available
- the repo can be cloned or opened temporarily
- the machine may be resettable or controlled by classroom environment
- the local environment may not be identical to Home Mode

Typical available tools:

- ChatGPT
- VS Code
- Codex Extension
- GitHub repo clone
- terminal if available
- browser
- screenshots or pasted output

Allowed:

- read repository files
- inspect project structure
- docs-only candidate edits
- produce local candidate diffs
- run read-only git status or git diff if available
- prepare review material for ChatGPT
- prepare Home Mode adoption packets
- draft issue bodies or documentation candidates

Forbidden by default:

- push
- merge
- GitHub-visible PR creation
- issue close rail
- approval consumption
- remote branch modification
- automatic commit + push chaining
- changing secrets or credentials
- storing long-lived credentials
- treating candidate diffs as adopted work

Local commit in Away-IDE Working Mode is not approved by default.

Local commits may only be considered after a dedicated Away-IDE local commit rail is designed, reviewed, and explicitly approved.

Until then, Away-IDE Working Mode should stop at local candidate diff.

Away-IDE Working Mode is stronger than Browser-only Away Mode for candidate generation because it can inspect files and produce local diffs.

However, it is still not equal to Home Mode.

Away-IDE Working Mode may support project progress during the day, but official adoption, commit, push, issue close, and final audit should remain Home Mode or separately approved rails.

## Home Mode

Home Mode is used when:

- the user is on the primary local development machine
- the local repo is available
- the local working tree can be audited
- the trusted local environment is available

Typical available tools:

- ChatGPT
- Codex App or local Codex
- local repo
- terminal or PowerShell
- Git
- local runner or dispatcher
- pytest when explicitly allowed
- GitHub

Allowed when explicitly scoped:

- local repo state audit
- clean working tree verification
- local candidate apply
- docs-only candidate diff
- runner / dispatcher smoke
- pytest
- ReviewBundle validation
- CommitApproved phase
- PushOnce phase
- CloseIssueOnce phase
- final audit

Home Mode must still preserve separated approval gates.

Commit, push, and issue close must not be chained together.

## Role definitions

### User role

The user is final approval authority for high-risk actions.

The user must explicitly approve:

- commit
- push
- issue close
- PR creation
- merge
- approval consumption
- irreversible or hard-to-revert workflow changes
- changes that expand automation authority

### ChatGPT role

ChatGPT is the main interface and decision coordinator.

ChatGPT responsibilities:

- interpreting user intent
- preserving roadmap
- drafting Codex prompts
- reviewing Codex outputs
- classifying risk
- preparing approval packages
- deciding whether Codex output is adoptable, rejectable, or requires user decision
- keeping Browser-only Away Mode, Away-IDE Working Mode, and Home Mode boundaries clear
- preventing tool-specific incidents from hijacking the main project direction

ChatGPT must clearly distinguish:

- planned
- candidate
- applied
- committed
- pushed
- closed
- merged

### Codex App role

Codex App is the preferred Home Mode execution tool.

Codex App may be used for:

- local file edits
- docs-only candidate apply
- local runner / dispatcher tasks when explicitly scoped
- test execution when explicitly scoped
- local ReviewBundle preparation
- local audit support

Codex App must obey allowed file lists, forbidden operations, and phase-specific safety rails.

### Codex Web role

Codex Web is a Browser-only Away Mode candidate helper.

Codex Web may be used for:

- docs-only candidate generation
- diff exploration
- planning support
- candidate review material

Codex Web must not be treated as the official PR rail until a dedicated PR policy is designed and approved.

Codex Web must not be assumed to have reliable access to GitHub issue comments.

Required task context should be embedded in the prompt when Codex Web is used.

Codex Web internal commit or PR metadata must not be treated as approved repository change.

For docs-only Codex Web tasks, prefer no-op or minimal setup to avoid unrelated dependency installation failures.

### VS Code + Codex Extension role

VS Code + Codex Extension may be used as an Away-IDE Working Mode candidate environment or as a Home Mode helper.

In Away-IDE Working Mode, it may be used for:

- repository inspection
- docs-only candidate edits
- local diff production
- read-only status checks
- preparing review material for ChatGPT

In Away-IDE Working Mode, it must not be used by default for:

- push
- merge
- GitHub-visible PR creation
- issue close
- approval consumption
- remote branch modification
- automatic commit + push chaining

In Home Mode, it may be treated similarly to Codex App only when the user is on the primary local development machine and the task is explicitly scoped.

### GitHub role

GitHub is the task, audit, and recovery surface.

GitHub may store:

- roadmap issues
- task issues
- audit comments
- candidate notes
- ReviewBundle results
- approval markers
- final audit results

GitHub issue or comment writes may be useful, but must not be assumed fully stable until the future GitHub write proof is completed.

### Local runner / dispatcher role

Local runner and dispatcher are Home Mode only unless a future dedicated Away-IDE runner policy is designed and approved.

They may be used for bounded, explicit, issue-scoped tasks.

They must not become:

- background watcher
- always-on polling system
- unrestricted automation
- approval bypass mechanism

## Standard workflow loop

The standard loop is:

1. User gives direction to ChatGPT
2. ChatGPT classifies mode and risk
3. ChatGPT prepares task draft or Codex prompt
4. User approves if the action is medium-risk, high-risk, or GitHub write
5. Codex App / Codex Web / VS Code Codex Extension / GitHub performs the scoped action
6. Result is returned or made visible
7. ChatGPT reviews result
8. ChatGPT reports outcome, risk, adopt / reject / revise recommendation, and next action
9. User approves only when required
10. Next phase begins

## Phase separation rules

The default sequence is:

1. Candidate generation
2. ChatGPT review
3. User approval when required
4. local apply
5. ReviewBundle
6. CommitApproved
7. PushOnce
8. CloseIssueOnce
9. Final audit

The following must not be chained:

- candidate apply + commit
- commit + push
- push + close
- close + final audit
- approval + multiple downstream operations

Each phase must have its own evidence and decision point.

## Risk authority summary

Low-risk examples:

- read-only audit
- issue state check
- git status check
- marker readback
- runner result verification
- final read-only audit

Medium-risk examples:

- docs-only candidate diff
- workflow document update
- Codex Web candidate generation
- Away-IDE local candidate generation
- GitHub issue or comment write

High-risk examples:

- commit
- push
- issue close
- GitHub-visible PR creation
- merge
- approval consumption
- remote branch modification
- automation authority expansion

High-risk actions require a ChatGPT risk package and explicit user approval.

## Non-goals

This document does not authorize:

- full autonomous agent behavior
- Lv5 full automation
- background watcher
- always-on polling
- unrestricted Codex execution
- automatic commit
- automatic push
- automatic issue close
- approval chaining
- broad issue scanning
- Codex Web PR rail adoption
- Away-IDE push / PR / close rail
- user-facing CLI as the main interface

## Current vs future distinction

Current approved direction:

- ChatGPT-centered semi-automated workflow
- bounded Codex execution
- GitHub as audit and recovery surface
- Home Mode for official local adoption and high-risk rails
- user approval retained for high-risk actions

Future-only or reserved direction:

- full autonomous agent behavior
- background watcher
- always-on polling
- broad issue scanning
- Codex Web PR rail
- Away-IDE push / PR / close rail
- Lv5 full automation

Future capabilities require separate design, testing, documentation, and explicit approval.

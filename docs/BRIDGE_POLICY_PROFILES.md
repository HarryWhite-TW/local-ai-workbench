# Bridge Policy Profiles

## Document Identity

title: Bridge Policy Profiles
version: v1
status: Draft candidate for review
scope: Short prompt policy/profile packaging for ChatGPT-to-Codex bridge work.

## Source Of Truth

`docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md` remains the highest source of truth for bridge direction. This document may package repeated rules into shorter prompts, but it must not override the Direction Lock Plan.

Every bridge-related prompt that uses a policy profile must still preserve:

- `manual_copy_paste_is_target=false`
- the goal that the user primarily interfaces with ChatGPT
- the goal that ChatGPT dispatches work through GitHub or another auditable shared surface
- the goal that Codex or a local relay writes results back to a ChatGPT-readable surface
- visible remaining bridge gaps

Workflow simplification is not the target workflow. It is only a support layer that reduces repeated prompt text while keeping the bridge gap explicit.

## Policy Profile: bridge_core_no_mutation.v1

Use `bridge_core_no_mutation.v1` for bridge support or core tasks that may read GitHub, inspect local repo state, generate a reviewed candidate, run bounded read-only relay behavior, or write an approved audit/readback comment.

This profile allows only bounded, auditable actions that are explicitly named by the phase. It does not grant standing permission to modify code, commit, push, close issues, post arbitrary comments, run arbitrary commands, or ask Codex to perform real code modification.

Profile rules:

- Direction Lock must be read before work starts.
- PLAN-READ-AUDIT must be emitted.
- `manual_copy_paste_is_target=false` must remain visible.
- Remaining bridge gaps must remain visible.
- GitHub reads are allowed when scoped to an explicit issue.
- GitHub writes are allowed only when the phase explicitly allows a named marker, packet, result packet, audit comment, or issue body audit.
- Candidate repo file modification is allowed only in `review_bundle` and only within the issue-approved file scope.
- Runtime relay actions must be foreground/manual-start, bounded, and issue-scoped.
- Real Codex code modification is forbidden unless a future explicit issue approves a new profile.
- Arbitrary shell execution is forbidden.
- Arbitrary prompt execution is forbidden.
- Background watchers are forbidden.
- Always-on polling is forbidden.
- Automatic commit, push, or close is forbidden.
- Approval chaining is forbidden.
- Commit, push, and close must remain separate approval phases.

## Global Mandatory Rules

These rules apply to every profile and phase unless the Direction Lock Plan is explicitly updated by the user:

- exact issue number is required
- expected branch is required
- expected HEAD SHA is required
- expected `origin/master` SHA is required
- working tree state must be checked before any write-like action
- staged files must be checked before any write-like action
- exact-one marker rule must be enforced for one-time approval markers
- no arbitrary shell execution
- no arbitrary prompt execution
- no real Codex modification unless a future explicit issue approves it
- no background watcher
- no always-on polling
- no automatic commit, push, or close
- no approval chaining
- commit, push, and close require separate approvals
- Direction Lock must be read and acknowledged with PLAN-READ-AUDIT
- `manual_copy_paste_is_target=false` must be included in auditable outputs
- remaining bridge gaps must be stated when relevant
- any allowed GitHub write must name its exact surface and purpose
- failures must report the exact reason and final safe state

## Phase Names

Short prompts should use one of these phase names.

### review_bundle

Purpose: create a reviewed candidate diff and publish a ReviewBundle audit.

Allowed:

- read repo files
- modify only approved candidate files
- run targeted tests and `git diff --check`
- update the selected issue with a ReviewBundle audit

Forbidden:

- commit
- push
- close issue
- label
- PR
- merge
- runtime GitHub result writeback unless separately approved

Required fields:

- issue number
- policy profile name
- expected branch
- expected HEAD
- expected `origin/master`
- allowed files or allowed file pattern
- validation commands
- expected next action

### runtime_smoke_once

Purpose: run exactly one foreground bounded relay smoke and write exactly one result packet when explicitly approved.

Allowed:

- read exactly one explicit GitHub issue
- create or reuse exactly one valid task packet if the phase allows it
- run exactly one allowlisted bounded relay action
- post exactly one result packet when explicit post is approved
- write one runtime smoke audit

Forbidden:

- repo file modification
- stage
- commit
- push
- close issue
- label
- PR
- merge
- arbitrary shell execution
- arbitrary prompt execution
- real Codex code modification

Required fields:

- issue number
- policy profile name
- expected branch
- expected HEAD
- expected `origin/master`
- task packet id
- action
- command kind
- allowed write surface
- expected next action

### commit_approved

Purpose: create exactly one local commit from an approved ReviewBundle candidate.

Allowed:

- read repo and selected issue state
- run approval state diagnostics
- run targeted validation
- stage only approved files
- create exactly one local commit
- post one local commit audit comment

Forbidden:

- push
- close issue
- label
- PR
- merge
- staging unapproved files
- amending previous commits

Required fields:

- issue number
- policy profile name
- expected branch
- expected HEAD
- expected `origin/master`
- review_id
- diff_fingerprint
- files_fingerprint
- approved files
- expected commit message
- expected next action

### push_once

Purpose: push exactly one approved local commit to `origin/master`.

Allowed:

- read repo and selected issue state
- compute commitfiles fingerprint
- create or reuse one current valid `push-approved-once` marker
- run PushOnce exactly once
- post one push audit comment

Forbidden:

- file modification
- stage
- commit
- amend
- close issue
- label
- PR
- merge
- force push
- approval chaining

Required fields:

- issue number
- policy profile name
- expected branch
- local_head
- expected `origin/master` before push
- pushed_head
- commitfiles fingerprint or instruction to compute it
- marker type: `push-approved-once`
- target issue
- expected next action

### close_issue_once

Purpose: close exactly one approved issue after the pushed commit is verified.

Allowed:

- read repo and selected issue state
- create or reuse one current valid `close-issue-approved-once` marker
- run CloseIssueOnce exactly once for the selected issue
- post one close audit comment

Forbidden:

- file modification
- stage
- commit
- amend
- push
- close any other issue
- label
- PR
- merge
- approval chaining

Required fields:

- issue number
- policy profile name
- expected branch
- expected HEAD
- expected `origin/master`
- pushed_head
- marker type: `close-issue-approved-once`
- target issue
- expected next action

### final_audit

Purpose: perform read-only verification after close and post one final audit comment.

Allowed:

- read repo state
- read selected issue state
- post one final audit comment when explicitly requested

Forbidden:

- file modification
- stage
- commit
- amend
- push
- close issue
- label
- PR
- merge
- runtime smoke
- approval chaining

Required fields:

- issue number
- policy profile name
- expected branch
- expected HEAD
- expected `origin/master`
- expected issue state
- expected state reason
- required audit markers
- expected next action

### packet_create_once

Purpose: create exactly one task packet on an explicit GitHub issue when no valid current packet exists.

Allowed:

- read selected issue body and comments
- post exactly one task packet comment only when no current valid packet exists

Forbidden:

- duplicate packet creation
- result packet posting
- runtime execution
- repo file modification

### marker_create_once

Purpose: create exactly one one-time approval marker when no current valid matching marker exists.

Allowed:

- read selected issue comments
- post exactly one marker comment with short expiry

Forbidden:

- duplicate marker creation
- running the approved action before exact-one validation

### audit_visible_comment

Purpose: post a standalone visible audit comment for a completed phase.

Allowed:

- post one explicitly named audit comment

Forbidden:

- hiding failed state
- editing unrelated issue content
- using the audit as approval for a different phase

### approval_state_diagnostic

Purpose: compute current review id, diff fingerprint, files fingerprint, modified files, and token preview without changing state.

Allowed:

- read repo state
- run the runner diagnostic mode

Forbidden:

- file modification
- stage
- commit
- push
- close issue

## Short Prompt Required Fields

Every short prompt must include:

- issue number
- phase name
- policy profile name
- expected branch
- expected HEAD
- expected `origin/master`
- allowed write surface
- expected next action

Commit phases must also include:

- review_id
- diff_fingerprint
- files_fingerprint
- approved files
- expected commit message

Push and close phases must also include:

- local_head or pushed_head
- commitfiles fingerprint when pushing
- marker type
- target issue

Runtime smoke phases must also include:

- task packet id
- action
- command kind
- explicit post permission status
- expected result packet surface

Final audit phases must also include:

- expected issue state
- expected state reason
- required prior audit markers

## Short Prompt Example: PushOnce

```text
phase=push_once
policy_profile=bridge_core_no_mutation.v1
issue=111
branch=master
local_head=d617168ad8927ae04cfc09697e915209a5634124
origin_master_before_push=75db39d60f4d72a2b8274dd0549f2b87f3c3c182
commitfiles=655e7f4ce4e74ac5ec110e5d3ee440b63af717b035a952a6d8f8e1f6a4e37efe
marker_type=push-approved-once
allowed_write_surface=one_push_marker_if_missing,one_push_audit_comment
expected_next_action=close_issue_once
```

This short prompt still requires Direction Lock readback, exact HEAD checks, clean git status, exact-one marker validation, PushOnce only, no force push, no issue close, no label, no PR, no merge, and no approval chaining.

## Short Prompt Example: Runtime Smoke Once

```text
phase=runtime_smoke_once
policy_profile=bridge_core_no_mutation.v1
issue=111
branch=master
head=75db39d60f4d72a2b8274dd0549f2b87f3c3c182
origin_master=75db39d60f4d72a2b8274dd0549f2b87f3c3c182
task_packet_id=bridge-codex-capability-probe-111-task-001
action=bounded-codex-capability-probe
command_kind=codex-side-capability-probe
allowed_write_surface=one_task_packet_if_missing,one_result_packet_comment,one_runtime_audit
expected_next_action=local_commit
```

This short prompt still requires exact-one task packet validation, explicit result posting permission, no repo file change beyond an already approved candidate, no stage, no commit, no push, no close, no arbitrary shell execution, no arbitrary prompt execution, no real Codex modification, no watcher, no polling, and no approval chaining.

## Short Prompt Example: CloseIssueOnce

```text
phase=close_issue_once
policy_profile=bridge_core_no_mutation.v1
issue=111
target_issue=111
branch=master
head=d617168ad8927ae04cfc09697e915209a5634124
origin_master=d617168ad8927ae04cfc09697e915209a5634124
pushed_head=d617168ad8927ae04cfc09697e915209a5634124
marker_type=close-issue-approved-once
allowed_write_surface=one_close_marker_if_missing,one_close_audit_comment
expected_next_action=final_audit
```

This short prompt still requires exact selected issue matching, exact-one close marker validation, CloseIssueOnce only, no file change, no stage, no commit, no push, no label, no PR, no merge, and no approval chaining.

## What Simplification Must Not Hide

Short prompts must not hide that the direct bridge is still incomplete where the user still manually starts a foreground relay or manually approves a rail through ChatGPT. That manual action is fallback only.

Short prompts must not hide:

- whether ChatGPT wrote the task packet itself or the packet was manually relayed
- whether the local relay was manually started
- whether result readback happened through GitHub
- whether a phase only produced documentation or a smoke result
- whether real Codex-side task execution is still missing

## Non-Weakening Statement

This document changes no runtime behavior and no runner behavior. It packages repeated workflow rules into named policy and phase vocabulary. Existing safety rails are not weakened.

## Lv4.5 Action State and Fail-Closed Rule

Current active safe dispatch action for Lv4.5 is:

- `maybe-status-check`

Reserved / future dispatch action names are:

- `run-reviewbundle`
- `run-reviewbundle-handoff`
- `read-final-audit`

Reserved actions must fail closed until they are explicitly implemented, tested, documented, and approved.

## Risk-Based Authority Model (Current Guardrail)

Low-risk examples:

- read-only audit
- issue state check
- git status check
- marker readback
- runner result verification
- final read-only audit

Medium-risk examples:

- docs-only ReviewBundle
- candidate diff
- low-risk queue review
- workflow document update

High-risk examples:

- local commit
- push
- issue close
- label changes
- PR creation
- merge
- approval consumption

High-risk actions require a ChatGPT risk package and explicit user approval before the next phase. Commit, push, and close remain separate approval phases, with no approval chaining.

# High-risk Approval Package Standard

## Purpose

This document defines the required approval package before any high-risk action in the semi-automated workflow.

The goal is to make commit, push, issue close, PR creation, merge, label change, and future approval-consuming actions explicit, reviewable, and separately approved.

This document does not authorize automatic commit.

This document does not authorize automatic push.

This document does not authorize automatic issue close.

This document does not authorize automatic PR creation.

This document does not authorize automatic merge.

This document does not authorize approval chaining.

This document does not authorize full autonomous agent behavior.

## Relationship to roadmap

#114 is the roadmap anchor for Semi-automated workflow v1.

#117 defines risk levels and approval gates.

#118 defines GitHub-visible markers and readback policy.

#119 defines Away-to-Home adoption packets.

#120 defines GitHub readback proof and fallback rules.

#121 verifies a low-risk closed-loop smoke path.

#122 defines the standard approval package for high-risk actions.

This document should be read together with the risk level, approval gate, and GitHub readback policies.

## High-risk actions

The following actions are high risk by default:

* local commit
* push
* issue close
* label change
* PR creation
* merge
* approval consumption
* destructive local Git operation
* branch rewrite
* future automation authority expansion

High-risk actions must remain separate phases.

Commit approval does not approve push.

Push approval does not approve issue close.

ReviewBundle success does not approve commit.

Final audit success does not approve the next roadmap task by itself.

## Approval package requirement

Before any high-risk action, ChatGPT must provide a high-risk approval package.

The user must explicitly approve the exact next high-risk action.

Approval must be scoped to one phase only.

Approval must not be inferred from prior approval.

Approval must not be chained.

Approval must not be reused for a different phase.

Approval must not be broadened by Codex, runner, dispatcher, or ChatGPT.

## Required approval package fields

A high-risk approval package must include:

* logical issue number
* current phase
* action being requested
* target repository
* target branch
* expected base commit
* expected head or expected parent commit
* allowed file or allowed files
* forbidden files or forbidden paths
* expected commit message when applicable
* expected pushed file when applicable
* change summary
* expected result
* risk level
* possible risks
* validation evidence
* rollback or recovery note
* forbidden operations
* next command or next action
* explicit stop condition
* recommended decision

The package should be written so the user can approve or reject without guessing.

## Change summary

The change summary should explain what will change and why.

It should be short, concrete, and scoped.

It should mention whether the action is docs-only, test-only, runtime-affecting, workflow-affecting, or authority-affecting.

It should not hide risk behind vague language.

## Expected result

The expected result should state the exact success condition.

Examples:

* exactly one local commit is created
* exactly one commit is pushed to origin/master
* exactly one GitHub issue comment is posted
* exactly one issue is closed
* exactly one document is changed
* no repo file is changed

The expected result should be specific enough for post-action audit.

## Risk level

The risk level must be stated explicitly.

Valid default risk labels are:

* low
* medium
* high

If an action can modify repository history, remote state, issue state, labels, PRs, or automation authority, it should be treated as high risk unless explicitly justified otherwise.

## Possible risks

The approval package must identify possible risks.

Examples:

* wrong file committed
* dirty workspace included accidentally
* push updates remote state incorrectly
* issue closed before final audit
* approval reused across phases
* marker says success but remote readback fails
* automation authority expanded unintentionally
* runtime behavior changed unexpectedly
* runner or dispatcher behavior changed unexpectedly

Risks should be practical and tied to the requested action.

## Validation evidence

The approval package must state what evidence supports moving to the high-risk phase.

Examples:

* ReviewBundle marker
* local commit audit marker
* push audit marker
* final audit marker
* remote commit readback
* remote file readback
* clean working tree check
* git diff check
* no staged changes check

Marker evidence is not enough when file content matters.

Remote readback wins when marker evidence and remote file content disagree.

## Rollback or recovery note

The approval package must include a rollback or recovery note.

For local commit, recovery may include stopping before push.

For push, recovery may require a separate revert plan.

For issue close, recovery may include reopening the issue.

For label change, recovery may include restoring the previous label state.

For PR or merge actions, recovery must be treated as higher risk and may require a separate plan.

The recovery note should not pretend that every action is easily reversible.

## Forbidden operations

Every high-risk approval package must list forbidden operations.

Common forbidden operations include:

* modifying unapproved files
* staging unapproved files
* creating extra commits
* pushing without separate approval
* pulling
* merging
* rebasing
* amending
* resetting
* restoring
* cleaning
* creating PRs
* merging PRs
* closing issues
* changing labels
* changing assignees
* running runner or dispatcher outside scope
* processing unrelated logical issues
* batch adoption

Forbidden operations should be explicit rather than implied.

## Stop condition

The approval package must include a stop condition.

Codex or runner must stop if:

* repository identity does not match
* current branch does not match
* HEAD does not match expected value
* origin/master does not match expected value
* working tree is not in the expected state
* staged changes are present unexpectedly
* changed files exceed scope
* diff check fails
* expected marker is missing
* expected file content is missing
* any forbidden operation would be required

Stopping is preferred over guessing.

## User approval language

The user approval should name the exact phase.

Examples:

* approve #122 commit
* approve #122 push
* approve #122 issue close
* approve #122 label change

Generic approval such as "go ahead" should not be treated as approval for multiple high-risk phases.

If approval is ambiguous, ChatGPT should clarify before providing a high-risk execution prompt.

## No approval chaining

Approval chaining is forbidden.

A single approval cannot authorize commit and push together.

A single approval cannot authorize push and issue close together.

A single approval cannot authorize PR creation and merge together.

A single approval cannot authorize current work and future roadmap work together.

Each high-risk action requires a separate approval package and separate user approval.

## GitHub marker requirement

After any high-risk action, the executor should write a GitHub-visible marker when scoped to do so.

Expected marker families include:

* LOCAL-COMMIT-AUDIT-VISIBLE
* PUSH-AUDIT-VISIBLE
* FINAL-AUDIT-VISIBLE

Markers support ChatGPT review.

Markers do not replace remote readback when content or remote state matters.

## Current status

This document defines the high-risk approval package standard for Semi-automated workflow v1.

It supports the current ChatGPT-centered Lv4.5-style workflow.

It does not implement new dispatcher behavior.

It does not change runtime behavior.

It does not change runner behavior.

It does not change dispatcher behavior.

It does not expand automation authority.

Future changes to approval authority, automation scope, or background execution require separate design, review, and explicit approval.

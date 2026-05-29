
# Risk Levels and Approval Gates

## Purpose

This document defines the risk levels and approval gates for the ChatGPT-centered semi-automated workflow.

The goal is to make project execution safer, more auditable, and easier to operate across Browser-only Away Mode, Away-IDE Working Mode, and Home Mode.

This document does not expand automation authority.

This document does not authorize automatic commit.

This document does not authorize automatic push.

This document does not authorize automatic issue close.

This document does not authorize full autonomous agent behavior.

## Relationship to roadmap

#114 is the roadmap anchor for Semi-automated workflow v1.

#115 clarified the current bridge status, Lv4.5 / Lv5 boundary, active actions, reserved actions, and safety authority.

#116 defined the semi-automated workflow v1 operating model.

#117 defines risk levels and approval gates.

This document should be read together with the existing bridge policy and operating SOP documents.

## Core principle

Risk is determined by the effect of an action, not by the tool that performs it.

A low-risk action can become higher risk if it changes repository state, remote state, issue state, automation authority, runtime behavior, or user-visible project history.

A high-risk action remains high risk even if Codex, ChatGPT, GitHub, or a local runner can technically perform it.

The user keeps final approval authority for high-risk actions.

## Risk level summary

The workflow uses four practical risk levels:

* read-only risk
* low risk
* medium risk
* high risk

Read-only risk means the task only inspects existing state.

Low risk means the task may write a bounded marker or produce planning output, but does not change repository files or project authority.

Medium risk means the task may create a local candidate diff or documentation candidate, but does not stage, commit, push, close, merge, or expand authority.

High risk means the task changes project history, remote state, issue state, approval state, automation authority, or executable behavior.

## Read-only risk

Read-only risk actions include:

* inspecting issue state
* reading GitHub comments
* searching GitHub-visible markers
* checking repository metadata
* checking current branch
* checking HEAD
* checking origin/master
* checking git status
* checking diff output
* checking commit history
* checking whether a marker exists
* checking whether a remote file exists

Read-only actions must not modify files, branches, issues, labels, PRs, commits, or remote state.

Read-only actions usually do not require explicit user approval, but should still be scoped.

## Low risk

Low-risk actions include:

* writing a short GitHub-visible marker when explicitly scoped
* creating a planning comment
* preparing a Codex prompt
* preparing a Home Mode adoption prompt
* summarizing known repo state
* classifying a task
* recommending adopt, reject, revise, or stop
* recording a non-mutating audit result

Low-risk actions must remain bounded.

Low-risk actions must not create repository file changes.

Low-risk actions must not consume approval for downstream phases.

## Medium risk

Medium-risk actions include:

* creating a docs-only local candidate file
* editing one scoped documentation file as a candidate
* producing a ReviewBundle candidate
* writing a GitHub ReviewBundle marker
* creating an Away-IDE local candidate diff
* preparing adoption packets
* preparing proof documents
* preparing failure records

Medium-risk actions may create local file diffs when explicitly scoped.

Medium-risk actions must not stage.

Medium-risk actions must not commit.

Medium-risk actions must not push.

Medium-risk actions must not create PRs.

Medium-risk actions must not close issues.

Medium-risk actions must not expand automation authority.

## High risk

High-risk actions include:

* staging files
* local commit
* push
* force push
* branch creation when used for project execution
* remote branch modification
* PR creation
* PR merge
* issue close
* issue reopen
* label change when used as workflow state
* assignee change when used as workflow state
* approval consumption
* runner behavior change
* dispatcher behavior change
* script change that affects command execution
* test change that affects safety gates
* automation authority expansion
* any operation that can make an incorrect state visible as official project history

High-risk actions require a ChatGPT approval package and explicit user approval.

High-risk actions must remain separate phases.

## Forbidden by default

The following are forbidden by default unless a scoped phase explicitly allows them:

* automatic commit
* automatic push
* automatic issue close
* automatic PR creation
* automatic merge
* approval chaining
* broad issue scanning
* background watcher
* always-on polling
* unrestricted Codex execution
* executing reserved actions
* modifying runner or dispatcher behavior without a dedicated issue
* expanding automation authority without a dedicated design
* treating candidate completion as official adoption
* treating marker success as push approval
* treating ambiguous user replies as high-risk approval

## Approval gate model

The workflow uses explicit approval gates.

A gate is a boundary where ChatGPT must stop and ask the user before continuing into a higher-risk phase.

The main gates are:

* ReviewBundle gate
* Home Mode adoption gate
* CommitApproved gate
* PushOnce gate
* CloseIssueOnce gate
* PR creation gate
* Merge gate
* Policy expansion gate
* Automation authority expansion gate

Each gate must be scoped to one phase.

Each gate must have a clear expected result.

Each gate must have forbidden operations.

Each gate must produce evidence before the next gate is requested.

## ReviewBundle gate

The ReviewBundle gate checks whether a candidate can be accepted, rejected, or revised.

Allowed:

* inspect candidate evidence
* inspect changed files
* inspect diff stat
* inspect marker fields
* inspect safety claims
* classify risk
* recommend next action
* write a ReviewBundle visible marker when scoped

Forbidden:

* stage
* commit
* push
* close issue
* create PR
* merge
* expand authority
* approve downstream phases automatically

A ReviewBundle success does not approve commit.

## Home Mode adoption gate

The Home Mode adoption gate applies an accepted candidate into the primary local repo.

Allowed when scoped:

* create or update one approved docs file
* perform read-only diff audit
* write ReviewBundle marker
* stop for ChatGPT review

Forbidden:

* stage
* commit
* push
* close issue
* create PR
* merge
* batch adoption unless explicitly approved
* continuing into commit without separate approval

Home Mode adoption is not the same as commit approval.

## CommitApproved gate

The CommitApproved gate allows exactly one local commit for an approved scope.

Allowed when explicitly approved:

* stage only the approved file or files
* create exactly one local commit
* write local commit audit marker when scoped

Forbidden:

* push
* PR creation
* merge
* issue close
* label change unless scoped
* staging unrelated files
* amend unless scoped
* reset or restore unless scoped
* approval chaining

Commit approval does not approve push.

## PushOnce gate

The PushOnce gate allows exactly one approved local commit to be pushed to the expected remote branch.

Allowed when explicitly approved:

* push exactly the approved commit to the expected branch
* write push audit marker when scoped

Forbidden:

* new commit
* file modification
* stage
* amend
* pull
* merge
* rebase
* force push
* PR creation
* issue close
* label change unless scoped
* approval chaining

Push approval does not approve issue close.

## CloseIssueOnce gate

The CloseIssueOnce gate allows exactly one explicitly scoped issue to be closed.

Allowed when explicitly approved:

* close the scoped issue
* write close audit marker when scoped

Forbidden:

* commit
* push
* PR creation
* merge
* closing unrelated issues
* label change unless scoped
* editing unrelated issue content
* approval chaining

Issue close approval does not approve final audit or next roadmap work.

## PR and merge gates

PR creation and merge are separate high-risk gates.

PR creation approval allows only creating one scoped PR.

PR creation approval does not approve merge.

Merge approval allows only merging one scoped PR using the approved method.

Merge approval does not approve issue close unless separately approved.

PR and merge gates are not default rails for the current workflow.

## Policy expansion gate

Policy expansion includes changes that give ChatGPT, Codex, runner, dispatcher, or another tool more authority.

Policy expansion requires a dedicated design, risk package, and explicit approval.

Policy expansion must not be hidden inside a docs-only candidate.

Policy expansion must not be inferred from successful proof markers.

Policy expansion must not be activated by default.

## Approval phrase rule

High-risk approval must be explicit.

Good approval examples:

* approve #117 commit
* approve #117 push
* approve #117 close issue
* approve #118 Home Mode adoption
* approve this PR creation
* approve this policy expansion

Ambiguous replies are not enough for high-risk approval.

Ambiguous examples:

* ok
* continue
* go
* do it
* next
* looks good
* sure
* yes
* proceed

If the user gives an ambiguous reply before a high-risk action, ChatGPT must clarify.

## No approval chaining

One approval authorizes only one phase.

Approving a candidate does not approve Home Mode adoption.

Approving Home Mode adoption does not approve commit.

Approving commit does not approve push.

Approving push does not approve issue close.

Approving issue close does not approve final audit.

Approving final audit does not approve the next roadmap task.

Approving a plan does not approve implementation.

## Mode restrictions

Browser-only Away Mode is for planning, issue drafting, GitHub review, and GitHub-visible readback.

Away-IDE Working Mode is for scoped local candidate diffs, docs-only candidates, ReviewBundle markers, and adoption preparation.

Home Mode is preferred for official adoption, commit, push, close, runner execution, dispatcher execution, and final audit rails.

After #124, Away-IDE Working Mode must not be treated as authorized for Git write rails by default.

## Evidence requirements

Each phase should produce evidence appropriate to its risk.

Examples of acceptable evidence:

* changed files list
* changed files count
* docs-only confirmation
* git diff check result
* no staged changes confirmation
* no commit confirmation
* no push confirmation
* no PR confirmation
* no issue close confirmation
* ReviewBundle marker
* local commit audit marker
* push audit marker
* remote branch readback
* remote commit readback
* remote file readback
* final audit marker

Marker-only evidence is weaker than direct remote file or commit readback.

For pushed changes, direct remote readback is preferred.

## Stop conditions

The workflow must stop when:

* changed files are unexpected
* staged changes already exist unexpectedly
* working tree is dirty unexpectedly
* branch is wrong
* HEAD is wrong
* origin/master is wrong
* marker is missing
* marker result is failure
* remote readback contradicts marker
* candidate contamination is detected
* Codex workspace does not match the expected task
* high-risk approval phrase is ambiguous
* a forbidden operation occurs
* a tool attempts automatic recovery without approval

Stopping is a successful safety behavior.

## Recovery rules

Recovery must be explicit.

Codex must not automatically recover by:

* push retry
* reset
* restore
* clean
* branch recreation
* force push
* merge
* rebase
* creating a replacement commit
* closing or reopening issues

Recovery requires ChatGPT review and explicit user approval when it touches high-risk state.

## Current authority

Current authority remains ChatGPT-centered and user-approved.

ChatGPT may prepare scoped prompts and review GitHub-visible results.

Codex may execute bounded tasks when explicitly scoped.

The user keeps final authority for high-risk actions.

No tool receives open-ended authority.

No background automation is authorized.

No Lv5 full automation is authorized.

## Non-goals

This document does not authorize:

* automatic commit
* automatic push
* automatic issue close
* automatic PR creation
* automatic merge
* approval chaining
* broad issue scanning
* background watcher
* always-on polling
* unrestricted Codex execution
* full autonomous agent behavior
* Lv5 full automation
* expanding Away-IDE Git write authority
* changing runner behavior
* changing dispatcher behavior
* changing runtime behavior

## Current status

This document defines the risk levels and approval gates for Semi-automated workflow v1.

It supports the current ChatGPT-centered Lv4.5-style workflow.

It does not implement new dispatcher behavior.

It does not change runtime behavior.

It does not change runner behavior.

It does not change dispatcher behavior.

It does not expand automation authority.

Future changes to risk levels or approval authority require separate design, review, and explicit approval.

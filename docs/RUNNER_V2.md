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

Initial `ApprovalOnce` validation is limited to `action=run-reviewbundle`; additional approval actions require separate design and validation.

`ApprovalNextOnce` validates that exactly one current approval exists across bounded open issues before delegating once to runner v1 `ReviewBundle`; it does not commit, push, close issues, or run `CommitApproved`.

`ApprovalNextWatch` is a bounded foreground convenience mode that polls for one valid `run-reviewbundle` approval, delegates once to runner v1 `ReviewBundle`, and exits.

## No-agent LV4 operating boundary

`ApprovalNextWatch` is the current no-agent LV4 foreground execution rail for the review-bundle handoff.

After user review, ChatGPT can post a structured GitHub issue comment with:

```text
RUNNER-V2-APPROVE action=run-reviewbundle
```

The user can then run one fixed command without specifying the issue number:

```powershell
.\scripts\local_runner_v2.ps1 -ApprovalNextWatch -TimeoutSeconds 300 -PollSeconds 15
```

Runner v2 must find exactly one current approval, validate that the approved action is `run-reviewbundle`, and delegate only to runner v1 `ReviewBundle`.

Runner v2 does not run `CommitApproved`, stage, commit, push, close issues, edit labels, create PRs, merge, force push, install dependencies, change `PATH`, change Windows settings, invoke external agents, run a daemon, run a scheduler, or chain approvals.

After `ReviewBundle`, ChatGPT or human review is still required before any commit or push. This completes the current no-agent LV4 review-bundle handoff target, but not higher-risk commit or push automation.

## ApprovalNextOnce rail SOP

Use `ApprovalNextOnce` only when a bounded open issue already has the required runner markers and the intended next action is exactly:

```text
action=run-reviewbundle
```

Expected flow:

- runner v2 scans bounded open issues
- validates that exactly one current approval exists
- confirms that the approved action is `run-reviewbundle`
- delegates once to runner v1 `ReviewBundle`
- leaves reviewable local changes unstaged for human inspection

Safety boundaries:

- no commit, push, close, label edit, PR creation, merge, or force push
- no automatic `CommitApproved`
- no original source document modification
- stop if the repo is dirty, approval is missing or stale, multiple approvals exist, or the action is not supported

Current limitation: `ApprovalNextOnce` supports only `action=run-reviewbundle`. Any other approval action requires separate design and validation before use.

## Approved docs-only local commit rail

The approved commit rail is higher risk than the ReviewBundle handoff because it can create one local Git commit. It is still narrow:

- docs-only markdown files only, currently `docs/*.md`
- local commit only
- no push
- no issue close
- no label edit
- no PR creation
- no merge or force push
- no Codex or external-agent execution
- no daemon, scheduler, background service, or approval chaining

Use the dry run first:

```powershell
.\scripts\local_runner_v2.ps1 -ApprovalNextCommitDryRun
```

Final validation should confirm `ApprovalNextCommitOnce` creates a local docs-only commit only after a matching dry run.

After review, use the execution mode only when exactly one current approval exists:

```powershell
.\scripts\local_runner_v2.ps1 -ApprovalNextCommitOnce
```

The approval comment format is:

```text
RUNNER-V2-APPROVE protocol=v2.approval.1 action=commit-approved-docs-only issue=<N> repo=HarryWhite-TW/local-ai-workbench branch=<branch> head=<sha> review=<review-id> diff=<diff-sha256> files=<files-sha256> filelist=<sha256-or-none> expires=<UTC_BASIC>
```

Required fields are `protocol`, `action`, `issue`, `repo`, `branch`, `head`, `review`, `diff`, `files`, and `expires`. `filelist` may be present, but it is not the primary security field. The `files` fingerprint remains required.

Approval token means a structured ASCII line that binds approval to one exact local state. Approval token（核准權杖）不是密碼，而是一次性的狀態確認字串。

Diff fingerprint means the SHA-256 fingerprint of the approved diff payload, including tracked diff and untracked file hashes. Diff fingerprint（差異指紋）用來確認目前差異內容沒有被替換。

Files fingerprint means the SHA-256 fingerprint of the approved file status payload. Files fingerprint（檔案清單指紋）用來確認目前被修改的檔案狀態仍是被審核的狀態。

`ApprovalNextCommitDryRun` scans bounded open issues and requires exactly one current valid `action=commit-approved-docs-only` approval. It rejects stale approvals, multiple approvals, unsupported actions, repo mismatch, branch mismatch, HEAD mismatch, issue mismatch, review id mismatch, diff fingerprint mismatch, files fingerprint mismatch, non-docs paths, and preexisting staged files. It prints the planned commit action and does not stage, commit, push, or post comments.

`ApprovalNextCommitOnce` performs the same validation, then delegates to runner v1 `CommitApproved` with the exact state-bound token. Runner v1 stages only the approved files, creates exactly one local commit, and posts the commit result, commit SHA, final git status, and next step to the GitHub Issue.

Human / ChatGPT review is still required before posting the commit approval comment. This rail exists only after a ReviewBundle has already been reviewed and approved. Push remains a later separate rail and is not performed here.

## PushDryRun rail

`PushDryRun` is a read-only push validation rail. It validates one current `action=push-dryrun-approved` marker, reports the planned push target, and stops before any remote write.

Use:

```powershell
.\scripts\local_runner_v2.ps1 -PushDryRun
```

The approval comment format is:

```text
RUNNER-V2-APPROVE protocol=v2.approval.1 action=push-dryrun-approved issue=<N> repo=HarryWhite-TW/local-ai-workbench branch=<branch> localhead=<local-head-sha> remote=<remote-name> upstream=<remote-tracking-branch> remotehead=<remote-branch-head-sha> commit=<approved-commit-sha> ahead=1 commitfiles=<sha256> expires=<UTC_BASIC>
```

`PushDryRun` requires a clean working tree, no staged files, the current branch and local HEAD to match the marker, the approved commit to equal local HEAD, exactly one local commit ahead, no behind count, the remote name and upstream to match, the remote URL to point to `HarryWhite-TW/local-ai-workbench`, and the committed file-list fingerprint to match.

The remote branch HEAD check uses a read-only query:

```powershell
git ls-remote origin refs/heads/master
```

`PushDryRun` does not run `git fetch` by default. If the read-only remote HEAD does not match `remotehead`, it stops.

The committed file-list fingerprint is the SHA-256 of the normalized committed file list from:

```powershell
git show --name-only --format= <approved-commit-sha>
```

The normalized list uses forward slashes, removes blank lines, sorts unique paths, and joins them with LF. For the no-agent local commit rail SOP commit, the normalized file list is:

```text
docs/NO_AGENT_LOCAL_COMMIT_RAIL_SOP.md
```

Safety boundaries:

- PushDryRun only
- one commit only
- no PushOnce
- no `git push`
- no issue close
- no label edit
- no PR creation
- no merge or force push
- no approval chaining
- no reuse of commit approval markers as push approval markers

## External-agent boundary

External agents are optional workflow executor adapters only.

For the separate validated no-agent report workflow, see [LOCAL_OPERATOR.md](LOCAL_OPERATOR.md).

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

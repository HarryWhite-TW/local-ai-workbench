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

## Runner result summary v1

Runner result comments and practical runner action output include a machine-readable summary block for ChatGPT or tooling.

The block starts with this exact marker line, followed immediately by a parseable JSON object. Consumers should not need to parse Markdown fences to recover the JSON.

```text
LAWBRUNNER-RESULT protocol=lawb.runner_result.v1
```

The JSON schema is stable for `lawb.runner_result.v1`:

```json
{
  "schema": "lawb.runner_result.v1",
  "repo": "HarryWhite-TW/local-ai-workbench",
  "issue": 81,
  "action": "run-reviewbundle",
  "result": "success",
  "branch": "master",
  "head": "<sha>",
  "selected_issue": 81,
  "review_id": "<review-id-or-null>",
  "diff_fingerprint": "<diff-fingerprint-or-null>",
  "files_fingerprint": "<files-fingerprint-or-null>",
  "changed_files": [],
  "validations": {
    "git_status_clean": {
      "status": "passed",
      "summary": "Final git status is clean."
    }
  },
  "safety": {
    "no_stage": true,
    "no_commit": true,
    "no_push": true,
    "no_issue_close": true,
    "no_label": true,
    "no_pr": true,
    "no_merge": true,
    "no_approval_chaining": true
  },
  "next_recommended_action": "chatgpt_review"
}
```

Required top-level fields are `schema`, `repo`, `issue`, `action`, `result`, `branch`, `head`, `selected_issue`, `review_id`, `diff_fingerprint`, `files_fingerprint`, `changed_files`, `validations`, `safety`, and `next_recommended_action`.

`schema` must be exactly `lawb.runner_result.v1`. `changed_files` is always an array. Each `validations` entry is an object with `status` and `summary`; allowed statuses are `passed`, `failed`, `not_run`, `warning`, and `reported`. Use `reported` when the runner is relaying a result from human-readable output instead of independently verifying it. Safety flags are booleans.

Current emitted actions include `run-reviewbundle`, `commit-approved-dryrun`, `commit-approved-once`, `push-dryrun`, `push-once`, and `close-issue-once`. The summary preserves existing human-readable output and does not change approval marker semantics.

## CHATGPT-DISPATCH marker spec v1

`CHATGPT-DISPATCH` is a request marker that ChatGPT may post for a future local dispatcher to consume. It asks a local runner to perform one narrow runner action, but it does not authorize approval-gated work.

This section is design/spec-only. It does not implement a dispatcher, background watcher, Codex auto-run, automatic commit, automatic push, issue close, approval chaining, or any change to existing `PushOnce` or `CloseIssueOnce` approval semantics.

The v1 marker is a single ASCII line:

```text
CHATGPT-DISPATCH protocol=lawb.dispatch.v1 action=<action> issue=<N> repo=HarryWhite-TW/local-ai-workbench branch=<branch> head=<sha> expires=<UTC_BASIC> requested_by=<actor> request_id=<id>
```

Required fields:

- `protocol`: must be exactly `lawb.dispatch.v1`.
- `action`: must be one of the supported v1 action names.
- `issue`: the explicit GitHub issue number in decimal form.
- `repo`: the explicit owner/name repo, currently `HarryWhite-TW/local-ai-workbench`.
- `branch`: the explicit branch name the request is bound to.
- `head`: the exact local Git `HEAD` SHA the request is bound to.
- `expires`: UTC basic timestamp in `yyyyMMddTHHmmssZ` form.
- `requested_by`: the GitHub or ChatGPT-visible actor that requested the dispatch.
- `request_id`: a caller-generated unique id for deduplication and audit correlation.

Optional fields:

- `mode`: a future dispatcher mode hint, such as `review-bundle-only`.
- `expected_state`: a concise expected state hint, such as `clean`.
- `reason`: a short human-readable reason. Consumers must treat it as descriptive only.

Supported v1 actions:

- `run-reviewbundle`: request one review-bundle generation for the explicit issue.
- `read-final-audit`: request a read-only final audit/report for the explicit issue.
- `maybe-status-check`: request a read-only status check to decide whether action is needed.

`CHATGPT-DISPATCH` v1 does not support `commit`, `push`, `close`, `commit-approved-once`, `push-approved-once`, `close-issue-approved-once`, or any action that directly or indirectly stages files, creates commits, pushes refs, closes issues, edits labels, creates PRs, merges, or force pushes. Commit, `PushOnce`, and `CloseIssueOnce` remain separate user-approved workflows.

Required safety behavior for any future consumer:

- scan only the selected explicit issue by default; do not broadly scan open issues unless a later spec explicitly adds that mode
- require explicit `issue`, `repo`, `branch`, `head`, and `expires`
- require the marker issue scope to match the issue being processed
- require local repo, branch, and current `HEAD` to match the marker
- require the marker to be unexpired at validation and immediately before execution
- fail closed on malformed markers, unknown fields, missing fields, duplicate fields, unsupported actions, repo mismatch, branch mismatch, issue mismatch, `HEAD` mismatch, expired markers, or read failures
- fail closed if more than one current `CHATGPT-DISPATCH protocol=lawb.dispatch.v1` marker exists for the same issue
- never choose between duplicate current markers, even if their fields are otherwise valid
- never reinterpret `CHATGPT-DISPATCH` as an approval marker
- never chain from a dispatch marker into an approval-gated action
- leave all approval-gated actions blocked until a separate valid `RUNNER-V2-APPROVE` marker or local user approval flow is supplied under that action's own rules

Duplicate handling is intentionally strict. A current marker means a syntactically valid, unexpired `CHATGPT-DISPATCH protocol=lawb.dispatch.v1` line on the selected issue. If zero current markers exist, the dispatcher must do nothing. If exactly one current marker exists, it may continue validation. If two or more current markers exist, including markers with different `request_id` values, it must stop without running any action.

Expired markers are non-current for action selection, but malformed or duplicate current markers are stop conditions. A consumer should report the stop reason in human-readable output and, when it posts machine-readable output, use `LAWBRUNNER-RESULT protocol=lawb.runner_result.v1`.

Relationship to existing markers:

- `CHATGPT-DISPATCH` requests a runner action.
- `RUNNER-V2-APPROVE` authorizes an approval-gated runner action under its own state-bound approval rules.
- `LRV1-APPROVE` authorizes runner v1 local commit mode under its own prompt/token rules.
- `LAWBRUNNER-RESULT` reports machine-readable runner results.

Expected future workflow:

```text
User asks ChatGPT to dispatch #N.
ChatGPT posts one CHATGPT-DISPATCH protocol=lawb.dispatch.v1 marker on issue #N.
Future local dispatcher validates the marker against issue, repo, branch, HEAD, and expiry.
Future local dispatcher runs only the supported requested action.
Runner posts LAWBRUNNER-RESULT protocol=lawb.runner_result.v1.
ChatGPT reads the result and reviews.
```

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

## PushOnce rail

`PushOnce` is the write-capable counterpart of `PushDryRun`. It validates one current `action=push-approved-once` marker, re-runs the same push safety checks immediately before the push, executes exactly one narrow non-force push, and reports the pushed commit plus the remote result.

Use:

```powershell
.\scripts\local_runner_v2.ps1 -PushOnce
```

The approval comment format is:

```text
RUNNER-V2-APPROVE protocol=v2.approval.1 action=push-approved-once issue=<N> repo=HarryWhite-TW/local-ai-workbench branch=<branch> localhead=<local-head-sha> remote=<remote-name> upstream=<remote-tracking-branch> remotehead=<remote-branch-head-sha> commit=<approved-commit-sha> ahead=1 commitfiles=<sha256> expires=<UTC_BASIC>
```

`PushOnce` requires the same state-bound validations as `PushDryRun`: clean working tree, no staged files, marker branch and local HEAD match, approved commit equals local HEAD, expected remote and upstream, expected remote URL, `git ls-remote` remote head equals marker `remotehead`, ahead count is exactly `1`, behind count is `0`, exactly one local commit is ahead, and the committed file-list fingerprint matches `commitfiles`.

After validation, `PushOnce` runs one command shaped as:

```powershell
git push origin HEAD:master
```

using the marker-approved remote and branch values. It then checks the remote branch HEAD with `git ls-remote` and requires it to equal the pushed commit.

Safety boundaries:

- PushOnce only
- exactly one current `push-approved-once` marker
- one approved commit only
- no reuse of `push-dryrun-approved` markers
- no reuse of commit approval markers
- no issue close
- no label edit
- no PR creation
- no merge or force push
- no approval chaining
- no daemon, scheduler, or watcher

## CloseIssueOnce rail

`CloseIssueOnce` closes one selected open issue after an explicit, state-bound approval marker on that same issue.

Use:

```powershell
.\scripts\local_runner_v2.ps1 -CloseIssueOnce -IssueNumber <N>
```

`-IssueNumber <N>` is mandatory. If it is missing, the command stops before reading GitHub Issues. This mode scans only the selected issue; it does not broad-scan open issues.

The approval comment format is:

```text
RUNNER-V2-APPROVE protocol=v2.approval.1 action=close-issue-approved-once issue=<N> repo=HarryWhite-TW/local-ai-workbench target=<N> targetstate=OPEN branch=master localhead=<sha> remote=origin upstream=origin/master remotehead=<sha> pushed=<sha> expires=<UTC_BASIC>
```

`CloseIssueOnce` requires exactly one current `action=close-issue-approved-once` marker on the selected issue. The marker `issue` and `target` must both equal the selected `-IssueNumber`, `targetstate` must be `OPEN`, and the selected issue must still be open at execution time.

The local / remote state must prove the approved work is already pushed:

- clean working tree
- no staged files
- current branch matches `branch`
- local `HEAD` matches `localhead`
- remote exists and matches `remote`
- upstream matches `upstream`
- read-only `git ls-remote` remote HEAD matches `remotehead`
- local `HEAD` equals remote HEAD
- `pushed` equals local `HEAD`
- `pushed` equals remote HEAD

If validation passes, `CloseIssueOnce` runs exactly one close operation for the selected issue:

```powershell
gh issue close <N> --repo HarryWhite-TW/local-ai-workbench
```

It then reads the selected issue again and reports the selected issue number, previous issue state, final issue state, local HEAD, remote HEAD, pushed commit SHA, and final git status.

Safety boundaries:

- CloseIssueOnce only
- explicit selected issue only
- no broad open-issue scan
- no labels
- no PR creation
- no merge
- no push
- no commit
- no staging
- no multi-issue close
- no cross-issue close
- no approval chaining
- no auto close after push
- no reuse of push, commit, or ReviewBundle approval markers

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

# Runner v1 Review Bundle Usage

## Purpose

Runner v1 is a helper for write-capable GitHub Issues.

By default, it runs in review-bundle-only mode. It can run Codex locally for an Issue, leave any repo changes unstaged, collect review data, and post a structured `local-runner-v1 review bundle` comment back to the same Issue.

It also has an explicit Level 3A local commit mode through `-Mode CommitApproved`. That mode requires a local ASCII approval token and creates one local commit after validating the current repo state.

Current limit: this version does not push, close issues, edit labels, create PRs, merge, force push, or parse GitHub comments for approval.

Review-bundle mode does not approve, stage, commit, push, close issues, edit labels, create pull requests, or consume approval tokens.

## When to use it

Use runner v1 review-bundle mode only when:

- The repo is clean before starting.
- The GitHub Issue explicitly says it is write-capable or review-bundle capable.
- You want Codex to prepare local changes for human review.
- You want GitHub to receive a bounded review bundle with final status and diff summary.

Do not use runner v1 for read-only audits. Use runner v0 for those.

## How to run

Open PowerShell at the repo root directory for this checkout.

Run:

```powershell
.\scripts\local_runner_v1.ps1 -IssueNumber <N>
```

Replace `<N>` with the GitHub Issue number.

The script derives the repo root from its own location, so it does not require a hard-coded local checkout path.

`ReviewBundle` is the default mode. You can also run it explicitly:

```powershell
.\scripts\local_runner_v1.ps1 -IssueNumber <N> -Mode ReviewBundle
```

## Level 3A local commit mode

After reviewing a `local-runner-v1 review bundle`, run commit mode only when a human / ChatGPT reviewer has approved the exact local state:

```powershell
.\scripts\local_runner_v1.ps1 -IssueNumber <N> -Mode CommitApproved
```

Commit mode prints the current approval context, then asks for an exact ASCII token:

```text
LRV1-APPROVE issue=<N> mode=Level3A branch=<branch> head=<head> review=<review-id> diff=<diff-sha256> files=<files-sha256>
```

The approval token is not a secret credential. It is a state-bound local confirmation string for the current issue, branch, HEAD, review id, diff fingerprint, and files fingerprint. Human / ChatGPT review is still required before entering it.

Before staging, commit mode recomputes the current branch, HEAD, modified file list, diff fingerprint, and files fingerprint. It rejects stale tokens, preexisting staged files, and outside-allowlist changes.

If validation succeeds, it stages only the approved files, creates exactly one local commit, and posts the commit SHA plus final git status back to the GitHub Issue.

If validation, staging, or commit fails, commit mode tries to post a GitHub failure comment with the reason, branch, HEAD, and final git status. It does not auto-reset; if files may be staged, human cleanup is required.

Commit mode does not push, close issues, edit labels, create PRs, merge, force push, or parse GitHub comments for approval.

## Safety boundaries

Runner v1 review-bundle-only mode:

- Requires a clean repo before Codex starts.
- Stops before Codex if the repo is dirty.
- Runs Codex with the `workspace-write` sandbox.
- Leaves Codex changes unstaged for review.
- Posts a GitHub Issue review bundle.
- Does not stage, commit, push, merge, close issues, edit labels, create PRs, or consume approval tokens.
- Does not implement Level 3B push or close issue.

## Review bundle contents

The GitHub comment includes:

- run metadata
- safety status
- modified files
- `git diff --stat`
- commands / verification summary
- Codex final report
- stderr summary
- final git status
- next approval note

## After it succeeds

Review the GitHub Issue comment and the local unstaged diff before taking any manual follow-up action.

Do not commit until a separate approval step is implemented or manual commit instructions are given.

# Runner v1 Review Bundle Usage

## Purpose

Runner v1 is a review-bundle-only helper for write-capable GitHub Issues.

It can run Codex locally for an Issue, leave any repo changes unstaged, collect review data, and post a structured `local-runner-v1 review bundle` comment back to the same Issue.

Current limit: this version is review-bundle-only and does not implement approval-token local commit yet.

Runner v1 does not approve, stage, commit, push, close issues, edit labels, create pull requests, or consume approval tokens.

## When to use it

Use runner v1 only when:

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

## Safety boundaries

Runner v1 review-bundle-only mode:

- Requires a clean repo before Codex starts.
- Stops before Codex if the repo is dirty.
- Runs Codex with the `workspace-write` sandbox.
- Leaves Codex changes unstaged for review.
- Posts a GitHub Issue review bundle.
- Does not stage, commit, push, merge, close issues, edit labels, create PRs, or consume approval tokens.
- Does not implement Level 3A local commit.
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

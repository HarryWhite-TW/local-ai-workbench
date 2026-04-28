# Runner v0 Usage

## Purpose

Runner v0 is a small local helper for running a read-only Codex task from a GitHub Issue.

It reads the Issue with GitHub CLI, runs Codex locally in read-only mode, and posts the Codex result back to the same GitHub Issue as a comment. It is meant to reduce manual copy and paste between ChatGPT, Codex, and GitHub while keeping the user in control.

Runner v0 is only for the current local, single-user prototype workflow.

## When to use it

Use runner v0 when:

- A GitHub Issue contains a clear Codex task.
- The task should be handled as read-only Codex execution.
- You want Codex output posted back to the Issue automatically.
- You want ChatGPT to review the GitHub Issue comment afterward.

Do not use runner v0 for tasks that require file edits, staging, commits, pushes, pull requests, issue closing, label changes, or other write automation.

## How to run

Open PowerShell at the repo root:

```text
C:\Users\harry\OneDrive\文件\New project
```

Run:

```powershell
.\scripts\local_runner.ps1 -IssueNumber <N>
```

Replace `<N>` with the GitHub Issue number.

Example:

```powershell
.\scripts\local_runner.ps1 -IssueNumber 14
```

## After it succeeds

After the runner finishes successfully, reply to ChatGPT with:

```text
Issue #<N> runner result posted.
```

Example:

```text
Issue #14 runner result posted.
```

ChatGPT can then read the GitHub Issue comment directly.

## Success checklist

On GitHub, success should look like this:

- A new `local-runner-v0 result` comment appears on the Issue.
- The Codex exit code is shown.
- The Codex result is visible in the comment.
- Diagnostics are summarized.
- Final git status is shown.

## If it appears to hang

If the runner appears to hang:

1. Wait a few minutes, especially for longer Issue prompts.
2. Check whether PowerShell is still producing output.
3. Check the GitHub Issue to see whether a `local-runner-v0 result` comment was posted.
4. If there is no new comment and PowerShell does not finish, stop and ask ChatGPT what to inspect next.

Do not start extra automation or switch to a write-capable workflow while troubleshooting runner v0.

## If it fails

If the runner fails, paste the following back to ChatGPT:

- The command you ran.
- The Issue number.
- The Codex exit code, if shown.
- Any PowerShell error output.
- Any GitHub CLI error output.
- Any stderr summary shown by the runner.
- The final git status shown by the runner, if available.
- Whether a GitHub Issue comment was posted.

## Safety boundaries

Runner v0 currently has these boundaries:

- Read-only Codex execution only.
- The runner does not automatically modify repo files.
- The only intentional write-back is the GitHub Issue comment with the runner result.
- No stage, commit, push, merge, or pull request.
- No issue close or label edits.
- No PATH or Windows setting changes.
- It currently uses an absolute `gh.exe` path.

## Current limitations

Do not expand runner v0 into these workflows yet:

- No runner v1.
- No branch-based write automation.
- No write automation.
- No auto-commit.
- No auto-PR.
